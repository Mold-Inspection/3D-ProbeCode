# ==============================================================================
# openbuilds_job_logger.py — โปรแกรมเสริมของ OpenBuilds Control: บันทึกไฟล์ .log
# ให้ทุก job อัตโนมัติ (เปิดทิ้งไว้ข้าง OpenBuilds ก็พอ ไม่ต้องเปิด 3D ProbeCode)
# ==============================================================================
# VERSION: 01
# OpenBuilds Control ไม่มีระบบ plugin ให้เขียนไฟล์ได้ — โปรแกรมนี้จึงต่อเข้า server
# ของ OpenBuilds (localhost:3000) แบบเดียวกับหน้าจอของมันเอง ฟังทุก job แล้วเขียน
# <out>/job_<วันเวลา>.log หลัง job จบ (รูปแบบเดียวกับปุ่ม Record ในแท็บ Evaluation —
# มีบรรทัด "; WCO:" ให้ log_parser แปลงพิกัดเครื่องเป็นพิกัดเทียบ Set Zero ได้)
#
# วิธีใช้:
#   python openbuilds_job_logger.py                 (เก็บที่ Documents\3D ProbeCode\Logs)
#   python openbuilds_job_logger.py --out D:\logs   (เลือกโฟลเดอร์เอง)
#   python openbuilds_job_logger.py --all           (เก็บ job ที่ไม่มีจุดโพรบด้วย)
#   หยุด: Ctrl+C
# ==============================================================================
import argparse
import datetime
import os
import queue
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.openbuilds_link import (DEFAULT_HOST, DEFAULT_PORT, JobRecorder, OpenBuildsLink,
                                  default_log_dir, write_job_log)


def _say(msg: str):
    print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}", flush=True)


def main():
    ap = argparse.ArgumentParser(description="Save an OpenBuilds Control log file after every job.")
    ap.add_argument("--out", default=default_log_dir(), help="folder for the .log files")
    ap.add_argument("--all", action="store_true", help="also save jobs with no probe points")
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = ap.parse_args()

    events = queue.Queue()   # ส่ง event จาก thread ของ link มาประมวลผลใน thread หลัก
    link = OpenBuildsLink(on_event=lambda n, p: events.put((n, p)),
                          on_state=lambda ok, msg: _say(msg),
                          host=args.host, port=args.port)
    recorder = JobRecorder()
    _say(f"saving job logs to {args.out}  (Ctrl+C to stop)")
    link.start()
    was_recording = False
    try:
        while True:
            try:
                name, payload = events.get(timeout=0.5)
            except queue.Empty:
                continue
            job = recorder.feed(name, payload)
            if recorder.recording and not was_recording:
                _say("job started - recording")
            was_recording = recorder.recording
            if job is None:
                continue
            if job.probe_count == 0 and not args.all:
                _say(f"job {job.result} - no probe points, not saved")
                continue
            path = write_job_log(job, args.out, naming="time")
            _say(f"job {job.result} - {job.probe_count} probe point(s) saved to {path}")
    except KeyboardInterrupt:
        _say("stopped")
    finally:
        link.stop()


if __name__ == "__main__":
    main()
