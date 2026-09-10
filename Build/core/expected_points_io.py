# core/expected_points_io.py
# VERSION: 01
# หน้าที่: อ่าน/เขียนไฟล์ "Expected Points" (.json) — รายการจุดที่คาดหวังว่า
# จะถูกโพรบสัมผัส (expected probe touch points) แบบพกพา (portable) แยกออก
# จากขั้นตอน export G-code โดยสิ้นเชิง — ให้ Evaluation tab โหลดจุดคาดหวัง
# ชุดเดิม ๆ กลับมาใช้ได้โดยไม่ต้องมีไฟล์ STEP/hole config เดิมอยู่ในโปรแกรม
# ตรงกับ session ที่ export ไว้
# (ดู PLAN_evaluation-expected-points-json-and-offset-only_v01.md §4.1)
#
# pure logic เท่านั้น ไม่แตะ UI — เรียกใช้ได้ทั้งจาก
# core/gcode_export_panel.py (เขียน sidecar อัตโนมัติหลัง export G-code, และ
# ปุ่ม standalone "Export Expected Points Only" ที่ไม่ต้อง export G-code เลย)
# และ ui/evaluation_left_panel.py (ปุ่ม "Load Expected Points (.json)")
#
# ตัวแปรสำคัญที่ปรับจูนได้:
#   _SCHEMA_VERSION = เลขเวอร์ชัน schema ของไฟล์ JSON — เพิ่มเลขนี้ถ้าโครงสร้าง
#                     points[] เปลี่ยนแบบ breaking change ในอนาคต
# ==============================================================================
import json
import datetime

from core.gcode_generator import build_point_map

_SCHEMA_VERSION = 1


def export_expected_points_json(holes: list, view_name: str, filepath: str,
                                  source_step_filename: str = None,
                                  tolerance_mm_at_export: float = None) -> None:
    """คำนวณ expected points ผ่าน build_point_map() (ตัวเดียวกับที่
    generate_gcode() ใช้ — ไม่ต้องพึ่ง GCodeSettings เลย เพราะ build_point_map()
    ไม่เคยรับพารามิเตอร์นั้นตั้งแต่แรก) แล้วเขียนลงไฟล์ .json แบบพกพา

    Parameters
    ----------
    holes                   : list ของ HoleFeature "ต้นฉบับ" (ยังไม่ผ่าน view
                               transform) — เดียวกับที่ส่งเข้า
                               generate_gcode()/build_point_map()
    view_name               : ชื่อมุมมองที่ใช้คำนวณ (ต้องตรงกับตอนประเมินผลจริง
                               — บันทึกไว้ใน metadata เพื่อให้ตรวจสอบย้อนหลังได้)
    filepath                : path ปลายทางของไฟล์ .json
    source_step_filename    : ชื่อไฟล์ STEP ต้นฉบับ (informational เท่านั้น)
    tolerance_mm_at_export  : ค่า tolerance ที่ตั้งไว้ตอน export (informational
                               เท่านั้น — ตอนประเมินผลจริงจะใช้ tolerance จาก
                               Evaluation sidebar เสมอ ไม่ใช่ค่านี้)
    """
    points = build_point_map(holes, view_name)

    payload = {
        "schema_version":         _SCHEMA_VERSION,
        "generated_at":           datetime.datetime.now().isoformat(timespec="seconds"),
        "view_name":              view_name,
        "source_step_filename":   source_step_filename,
        "tolerance_mm_at_export": tolerance_mm_at_export,
        "points":                 points,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def load_expected_points_json(filepath: str) -> list:
    """อ่านไฟล์ Expected Points .json กลับมาเป็น list ของ dict รูปแบบเดียวกับ
    ที่ build_point_map() คืนกลับมาเป๊ะ ๆ (hole_id/seg_idx/layer_idx/
    point_idx/x/y/z) — ใช้ต่อกับ core/evaluation_engine.py::evaluate_points()
    ได้ทันทีโดยไม่ต้องแปลงรูปแบบเพิ่ม

    Raises
    ------
    FileNotFoundError, OSError : เปิดไฟล์ไม่ได้
    ValueError                 : ไฟล์ไม่ใช่ JSON ที่ถูกต้อง หรือไม่มี key 'points'
    """
    return load_expected_points_json_full(filepath)["points"]


def load_expected_points_json_full(filepath: str) -> dict:
    """เหมือน load_expected_points_json() แต่คืน dict เต็ม (รวม metadata:
    view_name, source_step_filename, generated_at, tolerance_mm_at_export
    ฯลฯ) — ใช้เมื่อ UI ต้องการแสดงข้อมูลเสริมเกี่ยวกับไฟล์ที่โหลด ไม่ใช่แค่
    points[] อย่างเดียว (ดู ui/evaluation_left_panel.py::
    _on_load_expected_points_json())"""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict) or "points" not in data:
        raise ValueError("Expected Points JSON ไม่ถูกต้อง — ไม่มี key 'points'")

    return data
