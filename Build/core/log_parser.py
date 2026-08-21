# ==============================================================================
# core/log_parser.py — อ่านไฟล์ .log จาก OpenBuilds Control -> รายการจุดที่
# ถูกโพรบจริง (actual probe points) เรียงตามลำดับที่ไฟล์บันทึกไว้
# ==============================================================================
# VERSION: 01
# หน้าที่: แกะบรรทัด GRBL probe-report ("[PRB:x,y,z:s]") ออกจากไฟล์ .log ที่
# OpenBuilds Control บันทึกไว้หลังรันโปรแกรม G-code จริงบนเครื่อง แปลงเป็น
# รายการจุด (x, y, z) เรียงตามลำดับที่ปรากฏในไฟล์ — ลำดับนี้ตรงกับลำดับที่
# core/gcode_generator.py::build_point_map() คำนวณ "จุดที่คาดหวัง" ไว้แล้ว
# (ดู core/evaluation_engine.py::evaluate_points() ซึ่งจับคู่ทั้งสองฝั่งด้วย
# sequence index ไม่ใช่ spatial nearest-neighbor — ดูเหตุผลใน
# PLAN_evaluation-tab-openbuilds-log-comparison_v02.md §3)
#
# NOTE (สำคัญ — สมมติฐานรูปแบบไฟล์ ยังไม่เคยเห็นตัวอย่างไฟล์ .log จริง):
# ยังไม่มีตัวอย่างไฟล์ .log ของ OpenBuilds Control ให้ตรวจสอบจริง จึงเขียน
# โดยยึดตามรูปแบบ probe report มาตรฐานของเฟิร์มแวร์ GRBL คือ
#   [PRB:x,y,z:s]
# โดย s คือ 1 = probe สำเร็จ (touched), 0 = ไม่พบการสัมผัส (probe fail/timeout)
# — parser ตัวนี้ถูกออกแบบมาแบบ "ป้องกันตัวเอง" (defensive): ใช้ regex ค้นหา
# รูปแบบ [PRB:...] ที่ไหนก็ได้ในแต่ละบรรทัด (ไม่สนใจ prefix เช่น timestamp,
# log level, หรือข้อความอื่นรอบ ๆ) และบันทึกบรรทัดที่ parse ไม่ได้ไว้ต่างหาก
# (ไม่โยน exception ทิ้งข้อมูลไปเฉย ๆ) เพื่อให้แก้ไข regex ได้ง่ายทันทีที่มี
# ตัวอย่างไฟล์จริงมาเทียบ — ดู PLAN §10 "Remaining Assumption to Flag"
#
# ตัวแปรสำคัญที่ปรับจูนได้:
#   _PRB_PATTERN       = regex หลักที่ใช้จับบรรทัด probe report — แก้ตรงนี้
#                         จุดเดียวถ้ารูปแบบไฟล์จริงต่างจากสมมติฐาน
#   _SKIP_SUCCESS_ONLY = True = เก็บเฉพาะจุดที่ s==1 (probe สำเร็จจริง) ค่า
#                         เริ่มต้น — ตั้งเป็น False เพื่อเก็บทุกจุดรวม fail ด้วย
# ==============================================================================
import os
import re
import datetime

# รูปแบบมาตรฐาน GRBL probe report: [PRB:12.345,-6.789,3.210:1]
# ยอมรับเครื่องหมายลบ/จุดทศนิยม และไม่สนใจ whitespace รอบ ๆ ตัวเลข — ปรับได้
_PRB_PATTERN = re.compile(
    r"\[PRB:\s*([-+]?\d*\.?\d+)\s*,\s*([-+]?\d*\.?\d+)\s*,\s*([-+]?\d*\.?\d+)\s*:\s*(\d+)\s*\]"
)

# True = เก็บเฉพาะจุดที่ probe สัมผัสสำเร็จจริง (s==1) — ปรับได้
_SKIP_SUCCESS_ONLY = True

_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Log")


class LogParseWarning:
    """เก็บบรรทัดที่ parse ไม่ได้ (หรือ probe fail ถ้า _SKIP_SUCCESS_ONLY) ไว้
    เพื่อ debug — ไม่ใช่ exception เพราะไม่ควรทำให้การอ่านไฟล์ทั้งไฟล์ล้มเหลว
    แค่เพราะมีบางบรรทัดที่ไม่ตรงรูปแบบ (เช่นบรรทัด echo คำสั่ง, ข้อความสถานะอื่น)"""
    __slots__ = ("line_no", "raw_line", "reason")

    def __init__(self, line_no: int, raw_line: str, reason: str):
        self.line_no  = line_no
        self.raw_line = raw_line
        self.reason   = reason


def _write_debug_log(filepath: str, total_lines: int, matched: int,
                      warnings: list) -> None:
    """เขียนสรุปผลการ parse ลงไฟล์ log แยกต่างหาก (Build/Log/) เพื่อช่วย
    ตรวจสอบภายหลังว่ามีบรรทัดไหนที่ regex จับไม่ได้บ้าง — best-effort เท่านั้น
    ล้มเหลวได้โดยไม่กระทบผลลัพธ์การ parse หลัก"""
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        out_path = os.path.join(_LOG_DIR, f"log_parser_{ts}.txt")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(f"=== log_parser debug summary ===\n")
            f.write(f"source file : {filepath}\n")
            f.write(f"total lines : {total_lines}\n")
            f.write(f"matched     : {matched}\n")
            f.write(f"unmatched   : {len(warnings)}\n\n")
            if warnings:
                f.write("--- unmatched / skipped lines ---\n")
                for w in warnings:
                    f.write(f"L{w.line_no}: ({w.reason}) {w.raw_line!r}\n")
        print(f"[log_parser] debug summary written to {out_path}")
    except Exception as e:
        print(f"[log_parser] WARNING: could not write debug summary ({e!r})")


def parse_openbuilds_log(filepath: str) -> list:
    """อ่านไฟล์ .log ของ OpenBuilds Control แล้วคืนรายการจุดที่ถูกโพรบจริง
    เรียงตามลำดับที่ปรากฏในไฟล์ (ลำดับการทำงานจริงของเครื่อง)

    Parameters
    ----------
    filepath : path ของไฟล์ .log (หรือ .txt) ที่ผู้ใช้เลือกผ่าน file dialog

    Returns
    -------
    list ของ dict เรียงตามลำดับในไฟล์ แต่ละอันมี:
      seq_idx : ลำดับจุดนี้นับจาก 0 (ลำดับที่ใช้จับคู่กับ EXPECTED points
                ใน core/evaluation_engine.py::evaluate_points())
      x, y, z : พิกัดที่ probe รายงานว่าสัมผัส (mm)
      status  : สถานะจาก GRBL ("1"=สัมผัสสำเร็จ, "0"=ไม่พบการสัมผัส)
      raw     : บรรทัดดิบต้นฉบับ (เก็บไว้เผื่อ debug/ตรวจสอบย้อนหลัง)

    Raises
    ------
    FileNotFoundError, OSError : ถ้าเปิดไฟล์ไม่ได้ (ปล่อยให้ผู้เรียกจัดการ
    ผ่าน dialog แจ้งเตือน — ดู ui/evaluation_left_panel.py::_on_load_log())
    """
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        raw_lines = f.readlines()

    points   = []
    warnings = []
    matched  = 0

    for line_no, raw_line in enumerate(raw_lines, start=1):
        line = raw_line.rstrip("\n\r")
        if not line.strip():
            continue   # บรรทัดว่าง — ไม่ใช่ปัญหา ไม่ต้องบันทึกเป็น warning

        m = _PRB_PATTERN.search(line)
        if m is None:
            warnings.append(LogParseWarning(line_no, line, "no [PRB:...] match"))
            continue

        matched += 1
        try:
            x, y, z = float(m.group(1)), float(m.group(2)), float(m.group(3))
            status  = m.group(4)
        except ValueError:
            warnings.append(LogParseWarning(line_no, line, "numeric conversion failed"))
            continue

        if _SKIP_SUCCESS_ONLY and status != "1":
            warnings.append(LogParseWarning(line_no, line, f"probe not successful (status={status})"))
            continue

        points.append({
            'seq_idx': len(points),
            'x': x, 'y': y, 'z': z,
            'status': status,
            'raw': line,
        })

    _write_debug_log(filepath, len(raw_lines), matched, warnings)

    if not points:
        print(f"[log_parser] WARNING: 0 probe points parsed from {filepath} "
              f"({len(warnings)} unmatched/skipped line(s)) — the assumed "
              f"GRBL [PRB:...] format may not match this file; see the debug "
              f"summary written to Build/Log/ and PLAN §10.")

    return points
