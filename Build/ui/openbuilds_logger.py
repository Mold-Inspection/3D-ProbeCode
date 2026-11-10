# ==============================================================================
# ui/openbuilds_logger.py — ตัวบันทึก log เบื้องหลังและส่ง G-code
# ==============================================================================
# สรุปหน้าที่:
#   ตัวบันทึก log เบื้องหลังของหน้าต่างหลัก: ใช้ OpenBuildsLink + JobRecorder
#   ส่ง G-code อ่านค่า $$ ตั้ง $1=255 และแจ้งเมื่อมี log ใหม่
#
# ไฟล์ที่เกี่ยวข้อง:
#   ใช้งานไฟล์เหล่านี้:
#     - core/openbuilds_link.py — เชื่อม socket.io ของ OpenBuilds และบันทึก job เป็น .log (JobRecorder, OpenBuildsLink, default_log_dir, write_job_log)
#     - core/user_settings.py — จำค่าตั้งใน settings.json (get, py, save_section)
#   ถูกใช้งานโดย:
#     - ui/main_window.py — หน้าต่างหลัก UIManager (OpenBuildsLogger)
#   ไลบรารีภายนอก: os, queue, re, time
#
# รายละเอียด:
#   ตัวบันทึก log ของ OpenBuilds Control ที่ทำงานเบื้องหลัง
#   ตั้งแต่เปิดหน้าต่างหลัก (ไม่ต้องเปิด start_openbuilds_logger.bat แยก)
#
#   หน้าที่: ถือการเชื่อมต่อ OpenBuilds Control ตัวเดียวของทั้งแอป (core/openbuilds_link.py)
#   ทุก job ที่มีจุดโพรบ → เขียน <log_dir>/<ชื่อตาม log_name>.log แล้วแจ้งผู้ฟัง
#   (ปุ่ม Record ในแท็บ Evaluation ฟังจากที่นี่เพื่อประเมินผล job ถัดไป)
#
#   event จาก thread ของ OpenBuildsLink ถูกส่งผ่าน queue แล้วประมวลผลใน main thread
#   ด้วย root.after() — callback ทุกตัว (on_saved / on_status) จึงแตะ widget ได้ตรง ๆ
#
#   ค่าที่จำไว้ (core/user_settings.py, section "openbuilds"):
#     auto_log = True/False — เริ่มบันทึกอัตโนมัติตอนเปิดโปรแกรม (ค่าเริ่มต้น True)
#     log_dir  = โฟลเดอร์เก็บไฟล์ (ค่าเริ่มต้น Documents\3D ProbeCode\Logs)
#     log_name = "both" (ชื่อ job + เวลา) / "time" / "job" — core/openbuilds_link.LOG_NAME_CHOICES
#
#   ตัวแปรสำคัญที่ปรับจูนได้:
#     _POLL_MS = ความถี่ที่ดึง event จาก queue เข้ามาประมวลผล (ms)
# ==============================================================================

import os
import queue
import re
import time

from core import user_settings
from core.openbuilds_link import JobRecorder, OpenBuildsLink, default_log_dir, write_job_log

_POLL_MS = 250
_SETTING = re.compile(r"\$(\d+)=([-\d.]+)")


class OpenBuildsLogger:
    def __init__(self, app):
        self.app = app
        self.link = None
        self.recorder = None
        self.events = queue.Queue()
        self.connected = False
        self.status = "Auto-log off"
        self.last_path = None
        self.on_saved = []      # callback(job, path) หลังบันทึกไฟล์แต่ละ job
        self.on_status = []     # callback(text) เมื่อสถานะเปลี่ยน
        self.on_settings = []   # callback() เมื่อค่าตั้ง (auto_log / log_dir / log_name) เปลี่ยน
        self.on_event = []      # callback(name, payload) ทุก event จาก OpenBuilds (main thread)
        self._quiet_until = 0.0 # งานที่จบก่อนเวลานี้ไม่บันทึก log (งานแตะผนังตั้ง zero)
        self.last_status = None # status ล่าสุดจาก OpenBuilds (ใช้ตรวจตำแหน่งก่อน Find centre)
        self.grbl = {}          # ค่า GRBL ล่าสุด {เลข $: float} จากคำตอบของ $$
        self._asked_settings = False

    # ------------------------------------------------------------------
    # ค่าที่จำไว้
    # ------------------------------------------------------------------
    @staticmethod
    def _settings() -> dict:
        return user_settings.get("openbuilds", {}) or {}

    @property
    def auto_log(self) -> bool:
        return bool(self._settings().get("auto_log", True))

    def _save(self, key, value):
        saved = self._settings()
        saved[key] = value
        user_settings.save_section("openbuilds", saved)
        for cb in list(self.on_settings):
            try:
                cb()
            except Exception as e:
                print(f"[openbuilds_logger] settings callback failed: {e!r}")

    def set_auto_log(self, on: bool):
        """เปิด/ปิด auto-log (จำค่า) และเริ่ม/หยุดการเชื่อมต่อตามนั้น"""
        self._save("auto_log", bool(on))
        if on:
            self.start()
        else:
            self.stop()

    @property
    def log_dir(self) -> str:
        return self._settings().get("log_dir") or default_log_dir()

    def set_log_dir(self, folder: str):
        self._save("log_dir", folder)
        if self.connected:
            self._set_status(self._ready_text())

    @property
    def log_name(self) -> str:
        return self._settings().get("log_name") or "both"

    def set_log_name(self, naming: str):
        self._save("log_name", naming)

    def job_name(self) -> str:
        """ชื่อ job: G-code ที่ export ล่าสุด → ชื่อไฟล์ STEP → 'job'"""
        name = getattr(self.app, 'last_gcode_name', None)
        if not name:
            name = os.path.splitext(getattr(self.app, 'loaded_step_filename', None) or "")[0]
        return name or "job"

    # ------------------------------------------------------------------
    # start / stop
    # ------------------------------------------------------------------
    @property
    def running(self) -> bool:
        return self.link is not None

    def start_if_enabled(self):
        if self.auto_log:
            self.start()

    def start(self):
        if self.link is not None:
            return
        self.recorder = JobRecorder()
        self.link = OpenBuildsLink(on_event=lambda n, p: self.events.put(("event", n, p)),
                                   on_state=lambda ok, msg: self.events.put(("state", ok, msg)))
        self.link.start()
        self._set_status("Connecting to OpenBuilds Control…")
        self.app.root.after(_POLL_MS, self._poll)

    def stop(self):
        if self.link is not None:
            self.link.stop()
        self.link = None
        self.recorder = None
        self.connected = False
        self._asked_settings = False
        self._set_status("Auto-log off")

    # ------------------------------------------------------------------
    def _set_status(self, text: str):
        self.status = text
        for cb in list(self.on_status):
            try:
                cb(text)
            except Exception as e:
                print(f"[openbuilds_logger] status callback failed: {e!r}")

    def _ready_text(self) -> str:
        return f"Connected — saving a log after every job to\n{self.log_dir}"

    def _poll(self):
        if self.link is None:
            return
        try:
            while True:
                kind, a, b = self.events.get_nowait()
                if kind == "state":
                    self.connected = bool(a)
                    self._set_status(self._ready_text() if a else f"⚠ {b}")
                    continue
                if a == "status" and isinstance(b, dict):   # สถานะล่าสุด (ตำแหน่ง, alarm)
                    self.last_status = b
                    self._read_settings_once(b)
                elif a == "data" and isinstance(b, dict):    # $N=ค่า จาก $$ (ของใครก็ได้)
                    m = _SETTING.match(str(b.get("response") or "").strip())
                    if m:
                        self.grbl[int(m.group(1))] = float(m.group(2))
                for cb in list(self.on_event):
                    try:
                        cb(a, b)
                    except Exception as e:
                        print(f"[openbuilds_logger] event callback failed: {e!r}")
                was_recording = self.recorder.recording
                job = self.recorder.feed(a, b)
                if self.recorder.recording:
                    if not was_recording or a == "data":
                        self._set_status(f"● Recording job… {self.recorder.job.probe_count} probe point(s)")
                elif job is not None:
                    self._on_job(job)
        except queue.Empty:
            pass
        self.app.root.after(_POLL_MS, self._poll)

    # ------------------------------------------------------------------
    # ส่งคำสั่งให้เครื่อง (ผ่าน OpenBuilds Control)
    # ------------------------------------------------------------------
    def send_gcode(self, text: str):
        """เข้าคิวของ OpenBuilds เหมือนพิมพ์ใน console (หลายบรรทัดได้) — ต้องเชื่อมต่ออยู่"""
        if self.link is None:
            raise ConnectionError("OpenBuilds link is not running")
        self.link.send("runCommand", text)

    def _read_settings_once(self, status: dict):
        """อ่าน $$ ครั้งเดียวหลังเชื่อมต่อ — เฉพาะตอน Idle และไม่มีคิว (ไม่ทำให้เครื่องขยับ)"""
        comms = status.get("comms") or {}
        if self._asked_settings or self.grbl or not self.connected:
            return
        if str(comms.get("runStatus", "")).lower() != "idle" or comms.get("alarm") or comms.get("queue"):
            return
        self._asked_settings = True
        self.suppress_logs(5)
        self.send_gcode("$$")

    def ensure_idle_delay(self):
        """ก่อนงานที่เครื่องขยับ — $1 ≠ 255 (หรือยังไม่รู้ค่า) ตั้ง $1=255 ให้เลย ไม่ถาม
        (เครื่องต้อง Idle อยู่ — ผู้เรียกตรวจแล้ว; คำสั่งเข้าคิวก่อน G-code ของงานนั้น)"""
        if self.grbl.get(1) == 255:
            return
        self.suppress_logs(5)
        self.send_gcode("$1=255\n$$")
        self.grbl[1] = 255.0
        print("[openbuilds_logger] $1 set to 255 (motors stay powered between moves)")

    def discard_job(self):
        """ทิ้ง job ที่ยังอัดค้างอยู่ (ไม่บันทึก) — เรียกก่อนส่ง G-code งานใหม่ตอนเครื่อง Idle"""
        if self.recorder is not None and self.recorder.recording:
            print(f"[openbuilds_logger] discarded an unfinished job ({self.recorder.job.probe_count} point(s))")
            self.recorder.job = None

    def stop_machine(self):
        """เหมือนปุ่ม Stop ของ OpenBuilds: พักการเคลื่อนที่ ล้างคิว แล้ว soft reset"""
        if self.link is not None:
            self.link.send("stop", {"stop": False, "jog": False, "abort": False})

    def suppress_logs(self, seconds: float):
        """งานที่จบภายใน seconds วินาทีจากนี้ไม่ถูกบันทึกเป็นไฟล์ log"""
        self._quiet_until = time.monotonic() + float(seconds)

    def _on_job(self, job):
        if time.monotonic() < self._quiet_until:   # งานแตะผนังตั้ง zero — ไม่บันทึก
            self._set_status(self._ready_text())
            return
        if job.probe_count == 0:
            self._set_status(self._ready_text())
            return
        try:
            path = write_job_log(job, self.log_dir, job_name=self.job_name(), naming=self.log_name)
        except OSError as e:
            self._set_status(f"⚠ Could not save the log: {e}")
            return
        self.last_path = path
        print(f"[openbuilds_logger] job {job.result}: {job.probe_count} point(s) -> {path}")
        self._set_status(f"Last job {job.result} — {job.probe_count} point(s) saved:\n{path}")
        for cb in list(self.on_saved):
            try:
                cb(job, path)
            except Exception as e:
                print(f"[openbuilds_logger] saved callback failed: {e!r}")
