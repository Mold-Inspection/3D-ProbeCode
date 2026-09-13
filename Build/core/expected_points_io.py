# core/expected_points_io.py
# VERSION: 04
# CHANGE LOG (v03 -> v04):
#   FEATURE (user request — "after exporting G-code, the schema should
#   be auto-loaded as the active one, without the user picking it by
#   hand"): export_schema_json() now RETURNS the full `payload` dict it
#   just wrote to disk (previously returned None implicitly). This lets
#   core/gcode_export_panel.py v10 hand that exact dict straight to the
#   app's "active schema" state right after writing it, without having
#   to re-read the file back from disk or recompute build_point_map()
#   a second time. Purely additive — every existing caller that ignored
#   the return value still works unchanged.
#
# CHANGE LOG (v02 -> v03):
#   FEATURE (user request, follow-up to
#   PLAN_merged-export-record-non-destructive_v01.md): renamed the whole
#   concept from "Export Record" to "Schema" and the on-disk filename
#   convention from "<name>.export.json" to "<name>_schema.json" (the
#   actual filename is still chosen by the caller —
#   core/gcode_export_panel.py v09 — this module only renamed its own
#   function names/wording to match):
#     - export_combined_record_json() -> export_schema_json() (same
#       parameters/behavior, writes the same JSON structure — see §3 of
#       the plan doc for the structure, unchanged here)
#     - load_combined_record_json() -> load_schema_json()
#   FEATURE: bumped _SCHEMA_VERSION 2 -> 3. This is a real breaking
#   change in what 'settings_snapshot' is expected to contain — see
#   core/evaluation_engine.py v04's changelog: build_settings_snapshot()
#   now records `selected_for_inspection` per hole and callers now pass
#   ALL current holes (not just the selected ones) when building it, so
#   a v2 file's settings_snapshot is missing the hole-selection
#   information entirely and would silently under-restore if loaded
#   with the new v04 apply_settings_snapshot(full_replace=True) — a
#   hard version check here prevents that silent bad-restore rather than
#   accepting a stale/incomplete snapshot. Old "<name>.export.json"
#   (schema_version 2) and any earlier sidecar files are no longer
#   loadable — same "no backward compatibility, pre-release project"
#   decision already made in v01 -> v02 (plan §6, decision (b)) — export
#   again to get a current "<name>_schema.json" file.
#
# หน้าที่: อ่าน/เขียนไฟล์ "Schema" (.json, "<name>_schema.json") — ไฟล์รวม
# เดียวที่มีทั้ง expected probe touch points และ settings snapshot แบบ
# "ครบทุกรู" (ทั้งรูที่เลือกและไม่ได้เลือกไว้ ณ ตอน export) มาจากการ export
# ครั้งเดียวกันเสมอ — ให้ Evaluation tab โหลดกลับมาใช้เปรียบเทียบกับ .log
# ได้ และเมื่อโหลดแล้ว core/evaluation_engine.py::apply_settings_snapshot()
# จะถูกเรียกทันทีเพื่อ "แทนที่" (replace) การตั้งค่าปัจจุบันทั้งหมดด้วยค่าใน
# ไฟล์นี้ — ดู ui/evaluation_left_panel.py v07
#
# pure logic เท่านั้น ไม่แตะ UI — เรียกใช้ได้ทั้งจาก
# core/gcode_export_panel.py (เขียน schema หลัง export G-code, และปุ่ม
# standalone "Export Schema Only" ที่ไม่ต้อง export G-code เลย) และ
# ui/evaluation_left_panel.py (ปุ่ม "Load Schema (.json)")
#
# ตัวแปรสำคัญที่ปรับจูนได้:
#   _SCHEMA_VERSION = เลขเวอร์ชัน schema ของไฟล์ JSON — เพิ่มเลขนี้ถ้า
#                     โครงสร้างไฟล์เปลี่ยนแบบ breaking change ในอนาคต
# ==============================================================================
import json
import datetime

from core.gcode_generator import build_point_map

_SCHEMA_VERSION = 3


def export_schema_json(holes: list, view_name: str, filepath: str,
                        settings_snapshot: dict,
                        source_step_filename: str = None,
                        tolerance_mm_at_export: float = None) -> dict:
    """คำนวณ expected points ผ่าน build_point_map() แล้วเขียนรวมกับ
    settings_snapshot (มาจาก core/evaluation_engine.py::
    build_settings_snapshot() เสมอ — ผู้เรียกเป็นคนสร้างแล้วส่งเข้ามา ไม่
    build ซ้ำในไฟล์นี้ เพื่อไม่ผูก dependency กับ evaluation_engine.py
    โดยตรง) ลงไฟล์ .json เดียว — โครงสร้างเหมือน §3 ของ PLAN_merged-
    export-record-non-destructive_v01.md ทุกประการ (แค่เปลี่ยนชื่อไฟล์/
    ฟังก์ชัน — ดู CHANGE LOG ด้านบน)

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
                               ดู core/evaluation_engine.py v04 (อาจเป็น
                               dict ว่าง {'view_name': ..., 'holes': {}}
                               ถ้าผู้เรียกยังสร้าง snapshot จริงไม่ได้)
    source_step_filename    : ชื่อไฟล์ STEP ต้นฉบับ (informational เท่านั้น)
    tolerance_mm_at_export  : ค่า tolerance ที่ตั้งไว้ตอน export (informational
                               เท่านั้น — ตอนประเมินผลจริงจะใช้ tolerance จาก
                               Evaluation sidebar เสมอ ไม่ใช่ค่านี้)

    Returns
    -------
    dict : payload เดียวกันเป๊ะ ๆ กับที่เขียนลงไฟล์ (v04) — ให้ผู้เรียก (เช่น
           core/gcode_export_panel.py) เอาไปตั้งเป็น "schema ที่ใช้งานอยู่"
           ในแอปต่อได้ทันที โดยไม่ต้องเปิดไฟล์กลับมาอ่านหรือคำนวณ
           build_point_map() ซ้ำ
    """
    points = build_point_map(holes, view_name)

    payload = {
        "schema_version":         _SCHEMA_VERSION,
        "generated_at":           datetime.datetime.now().isoformat(timespec="seconds"),
        "view_name":              view_name,
        "source_step_filename":   source_step_filename,
        "tolerance_mm_at_export": tolerance_mm_at_export,
        "settings_snapshot":      settings_snapshot,
        "points":                 points,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    return payload   # v04


def load_schema_json(filepath: str) -> dict:
    """อ่านไฟล์ Schema (.json, "<name>_schema.json", schema_version 3)
    กลับมาเป็น dict เต็ม (metadata + settings_snapshot + points) — ใช้โดย
    ui/evaluation_left_panel.py::_on_load_schema(). points[] ภายในมี
    รูปแบบเดียวกับที่ build_point_map() คืนกลับมาเป๊ะ ๆ (hole_id/seg_idx/
    layer_idx/point_idx/x/y/z) — ใช้ต่อกับ core/evaluation_engine.py::
    evaluate_points() ได้ทันที; settings_snapshot มีรูปแบบเดียวกับที่
    core/evaluation_engine.py::build_settings_snapshot() คืนกลับมา (v04 —
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
                                  v02 — export ใหม่อีกครั้งเพื่อได้ไฟล์
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