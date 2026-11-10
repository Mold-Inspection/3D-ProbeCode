# ==============================================================================
# core/expected_points_io.py — อ่าน/เขียนไฟล์ _schema.json
# ==============================================================================
# สรุปหน้าที่:
#   อ่าน/เขียนไฟล์ Schema (_schema.json) ที่เก็บจุดคาดหวังทุกจุด + ค่าตั้งตอน
#   export ใช้ประเมินผลย้อนหลังได้แม้ค่าตั้งในโปรแกรมเปลี่ยนแล้ว
#
# ไฟล์ที่เกี่ยวข้อง:
#   ใช้งานไฟล์เหล่านี้:
#     - core/gcode_generator.py — สร้าง G-code และ point map (จุดคาดหวัง) (build_point_map)
#   ถูกใช้งานโดย:
#     - core/gcode_export_panel.py — หน้าต่าง G-code Export (export_schema_json)
#     - ui/evaluation_left_panel.py — แผงซ้ายแท็บ Evaluation (โหลด log/Schema, Run inspection) (load_schema_json)
#   ไลบรารีภายนอก: datetime, json
#
# รายละเอียด:
#   หน้าที่: อ่าน/เขียนไฟล์ "Schema" (.json, "<name>_schema.json") — ไฟล์รวม
#   เดียวที่มีทั้ง expected probe touch points และ settings snapshot แบบ
#   "ครบทุกรู" (ทั้งรูที่เลือกและไม่ได้เลือกไว้ ณ ตอน export) มาจากการ export
#   ครั้งเดียวกันเสมอ — ให้ Evaluation tab โหลดกลับมาใช้เปรียบเทียบกับ .log
#   ได้ และเมื่อโหลดแล้ว core/evaluation_engine.py::apply_settings_snapshot()
#   จะถูกเรียกทันทีเพื่อ "แทนที่" (replace) การตั้งค่าปัจจุบันทั้งหมดด้วยค่าใน
#   ไฟล์นี้ — ดู ui/evaluation_left_panel.py
#
#   pure logic เท่านั้น ไม่แตะ UI — เรียกใช้ได้ทั้งจาก
#   core/gcode_export_panel.py (เขียน schema หลัง export G-code, และปุ่ม
#   standalone "Export Schema Only" ที่ไม่ต้อง export G-code เลย) และ
#   ui/evaluation_left_panel.py (ปุ่ม "Load Schema (.json)")
#
#   ตัวแปรสำคัญที่ปรับจูนได้:
#     _SCHEMA_VERSION = เลขเวอร์ชัน schema ของไฟล์ JSON — เพิ่มเลขนี้ถ้า
#                       โครงสร้างไฟล์เปลี่ยนแบบ breaking change ในอนาคต
# ==============================================================================

import json
import datetime

from core.gcode_generator import build_point_map

_SCHEMA_VERSION = 3


def export_schema_json(holes: list, view_name: str, filepath: str,
                        settings_snapshot: dict,
                        source_step_filename: str = None,
                        tolerance_mm_at_export: float = None,
                        screen_rot: int = 0,
                        origin=None, work_zero: str = None, z_trigger: bool = False,
                        probe_r: float = None, calib=None, points: list = None) -> dict:
    """คำนวณ expected points ผ่าน build_point_map() แล้วเขียนรวมกับ
    settings_snapshot (มาจาก core/evaluation_engine.py::
    build_settings_snapshot() เสมอ — ผู้เรียกเป็นคนสร้างแล้วส่งเข้ามา ไม่
    build ซ้ำในไฟล์นี้ เพื่อไม่ผูก dependency กับ evaluation_engine.py
    โดยตรง) ลงไฟล์ .json เดียว — โครงสร้างเหมือน §3 ของ PLAN_merged-
    export-record-non-destructive_v01.md ทุกประการ (แค่เปลี่ยนชื่อไฟล์/
    ฟังก์ชัน)

    Parameters
    ----------
    holes                   : list ของ HoleFeature "ต้นฉบับ" (ยังไม่ผ่าน
                               view transform) — เดียวกับที่ส่งเข้า
                               generate_gcode()/build_point_map() — ปกติ
                               คือเฉพาะรูที่ selected_for_inspection เท่านั้น
                               (จุดที่คาดหวังมีความหมายเฉพาะรูที่จะถูกโพรบ
                               จริง)
    view_name               : ชื่อมุมมองที่ใช้คำนวณ (ต้องตรงกับตอนประเมิน
                               ผลจริง — บันทึกไว้ใน metadata)
    filepath                : path ปลายทางของไฟล์ .json (ผู้เรียกเป็นคนตั้ง
                               ชื่อไฟล์ — แนะนำ "<name>_schema.json")
    settings_snapshot       : dict จาก build_settings_snapshot(ALL_holes,
                               view_name) — สำคัญ: ควรสร้างจาก "รูทั้งหมด"
                               ไม่ใช่แค่รูที่เลือกไว้ (ต่างจาก `holes`
                               พารามิเตอร์ด้านบนซึ่งเป็นแค่รูที่เลือก)
                               เพื่อให้ snapshot นี้เป็นภาพสมบูรณ์ของการ
                               ตั้งค่าทั้งโมเดล ไม่ใช่แค่ส่วนที่ถูกเลือก —
                               ดู core/evaluation_engine.py (อาจเป็น
                               dict ว่าง {'view_name': ..., 'holes': {}}
                               ถ้าผู้เรียกยังสร้าง snapshot จริงไม่ได้)
    source_step_filename    : ชื่อไฟล์ STEP ต้นฉบับ (informational เท่านั้น)
    tolerance_mm_at_export  : ค่า tolerance ที่ตั้งไว้ตอน export (informational
                               เท่านั้น — ตอนประเมินผลจริงจะใช้ tolerance จาก
                               Evaluation sidebar เสมอ ไม่ใช่ค่านี้)

    Returns
    -------
    dict : payload เดียวกันเป๊ะ ๆ กับที่เขียนลงไฟล์ — ให้ผู้เรียก (เช่น
           core/gcode_export_panel.py) เอาไปตั้งเป็น "schema ที่ใช้งานอยู่"
           ในแอปต่อได้ทันที โดยไม่ต้องเปิดไฟล์กลับมาอ่านหรือคำนวณ
           build_point_map() ซ้ำ
    """
    if points is None:   # ปกติส่ง point map ของ generate_gcode() มาเลย (ลำดับ/ค่าเดียวกันแน่นอน)
        points = build_point_map(holes, view_name, screen_rot, origin, z_trigger=z_trigger,
                                 probe_r=probe_r, calib=calib)   # + จุดพื้นก้นรู + คาลิเบรต

    payload = {
        "schema_version":         _SCHEMA_VERSION,
        "generated_at":           datetime.datetime.now().isoformat(timespec="seconds"),
        "view_name":              view_name,
        "screen_rotation":        int(screen_rot),   # — การหมุนจอตอน export
        "work_zero":              work_zero or "centroid",   # จุด X0 Y0 Z0 ของ points ชุดนี้ (core/work_zero.py)
        "work_zero_origin":       [float(c) for c in (origin if origin is not None else (0.0, 0.0, 0.0))],
        "source_step_filename":   source_step_filename,
        "tolerance_mm_at_export": tolerance_mm_at_export,
        "settings_snapshot":      settings_snapshot,
        "points":                 points,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    return payload


def load_schema_json(filepath: str) -> dict:
    """อ่านไฟล์ Schema (.json, "<name>_schema.json", schema_version 3)
    กลับมาเป็น dict เต็ม (metadata + settings_snapshot + points) — ใช้โดย
    ui/evaluation_left_panel.py::_on_load_schema(). points[] ภายในมี
    รูปแบบเดียวกับที่ build_point_map() คืนกลับมาเป๊ะ ๆ (hole_id/seg_idx/
    layer_idx/point_idx/x/y/z) — ใช้ต่อกับ core/evaluation_engine.py::
    evaluate_points() ได้ทันที; settings_snapshot มีรูปแบบเดียวกับที่
    core/evaluation_engine.py::build_settings_snapshot() คืนกลับมา (—
    รวม selected_for_inspection ต่อรูด้วย) — ใช้ต่อกับ
    apply_settings_snapshot()/diff_snapshots() ได้ทันที

    Raises
    ------
    FileNotFoundError, OSError : เปิดไฟล์ไม่ได้
    ValueError                 : ไฟล์ไม่ใช่ JSON ที่ถูกต้อง, ไม่มี key
                                  'points', หรือ schema_version ไม่ตรง
                                  (ไฟล์เก่าก่อนการเปลี่ยนแปลงนี้ — เดิม
                                  schema_version 1/2 หรือไม่มีเลย — ไม่
                                  รองรับอีกต่อไป ตามการตัดสินใจ "ไม่ทำ
                                  backward compatibility" ที่ยึดถือมาตั้งแต่
 — export ใหม่อีกครั้งเพื่อได้ไฟล์
                                  "<name>_schema.json" รูปแบบปัจจุบัน)
    """
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict) or "points" not in data:
        raise ValueError("ไฟล์ Schema JSON ไม่ถูกต้อง — ไม่มี key 'points'")

    if data.get("schema_version") != _SCHEMA_VERSION:
        raise ValueError(
            f"ไฟล์นี้เป็น schema_version {data.get('schema_version')!r} "
            f"ซึ่งไม่รองรับแล้ว (ต้องการ {_SCHEMA_VERSION}) — กรุณา export "
            f"ใหม่อีกครั้งเพื่อได้ไฟล์ '<name>_schema.json' รูปแบบปัจจุบัน")

    return data