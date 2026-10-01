# ==============================================================================
# core/axis_test.py — G-code โหมดทดสอบแกน X/Y (Axis Test / corner trace)
# ==============================================================================
# VERSION: 02
# CHANGE LOG (v01 -> v02):
#   FEATURE: Hole-center test — generate_hole_center_test_gcode() เดินไปจุด
#   ศูนย์กลางของทุกรู/ช่องที่เลือกไว้ตรวจ (zero เดียวกับ corner trace)
# หน้าที่: สร้างโปรแกรม G-code (GRBL) สั้น ๆ สำหรับเช็คว่าแกน X/Y เดินถูกทิศ
# และถูกระยะ ก่อนรันโปรแกรมโพรบจริง — ใช้กับเข็ม/analog probe หรือของทดแทน
# ที่ตั้งไว้ที่ "มุมซ้ายบน" ของชิ้นงาน แล้วกด Set Zero ใน OpenBuilds Control
# ไว้แล้ว (work zero X0 Y0 Z0 = มุมซ้ายบน ณ ผิวชิ้นงาน)
#
# ลำดับการเดิน (มองชิ้นงานแบบเดียวกับบนจอ):
#   ยก Z → มุมขวาบน → มุมขวาล่าง → มุมซ้ายล่าง → กลับมุมซ้ายบน (X0 Y0) → ลด Z0
#   หยุดค้าง (dwell) ทุกมุมให้ดูได้ว่าเข็มชี้ตรงมุมชิ้นงานจริงหรือไม่
#
# สมมติฐานทิศแกน (GRBL/เครื่องทั่วไป): X+ = ไปทางขวา, Y+ = ไปด้านหลังเครื่อง
# (= ขึ้นบนจอ) — มุม "ล่าง" จึงอยู่ที่ Y ติดลบ ถ้าเครื่องเดินสวนทาง แปลว่าทิศ
# แกนในเครื่อง (เช่น $3 direction invert) ไม่ตรงกับสมมติฐานนี้ — นั่นคือสิ่งที่
# โหมดนี้มีไว้ตรวจหา
#
# ไม่มีคำสั่ง G92 / ไม่แตะ work offset — ใช้ zero ที่ผู้ใช้ตั้งไว้ใน OpenBuilds
#
# ตัวแปรสำคัญที่ปรับจูนได้: ค่าเริ่มต้นใน AxisTestSettings ด้านล่าง
# ==============================================================================


class AxisTestSettings:
    """ค่าตั้งของโปรแกรมทดสอบแกน (ทุกค่าเป็น mm / mm/min / วินาที)"""
    def __init__(self, width_x: float, length_y: float, z_lift: float = 5.0,
                 feedrate: float = 500.0, dwell_s: float = 2.0):
        self.width_x  = float(width_x)    # ความกว้างชิ้นงานตามแกน X
        self.length_y = float(length_y)   # ความยาวชิ้นงานตามแกน Y
        self.z_lift   = float(z_lift)     # ยก Z ขึ้นก่อนเดิน (0 = ไม่ยก เดินที่ Z0)
        self.feedrate = float(feedrate)   # ความเร็วเดิน G1 ระหว่างมุม
        self.dwell_s  = float(dwell_s)    # หยุดค้างที่แต่ละมุม (0 = ไม่หยุด)

    def validate(self) -> str:
        """คืนข้อความ error (ภาษาไทย) หรือ "" ถ้าค่าถูกต้อง"""
        if self.width_x <= 0 or self.length_y <= 0:
            return "ความกว้าง/ความยาวชิ้นงานต้องมากกว่า 0"
        if self.z_lift < 0:
            return "Z Lift ต้องไม่ติดลบ"
        if self.feedrate <= 0:
            return "Feedrate ต้องมากกว่า 0"
        if self.dwell_s < 0:
            return "Dwell ต้องไม่ติดลบ"
        return ""


def axis_test_corners(settings: AxisTestSettings, zero_offset=(0.0, 0.0)) -> list:
    """มุมทั้ง 4 ตามลำดับการเดิน (ชื่อ, X, Y) — เริ่ม/จบที่มุมซ้ายบน
    zero_offset = ตำแหน่งจุด zero เทียบมุมซ้ายบน (X ขวา, Y ขึ้น) จาก
    core/work_zero.py::zero_offset_from_upper_left() — (0, 0) = zero ที่มุมซ้ายบน
    (ผลลัพธ์เหมือนเดิมทุกประการ)"""
    w, l = settings.width_x, settings.length_y
    zx, zy = zero_offset
    ul = "upper-left (zero)" if (zx, zy) == (0.0, 0.0) else "upper-left"
    return [
        (ul,            0.0 - zx, 0.0 - zy),
        ("upper-right", w - zx,   0.0 - zy),
        ("lower-right", w - zx,   -l - zy),
        ("lower-left",  0.0 - zx, -l - zy),
        (ul,            0.0 - zx, 0.0 - zy),
    ]


def generate_axis_test_gcode(settings: AxisTestSettings, view_name: str = "Top",
                             source_name: str = None, zero_offset=(0.0, 0.0),
                             zero_name: str = "UPPER-LEFT corner") -> str:
    """สร้างข้อความ G-code ทดสอบแกน X/Y — ดูคำอธิบายด้านบนไฟล์"""
    err = settings.validate()
    if err:
        raise ValueError(err)

    s = settings
    lines = [
        "; ============================================",
        "; 3D ProbeCode - AXIS TEST (corner trace)",
        f"; Object: {source_name or '(no file)'}  View: {view_name}",
        f"; Size: X {s.width_x:.3f} mm  x  Y {s.length_y:.3f} mm",
        f"; BEFORE RUNNING: put the needle at the {zero_name} of the",
        ";   object (as seen on screen) and Set Zero X/Y/Z there.",
        "; Path: upper-left -> upper-right -> lower-right -> lower-left -> upper-left",
        ";   X+ = right, Y+ = toward back of machine (up on screen).",
        "; No G92 / work-offset change: uses the zero you set.",
        "; ============================================",
        "G21 ; mm units",
        "G90 ; absolute positioning",
        "G94 ; feed rate mode: units/min",
    ]
    if s.z_lift > 0:
        lines.append(f"G0 Z{s.z_lift:.3f} ; lift needle")

    corners = axis_test_corners(s, zero_offset)
    zero_at_ul = tuple(zero_offset) == (0.0, 0.0)
    # zero อยู่ที่มุมซ้ายบน: เริ่มที่มุมนั้นอยู่แล้ว (เหมือนเดิม) — zero อยู่จุดอื่น: เดินไปมุมซ้ายบนก่อน
    for i, (name, x, y) in enumerate(corners if not zero_at_ul else corners[1:]):
        lines.append(f"G1 X{x:.3f} Y{y:.3f} F{s.feedrate:.0f} ; -> {name}")
        last = (i == len(corners) - 1) if not zero_at_ul else (name == corners[-1][0])
        if s.dwell_s > 0 and not last:
            lines.append(f"G4 P{s.dwell_s:.1f} ; check needle is on the {name} corner")
    if not zero_at_ul:
        lines.append(f"G1 X0.000 Y0.000 F{s.feedrate:.0f} ; -> back to zero ({zero_name})")

    if s.z_lift > 0:
        lines.append(f"G1 Z0.000 F{min(s.feedrate, 200.0):.0f} ; lower back to set-zero point")
    lines.append("M30 ; program end")
    return "\n".join(lines) + "\n"


# ==============================================================================
# v02: Hole-center test — เดินไปจุดศูนย์กลางของทุกรู/ช่องที่เลือกไว้ตรวจ
# ==============================================================================
def hole_centers_from_view(holes, view_x, view_y, zero_offset=(0.0, 0.0)) -> list:
    """แปลงตำแหน่งรู (พิกัดจอ h.x/h.y) เป็นพิกัดเทียบ zero ที่มุมซ้ายบนของ
    ชิ้นงาน — view_x/view_y คือพิกัดจอของ vertex ทั้งชิ้นงาน (app.current_x/y)
    คืน list ของ (ชื่อ, X, Y) เฉพาะรูที่ selected_for_inspection และมีตำแหน่ง"""
    x0, y0 = float(min(view_x)), float(max(view_y))   # มุมซ้ายบนบนจอ
    x0, y0 = x0 + zero_offset[0], y0 + zero_offset[1]   # เลื่อนไปจุด zero ที่เลือก (core/work_zero.py)
    out = []
    for h in holes:
        if not getattr(h, 'selected_for_inspection', False) or h.x is None or h.y is None:
            continue
        sh = getattr(h, '_step_hole', None)
        kind = sh.size_text() if sh is not None and hasattr(sh, 'size_text') else f"⌀{h.radius * 2:.2f}"
        out.append((f"hole {h.display_id} ({kind})", float(h.x) - x0, float(h.y) - y0))
    return out


def order_from_zero(points: list) -> list:
    """เรียงจุดแบบ nearest-neighbor เริ่มจากจุด zero (0, 0) — ระยะเดินสั้น"""
    remaining, ordered, cur = list(points), [], (0.0, 0.0)
    while remaining:
        nxt = min(remaining, key=lambda p: (p[1] - cur[0]) ** 2 + (p[2] - cur[1]) ** 2)
        remaining.remove(nxt)
        ordered.append(nxt)
        cur = (nxt[1], nxt[2])
    return ordered


def generate_hole_center_test_gcode(settings: AxisTestSettings, centers: list,
                                    view_name: str = "Top", source_name: str = None,
                                    zero_name: str = "UPPER-LEFT corner") -> str:
    """G-code เดินไปจุดศูนย์กลางรูทีละรู (ยก Z ไว้ตลอด) หยุดค้างให้ดูว่าเข็ม
    ชี้ตรงกลางรูจริงหรือไม่ แล้วกลับ zero — centers จาก hole_centers_from_view()"""
    err = settings.validate()
    if err:
        raise ValueError(err)
    if not centers:
        raise ValueError("ไม่มีรูที่เลือกไว้สำหรับตรวจ")

    s = settings
    ordered = order_from_zero(centers)
    lines = [
        "; ============================================",
        "; 3D ProbeCode - HOLE CENTER TEST",
        f"; Object: {source_name or '(no file)'}  View: {view_name}",
        f"; Size: X {s.width_x:.3f} mm  x  Y {s.length_y:.3f} mm   Holes: {len(ordered)}",
        f"; BEFORE RUNNING: put the needle at the {zero_name} of the",
        ";   object (as seen on screen) and Set Zero X/Y/Z there.",
        "; Visits the center of every hole selected for inspection, then",
        ";   returns to the zero point. Needle stays lifted the whole time.",
        ";   X+ = right, Y+ = toward back of machine (up on screen).",
        "; No G92 / work-offset change: uses the zero you set.",
        "; ============================================",
        "G21 ; mm units",
        "G90 ; absolute positioning",
        "G94 ; feed rate mode: units/min",
    ]
    if s.z_lift > 0:
        lines.append(f"G0 Z{s.z_lift:.3f} ; lift needle")
    for i, (name, x, y) in enumerate(ordered, start=1):
        lines.append(f"G1 X{x:.3f} Y{y:.3f} F{s.feedrate:.0f} ; -> {i}/{len(ordered)} {name} center")
        if s.dwell_s > 0:
            lines.append(f"G4 P{s.dwell_s:.1f} ; check needle is over the center of {name}")
    lines.append(f"G1 X0.000 Y0.000 F{s.feedrate:.0f} ; -> {zero_name.lower().replace(' corner', '')} (zero)")
    if s.z_lift > 0:
        lines.append(f"G1 Z0.000 F{min(s.feedrate, 200.0):.0f} ; lower back to set-zero point")
    lines.append("M30 ; program end")
    return "\n".join(lines) + "\n"
