# ==============================================================================
# core/user_settings.py — จำค่าตั้งของผู้ใช้ข้ามการเปิดโปรแกรม
# ==============================================================================
# VERSION: 01
# หน้าที่: เก็บค่าที่ผู้ใช้ตั้งไว้ (แบบเดียวกับ "cookie" ของเว็บ แต่เป็นไฟล์ในเครื่อง)
# ไว้ที่ %APPDATA%\3D ProbeCode\settings.json แล้วโหลดกลับตอนเปิดโปรแกรมครั้งถัดไป
#
# หมวดที่เก็บ (key บนสุดของไฟล์ JSON):
#   work_zero   — จุด X0 Y0 Z0 ที่เลือก (core/work_zero.py)
#   appearance  — "Light" / "Dark"
#   probe       — Hardware Setting → Probe Stylus
#   machine     — Hardware Setting → Machine Working Area
#   export      — G-code Export → Export Settings (ยกเว้น Safe Z ซึ่งขึ้นกับชิ้นงาน)
#   axis_test   — G-code Export → Axis Test (ยกเว้นขนาดชิ้นงาน ซึ่งขึ้นกับชิ้นงาน)
#
# อ่าน/เขียนไม่สำเร็จ (ไฟล์เสีย, ไม่มีสิทธิ์เขียน) จะไม่ทำให้โปรแกรมล้ม — ใช้ค่าเริ่มต้นแทน
# ==============================================================================
import json
import os

_DIR  = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "3D ProbeCode")
PATH  = os.path.join(_DIR, "settings.json")


def load() -> dict:
    try:
        with open(PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def get(section: str, default=None):
    return load().get(section, default)


def save_section(section: str, value) -> None:
    """แทนที่หมวด `section` ด้วย `value` แล้วเขียนไฟล์ (หมวดอื่นคงเดิม)"""
    data = load()
    data[section] = value
    try:
        os.makedirs(_DIR, exist_ok=True)
        tmp = PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, PATH)   # เขียนทับแบบ atomic — ไฟล์ไม่เสียถ้าโปรแกรมปิดกลางคัน
    except Exception as e:
        print(f"[user_settings] could not save '{section}': {e!r}")


def apply_numbers(obj, values, fields, allow_zero=()) -> None:
    """ตั้งค่า attribute ตัวเลขของ obj จาก dict ที่โหลดมา — ข้ามค่าที่หายไป/ผิดรูปแบบ/ไม่เป็นบวก
    (ชื่อใน allow_zero ยอมให้เป็น 0 ได้)"""
    if not isinstance(values, dict):
        return
    for name in fields:
        try:
            v = float(values[name])
        except (KeyError, TypeError, ValueError):
            continue
        if v > 0 or (v == 0 and name in allow_zero):
            setattr(obj, name, v)
