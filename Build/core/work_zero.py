# ==============================================================================
# core/work_zero.py — ตำแหน่ง Work Zero (X0 Y0 Z0) ของ G-code
# ==============================================================================
# VERSION: 01
# หน้าที่: ให้ผู้ใช้เลือกได้ว่าจุด zero ของโปรแกรม G-code อยู่ตรงไหนของชิ้นงาน
# (ตั้งค่าที่ G-code Export → Export Settings → "Work zero") แล้วคำนวณ
# "origin" = ตำแหน่งของจุดนั้นในพิกัดเครื่อง (machining frame) เพื่อนำไปลบออก
# จากพิกัดทุกจุดก่อนเขียน G-code / expected points ของ Schema
#
# ตัวเลือก (ซ้าย/ขวา/บน/ล่าง = ตามที่เห็นบนจอ, X+ = ขวา, Y+ = ขึ้นบนจอ):
#   centroid     — จุดศูนย์กลางมวลของ mesh (ค่าเริ่มต้น = พฤติกรรมเดิมทุกประการ)
#   center       — กึ่งกลางกรอบชิ้นงาน (bounding box), Z0 = ผิวบนสุด
#   upper_left / upper_right / lower_left / lower_right
#                — มุมของกรอบชิ้นงาน, Z0 = ผิวบนสุด
# ("ผิวบนสุด" = ด้านที่หันเข้าหาหัวโพรบในมุมมองที่ใช้ export)
#
# พิกัดเครื่อง = พิกัดโมเดล (ย้ายจุดศูนย์กลางมวลไป 0,0,0 แล้วใน cad_loader)
# หมุนด้วย core/projector.py::view_rotation_matrix — เมทริกซ์เดียวกับ
# core/gcode_generator.py::apply_view_transform() และกับจอ
# ==============================================================================
import numpy as np

DEFAULT_WORK_ZERO = "centroid"

# (key, ข้อความในเมนู) — ลำดับที่แสดงในเมนู
WORK_ZERO_CHOICES = [
    ("centroid",    "Mesh centroid (default)"),
    ("center",      "Center of object"),
    ("upper_left",  "Upper-left corner"),
    ("upper_right", "Upper-right corner"),
    ("lower_left",  "Lower-left corner"),
    ("lower_right", "Lower-right corner"),
]

_POINT_TEXT = {
    "center":      "the CENTER of the object",
    "upper_left":  "the UPPER-LEFT corner of the object",
    "upper_right": "the UPPER-RIGHT corner of the object",
    "lower_left":  "the LOWER-LEFT corner of the object",
    "lower_right": "the LOWER-RIGHT corner of the object",
}


def label_of(mode: str) -> str:
    return dict(WORK_ZERO_CHOICES).get(mode, dict(WORK_ZERO_CHOICES)[DEFAULT_WORK_ZERO])


def mode_of_label(label: str) -> str:
    for key, text in WORK_ZERO_CHOICES:
        if text == label:
            return key
    return DEFAULT_WORK_ZERO


def zero_view_text(app) -> str:
    """มุมมอง + การหมุนจอปัจจุบันของแอป เช่น "Top view, rotated 90°" — ซ้าย/ขวา/บน/ล่าง
    ของจุด zero คิดตามมุมมองนี้เสมอ"""
    rot = getattr(app, 'screen_rotation', 0)
    return f"{getattr(app, 'current_view', 'Top')} view" + (f", rotated {rot}\u00b0" if rot else "")


def zero_hint_text(app) -> str:
    """คำอธิบายใต้ตัวเลือก Work zero (Hardware Setting)"""
    mode = getattr(app, 'work_zero', DEFAULT_WORK_ZERO)
    if mode not in _POINT_TEXT:
        return ("Coordinates are measured from the mesh centroid (as before). "
                "That point can't be touched off on the machine — choose the "
                "center or a corner if you set zero by hand.")
    return (f"Before running, Set Zero X/Y/Z on the machine at {describe(mode)} — "
            f"in the current {zero_view_text(app)}, shown by the X0 Y0 mark on the "
            "Selection and Customization views. Used by the probe G-code, the "
            "schema and both test programs.")


def describe(mode: str) -> str:
    """คำอธิบายสั้น ๆ ภาษาอังกฤษของจุด zero (ใช้ใน UI และหัวไฟล์ G-code)"""
    if mode not in _POINT_TEXT:
        return "the mesh centroid (center of mass) — not a point you can touch off on the machine"
    return f"{_POINT_TEXT[mode]} (as seen on screen), Z0 on the top surface"


def object_bounds(mesh, view_name: str, screen_rot: int = 0):
    """(min_xyz, max_xyz) ของชิ้นงานในพิกัดเครื่องของมุมมองนี้"""
    from core.projector import view_rotation_matrix
    rot = view_rotation_matrix(view_name, screen_rot)
    verts = np.asarray(mesh.vertices, dtype=float) @ rot.T
    return verts.min(axis=0), verts.max(axis=0)


def work_zero_origin(mesh, view_name: str, screen_rot: int = 0,
                     mode: str = DEFAULT_WORK_ZERO) -> np.ndarray:
    """ตำแหน่งของจุด zero ในพิกัดเครื่อง — ลบค่านี้ออกจากทุกพิกัดก่อนเขียน G-code
    คืน (0, 0, 0) สำหรับ 'centroid' (= พฤติกรรมเดิม) หรือถ้ายังไม่มี mesh"""
    if mode not in _POINT_TEXT or mesh is None:
        return np.zeros(3)
    lo, hi = object_bounds(mesh, view_name, screen_rot)
    mid = (lo + hi) / 2.0
    x = {"center": mid[0], "upper_left": lo[0], "lower_left": lo[0],
         "upper_right": hi[0], "lower_right": hi[0]}[mode]
    y = {"center": mid[1], "upper_left": hi[1], "upper_right": hi[1],
         "lower_left": lo[1], "lower_right": lo[1]}[mode]
    return np.array([x, y, hi[2]], dtype=float)


def zero_offset_from_upper_left(mode: str, width_x: float, length_y: float):
    """ตำแหน่งจุด zero เทียบกับมุมซ้ายบนของชิ้นงาน (X ขวา, Y ขึ้น) — ใช้กับ
    G-code ทดสอบแกน (core/axis_test.py) ซึ่งอิงมุมซ้ายบน
    'centroid' ไม่ใช่จุดที่ตั้งบนเครื่องได้ → โปรแกรมทดสอบใช้มุมซ้ายบนแทน (เหมือนเดิม)"""
    return {
        "center":      (width_x / 2.0, -length_y / 2.0),
        "upper_right": (width_x, 0.0),
        "lower_left":  (0.0, -length_y),
        "lower_right": (width_x, -length_y),
    }.get(mode, (0.0, 0.0))


def test_zero_name(mode: str) -> str:
    """ชื่อจุด zero ที่ใช้ในข้อความของ G-code ทดสอบแกน (core/axis_test.py)
    'centroid' ตั้งบนเครื่องไม่ได้ → โปรแกรมทดสอบใช้มุมซ้ายบน (เหมือนเดิม)"""
    return {
        "center":      "CENTER",
        "upper_right": "UPPER-RIGHT corner",
        "lower_left":  "LOWER-LEFT corner",
        "lower_right": "LOWER-RIGHT corner",
    }.get(mode, "UPPER-LEFT corner")


def zero_in_view(mesh, view_name: str, screen_rot: int = 0,
                 mode: str = DEFAULT_WORK_ZERO):
    """ตำแหน่งจุด Work zero ในพิกัดของกราฟบนจอ (ตามมุมมอง + การหมุนจอปัจจุบัน)
    คืน (x, y, depth):
      x, y  — เทียบจุดกึ่งกลางกรอบชิ้นงาน = พิกัดเดียวกับกราฟแท็บ Selection
              (core/projector.py) และแกน X/Y ของกราฟ 3D แท็บ Customization
      depth — ระยะลึกจากผิวบนสุดลงไป = แกน Z ของกราฟ 3D แท็บ Customization
              (0 = ผิวบน ซึ่งเป็น Z0 ของทุกตัวเลือกยกเว้น centroid)"""
    lo, hi = object_bounds(mesh, view_name, screen_rot)
    org = work_zero_origin(mesh, view_name, screen_rot, mode)
    mid = (lo + hi) / 2.0
    return float(org[0] - mid[0]), float(org[1] - mid[1]), float(hi[2] - org[2])
