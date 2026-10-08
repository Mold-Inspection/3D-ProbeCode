# ==============================================================================
# core/probe_test.py — G-code ทดสอบหัวโพรบ (Probe Test) ทีละทิศ
# ==============================================================================
# VERSION: 02
# CHANGE LOG (v01 -> v02):
#   FEATURE: return_to_zero — หลังแตะแล้วกลับจุด Set Zero (เดินกลับเฉพาะแกนที่โพรบ)
#   ต้อง Set Zero ที่จุดเริ่มก่อนรัน; ปิดได้ = แบบเดิม (ถอยออกแล้วหยุดอยู่ตรงนั้น)
# หน้าที่: สร้างโปรแกรม G-code (GRBL) สั้น ๆ ที่สั่ง G38.2 เดินไปทิศเดียว
# (X+, X-, Y+, Y-, Z-) เป็นระยะ distance mm — ไว้เช็คว่าเครื่องรับสัญญาณ
# จากหัวโพรบจริงหรือไม่ ก่อนรันโปรแกรมวัดจริง แยกไฟล์ละ 1 ทิศ
#
# ผลที่ควรเห็นใน OpenBuilds Control:
#   แตะก้านโพรบ (หรือให้วิ่งชนชิ้นงาน) ระหว่างเดิน → เครื่องหยุดทันที +
#   ข้อความ [PRB:x,y,z:1] แล้วถอยออก back-off mm = โพรบทำงาน
#   เดินจนสุดระยะโดยไม่หยุด → ALARM:5 (probe fail) = เครื่องไม่ได้รับสัญญาณ
#   ALARM:4 ตั้งแต่เริ่ม = สัญญาณโพรบค้างอยู่ก่อนเดิน (สายหลุด/NC กลับขั้ว)
#
# ใช้พิกัดแบบสัมพัทธ์ (G91) — เดินจากตำแหน่งปัจจุบัน; ถ้า return_to_zero ต้อง Set Zero
# ที่จุดเริ่มก่อน (G38.2 หยุดตรงไหนไม่รู้ล่วงหน้า จึงกลับได้ด้วยพิกัด zero เท่านั้น)
# ไม่มี Z+ เพราะโพรบไม่แตะอะไรจากด้านล่าง
#
# ตัวแปรสำคัญที่ปรับจูนได้: ค่าเริ่มต้นใน ProbeTestSettings ด้านล่าง
# ==============================================================================

# (ชื่อทิศ, แกน, เครื่องหมาย) — ลำดับที่แสดงในหน้าต่าง
DIRECTIONS = [
    ("X+", "X", 1),
    ("X-", "X", -1),
    ("Y+", "Y", 1),
    ("Y-", "Y", -1),
    ("Z-", "Z", -1),
]

_DIR_TEXT = {
    "X+": "toward X+ (right)",
    "X-": "toward X- (left)",
    "Y+": "toward Y+ (back of machine)",
    "Y-": "toward Y- (front of machine)",
    "Z-": "down (Z-)",
}


class ProbeTestSettings:
    """ค่าตั้งของโปรแกรมทดสอบโพรบ (mm / mm/min)"""
    def __init__(self, distance: float = 12.0, feedrate: float = 100.0, backoff: float = 2.0,
                 return_to_zero: bool = True):
        self.distance = float(distance)   # ระยะเดินสูงสุดของ G38.2
        self.feedrate = float(feedrate)   # ความเร็วเดินขณะรอสัมผัส
        self.backoff  = float(backoff)    # ถอยออกหลังแตะ (0 = ไม่ถอย)
        self.return_to_zero = bool(return_to_zero)   # กลับจุด Set Zero หลังแตะ

    def validate(self) -> str:
        """คืนข้อความ error (ภาษาไทย) หรือ "" ถ้าค่าถูกต้อง"""
        if self.distance <= 0:
            return "ระยะเดินต้องมากกว่า 0"
        if self.feedrate <= 0:
            return "Feedrate ต้องมากกว่า 0"
        if self.backoff < 0:
            return "Back-off ต้องไม่ติดลบ"
        if self.backoff > self.distance:
            return "Back-off ต้องไม่มากกว่าระยะเดิน"
        return ""


def generate_probe_test_gcode(settings: ProbeTestSettings, direction: str) -> str:
    """G-code ทดสอบโพรบ 1 ทิศ — direction เป็นชื่อใน DIRECTIONS (เช่น "X+")"""
    err = settings.validate()
    if err:
        raise ValueError(err)
    axis, sign = next((a, s) for name, a, s in DIRECTIONS if name == direction)

    s = settings
    lines = [
        "; ============================================",
        f"; 3D ProbeCode - PROBE TEST {direction}",
        f"; Moves {_DIR_TEXT[direction]} up to {s.distance:.3f} mm from the CURRENT",
        ";   position and stops as soon as the probe triggers (G38.2).",
        "; BEFORE RUNNING: jog the probe so it has at least",
        f";   {s.distance:g} mm of free space {_DIR_TEXT[direction]}.",
        ";   Touch the stylus by hand while it moves (or let it hit a part).",
        "; RESULT:",
        ";   stops + [PRB:x,y,z:1] in the console -> probe signal OK",
        ";   runs the full distance, ALARM:5        -> no probe signal",
        ";   ALARM:4 right at the start             -> probe already triggered",
        ";   (clear an alarm with $X)",
    ] + ([
        "; START: Set Zero X/Y/Z at the start point first -- after contact",
        f";   the probe returns along {axis} to {axis}0 (the start point).",
    ] if s.return_to_zero else [
        "; Relative moves (G91): no Set Zero needed. The probe stays",
        ";   where it stopped (after the back-off).",
    ]) + [
        "; ============================================",
        "G21 ; mm units",
        "G94 ; feed rate mode: units/min",
        "G91 ; relative positioning",
        f"G38.2 {axis}{sign * s.distance:.3f} F{s.feedrate:.0f} ; probe {direction}, stop on contact",
    ]
    if s.backoff > 0:
        lines.append(f"G0 {axis}{-sign * s.backoff:.3f} ; back off from the contact")
    lines.append("G90 ; back to absolute positioning")
    if s.return_to_zero:   # กลับเฉพาะแกนที่โพรบ = ย้อนเส้นทางเดิม
        lines.append(f"G0 {axis}0.000 ; return to the start point (Set Zero)")
    lines.append("M30 ; program end")
    return "\n".join(lines) + "\n"
