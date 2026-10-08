# ==============================================================================
# core/openbuilds_link.py — ฟังข้อมูลจาก OpenBuilds Control แบบ real-time แล้ว
# บันทึกเป็นไฟล์ .log ของแต่ละ job อัตโนมัติ (ไม่ต้อง copy console เอง)
# ==============================================================================
# VERSION: 02
# CHANGE LOG (v01 -> v02):
#   write_job_log(): เลือกรูปแบบชื่อไฟล์ได้ (LOG_NAME_CHOICES: ชื่อ job + เวลา / เวลา /
#   ชื่อ job) ชื่อซ้ำต่อท้าย _2, _3 ไม่เขียนทับ + บันทึกชื่อ job ในหัวไฟล์
# หน้าที่:
#   OpenBuildsLink  — ต่อ socket.io (v4, transport=polling) ของ OpenBuilds Control
#                     ที่ http://localhost:3000 ซึ่งเป็นช่องทางเดียวกับที่หน้าจอของ
#                     OpenBuilds เองใช้ แล้วส่งทุก event เข้า callback (thread แยก)
#                     ต่อใหม่เองถ้า OpenBuilds ปิด/เปิดใหม่ — ใช้ standard library ล้วน
#   JobRecorder     — รับ event แล้วแบ่งเป็น "job": เริ่มเมื่อมีคิว G-code (queue > 0
#                     หรือ runStatus = Run) จบเมื่อได้ jobComplete (หรือคิวว่าง + Idle
#                     นานเกิน _IDLE_END_S) เก็บทุกบรรทัดตอบกลับของ GRBL ใน job นั้น
#   write_job_log() — เขียน job เป็นไฟล์ .log ที่ core/log_parser.py อ่านได้
#
# สำคัญ — พิกัดใน [PRB:x,y,z:s] ของ GRBL เป็น "พิกัดเครื่อง" (MPos) เสมอ ไม่ใช่พิกัด
# เทียบจุด Set Zero ที่ Schema ใช้ — จึงบันทึก work offset (WCO / G54) จาก status ของ
# OpenBuilds ไว้เป็นบรรทัด "; WCO: x,y,z" ก่อนจุดแรกและทุกครั้งที่ offset เปลี่ยน
# log_parser.py v02 ลบ WCO ออกให้เอง: พิกัดงาน = PRB - WCO
#
# event ของ OpenBuilds Control ที่ใช้ (ตรวจกับ v1.0.390 / GRBL 1.1h):
#   data        {"command": "G38.2 ...", "response": "[PRB:...:1]", "type": ...}
#   status      {"comms": {"runStatus", "queue", "alarm", ...},
#                "machine": {"position": {"work": {...}, "offset": {x, y, z}}, ...}}
#   queueCount  [จำนวนบรรทัดที่ยังรอส่ง, ...]
#   jobComplete {"completed", "failed", "jobStartTime", "jobEndTime"}
#               (ตอนต่อครั้งแรกจะได้ jobComplete เก่ามา 1 ครั้ง — ไม่สนใจถ้าไม่ได้อัดอยู่)
#
# ตัวแปรสำคัญที่ปรับจูนได้:
#   DEFAULT_HOST / DEFAULT_PORT = ที่อยู่ของ OpenBuilds Control
#   _RETRY_S    = รอกี่วินาทีก่อนต่อใหม่เมื่อหลุด
#   _IDLE_END_S = คิวว่าง + Idle นานเท่านี้ ถือว่า job จบ (กันกรณีไม่ได้ jobComplete)
# ==============================================================================
import datetime
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 3000
_RETRY_S     = 3.0
_IDLE_END_S  = 3.0

_PRB_RE = re.compile(r"\[PRB:[^\]]*\]")


def default_log_dir() -> str:
    """โฟลเดอร์เริ่มต้นของไฟล์ log: Documents\\3D ProbeCode\\Logs"""
    return os.path.join(os.path.expanduser("~"), "Documents", "3D ProbeCode", "Logs")


# ==============================================================================
# 1) socket.io client (Engine.IO v4, long-polling)
# ==============================================================================
class OpenBuildsLink:
    """ต่อ OpenBuilds Control แล้วเรียก on_event(name, payload) ทุก event
    on_state(connected: bool, message: str) เมื่อสถานะการเชื่อมต่อเปลี่ยน
    callback ทั้งสองถูกเรียกจาก thread เบื้องหลัง — ฝั่ง UI ต้องส่งต่อเข้า main thread เอง"""

    def __init__(self, on_event, on_state=None, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.on_event = on_event
        self.on_state = on_state or (lambda connected, message: None)
        self.base = f"http://{host}:{port}/socket.io/?EIO=4&transport=polling"
        self.connected = False
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="openbuilds-link", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and not self._stop.is_set()

    # ------------------------------------------------------------------
    def _set_state(self, connected: bool, message: str):
        if connected != self.connected or not connected:
            self.connected = connected
            self.on_state(connected, message)

    def _run(self):
        while not self._stop.is_set():
            try:
                self._session()
            except (urllib.error.URLError, OSError, ValueError) as e:
                self._set_state(False, f"OpenBuilds Control not reachable ({e.__class__.__name__}) "
                                       f"- retrying every {_RETRY_S:g} s")
            self._stop.wait(_RETRY_S)
        self._set_state(False, "stopped")

    def _session(self):
        hello = self._get(self.base, timeout=5)
        if not hello.startswith("0"):
            raise ValueError("unexpected handshake")
        info = json.loads(hello[1:])
        url = f"{self.base}&sid={info['sid']}"
        poll_timeout = (info.get("pingInterval", 25000) + info.get("pingTimeout", 20000)) / 1000 + 5
        self._post(url, "40")                      # เข้า namespace "/"
        self._set_state(True, "connected to OpenBuilds Control")
        while not self._stop.is_set():
            for pkt in self._get(url, timeout=poll_timeout).split("\x1e"):
                if pkt == "2":                     # ping จาก server → ตอบ pong
                    self._post(url, "3")
                elif pkt.startswith("42"):
                    try:
                        ev = json.loads(pkt[2:])
                    except ValueError:
                        continue
                    if ev:
                        self.on_event(ev[0], ev[1] if len(ev) > 1 else None)
                elif pkt.startswith("1") or pkt.startswith("41"):
                    raise ValueError("server closed the session")

    @staticmethod
    def _get(url: str, timeout: float) -> str:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")

    @staticmethod
    def _post(url: str, body: str):
        req = urllib.request.Request(url, data=body.encode("utf-8"), method="POST",
                                     headers={"Content-Type": "text/plain;charset=UTF-8"})
        with urllib.request.urlopen(req, timeout=5) as r:
            r.read()


# ==============================================================================
# 2) แบ่ง event เป็น job
# ==============================================================================
class Job:
    """ข้อมูล 1 job — lines = บรรทัดที่จะเขียนลงไฟล์ (รวมบรรทัด "; WCO:")"""
    def __init__(self):
        self.start = datetime.datetime.now()
        self.end = None
        self.result = "running"
        self.lines = []
        self.probe_count = 0
        self.machine = ""


class JobRecorder:
    """feed(name, payload) ทุก event — คืน Job ที่เพิ่งจบ (หรือ None)
    armed=False = อัดทุก job (โปรแกรม logger), armed=True = อัดแค่ job ถัดไป (ปุ่มในแอป)
    — ใน armed mode เรียก arm() ก่อน แล้ว job ถัดไปที่จบจะถูกคืนมา จากนั้นหยุดอัด"""

    def __init__(self, armed: bool = False):
        self.one_shot = armed
        self.armed = not armed
        self.job = None
        self.offset = None          # (x, y, z) work offset ล่าสุด
        self._written_offset = None
        self._idle_since = None
        self.machine = ""

    def arm(self):
        self.armed = True
        self.job = None

    def disarm(self):
        self.armed = False
        self.job = None

    @property
    def recording(self) -> bool:
        return self.job is not None

    # ------------------------------------------------------------------
    def feed(self, name: str, payload):
        if name == "status" and isinstance(payload, dict):
            return self._on_status(payload)
        if name == "grbl" and isinstance(payload, dict):
            self.machine = f"{payload.get('type', '')} {payload.get('version', '')}".strip()
        elif name == "queueCount" and isinstance(payload, list) and payload:
            if self._num(payload[0]) > 0:
                self._begin()
        elif name == "data" and isinstance(payload, dict) and self.job is not None:
            self._on_data(payload)
        elif name == "jobComplete" and isinstance(payload, dict) and self.job is not None:
            if payload.get("jobStartTime"):   # jobComplete ของคำสั่ง $$/$G มี jobStartTime = false
                failed = bool(payload.get("failed"))
                return self._finish("failed" if failed else "completed")
        return None

    def _on_status(self, st: dict):
        comms = st.get("comms") or {}
        pos = ((st.get("machine") or {}).get("position") or {}).get("offset")
        if isinstance(pos, dict):
            self.offset = tuple(self._num(pos.get(k)) for k in ("x", "y", "z"))
        run, queue = str(comms.get("runStatus", "")), self._num(comms.get("queue"))
        # runStatus = "Running" สั้น ๆ ทุกครั้งที่ OpenBuilds ถาม $$/$I/$G เอง — เริ่ม job
        # เฉพาะเมื่อมี G-code เข้าคิวจริง (queue > 0) เท่านั้น
        if queue > 0:
            self._begin()
        if self.job is None:
            return None
        alarm = comms.get("alarm")
        if alarm:
            self.job.lines.append(f"; ALARM: {alarm}")
            return self._finish("alarm")
        if queue > 0 or run.lower() != "idle":
            self._idle_since = None
            return None
        now = time.monotonic()       # คิวว่าง + Idle — ถ้านานพอถือว่า job จบ
        self._idle_since = self._idle_since or now
        if now - self._idle_since >= _IDLE_END_S:
            return self._finish("completed (idle)")
        return None

    def _on_data(self, d: dict):
        cmd = str(d.get("command") or "").strip()
        resp = str(d.get("response") or "").strip()
        if _PRB_RE.search(resp):
            if self.offset is not None and self.offset != self._written_offset:
                self.job.lines.append("; WCO: " + ",".join(f"{v:.3f}" for v in self.offset))
                self._written_offset = self.offset
            self.job.probe_count += 1
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.job.lines.append(f"[{ts}] [ {cmd} ] {resp}")

    def _begin(self):
        if self.job is None and self.armed:
            self.job = Job()
            self.job.machine = self.machine
            self._written_offset = None
            self._idle_since = None

    def _finish(self, result: str):
        job, self.job = self.job, None
        job.end = datetime.datetime.now()
        job.result = result
        if self.one_shot:
            # คำสั่งเดี่ยวจาก console / jog ก็นับเป็นคิว — ถ้ายังไม่มีจุดโพรบเลยและไม่ใช่
            # alarm ให้รอ job จริงต่อไป (ไม่เสียการ arm ไปกับการ jog ก่อนรัน)
            if job.probe_count == 0 and result != "alarm":
                return None
            self.armed = False
        return job

    @staticmethod
    def _num(v) -> float:
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0


# ==============================================================================
# 3) เขียนไฟล์ .log
# ==============================================================================
# ชื่อไฟล์ log: (key, ข้อความในเมนู) — "both" เป็นค่าเริ่มต้น
LOG_NAME_CHOICES = [
    ("both", "Job name + time"),
    ("time", "Time only"),
    ("job",  "Job name only"),
]


def log_file_name(job_name: str, start: datetime.datetime, naming: str = "both") -> str:
    """ชื่อไฟล์ (ไม่รวมโฟลเดอร์) ตามรูปแบบที่เลือก — job_name ถูกกรองอักขระต้องห้ามแล้ว"""
    name = re.sub(r'[\/:*?"<>|]+', "_", (job_name or "").strip()) or "job"
    stamp = start.strftime("%Y-%m-%d_%H-%M-%S")
    stem = {"time": stamp, "job": name}.get(naming, f"{name}_{stamp}")
    return stem + ".log"


def write_job_log(job: Job, folder: str, job_name: str = "job", naming: str = "both") -> str:
    """เขียน job ลง <folder>/<ชื่อตาม naming> แล้วคืน path — ชื่อซ้ำจะต่อท้าย _2, _3, …
    (ไม่เขียนทับไฟล์เก่า)"""
    os.makedirs(folder, exist_ok=True)
    stem, ext = os.path.splitext(log_file_name(job_name, job.start, naming))
    path, n = os.path.join(folder, stem + ext), 2
    while os.path.exists(path):
        path, n = os.path.join(folder, f"{stem}_{n}{ext}"), n + 1
    end = job.end.strftime("%H:%M:%S") if job.end else "—"
    header = [
        "; 3D ProbeCode - OpenBuilds Control job log",
        f"; Job: {job.start:%Y-%m-%d %H:%M:%S} -> {end}   result: {job.result}"
        f"   probe points: {job.probe_count}",
        f"; Job name: {job_name or '—'}   Machine: {job.machine or 'unknown'}",
        "; [PRB:x,y,z:s] values are MACHINE coordinates. '; WCO: x,y,z' = work offset",
        ";   (Set Zero) in effect; work position = PRB - WCO (applied by the app's log parser).",
        "",
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(header + job.lines) + "\n")
    return path
