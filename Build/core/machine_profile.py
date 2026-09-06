# ==============================================================================
# core/machine_profile.py — ขนาดพื้นที่ทำงานจริงของเครื่อง CNC (physical
# machine travel / work area) — ส่วนหนึ่งของ "Hardware Setting" ใน sidebar ซ้าย
# ==============================================================================
# VERSION: 02
# CHANGE LOG (v01 -> v02):
#   FEATURE (PLAN_machine-z-height-and-padding-calculation.md, Step 2):
#   added `z_height` — the fixed physical distance from the floor to the
#   underside of the Z-axis carriage, measured with the Z-axis at its home
#   / fully-retracted (top of stroke) position. Unlike `x_travel`/
#   `y_travel`/`z_travel` (still reference/display only — see note below),
#   `z_height` is the FIRST field in this class that actually feeds a real
#   calculation: core/gcode_generator.py v06's suggest_padding_height()
#   uses it together with core/probe_profile.py's `stylus_holder_height` +
#   `stylus_length` and this class's own `z_travel` to compute how much
#   riser/padding height a workpiece needs so the probe tip can physically
#   reach it within the machine's downward Z travel range. See the PLAN
#   doc for the full formula derivation and confirmed measurement point.
# ==============================================================================
# หน้าที่: เก็บระยะเดินสูงสุดของแต่ละแกน (X/Y/Z, mm) ตามสเปกเครื่องจริง
# บวกความสูงจากพื้นถึงใต้ก้นแกน Z (z_height) ซึ่งเป็นค่าที่ใช้จริงในการคำนวณ
# padding ใต้ชิ้นงาน (ดู core/gcode_generator.py::suggest_padding_height())
# — ส่วน x_travel/y_travel/z_travel ยังคง "เก็บและแสดงผล" เท่านั้น (ยังไม่
# ผูกกับการตรวจสอบ/บล็อกใด ๆ — ดู PLAN probe-safety Phase 1–3 ใน memory)
#
# ตัวแปรสำคัญที่ปรับจูนได้:
#   x_travel / y_travel / z_travel = ระยะเดินสูงสุดแต่ละแกน (mm) — ปรับตามสเปกเครื่อง
#   z_height = ความสูงจากพื้นถึงใต้ก้นแกน Z ตอน Z อยู่ตำแหน่ง home/สุดบน (mm) — v02
#              ใช้คำนวณ padding ใต้ชิ้นงานจริง — ปรับตามสเปกเครื่อง
#   DEFAULT_X / DEFAULT_Y / DEFAULT_Z = ค่าเริ่มต้นเมื่อกด "Reset to Default"
#   DEFAULT_Z_HEIGHT = ค่าเริ่มต้นของ z_height เมื่อกด "Reset to Default" — v02
# ==============================================================================
from dataclasses import dataclass, field
 
@dataclass
class MachineProfile:
    x_travel: float = 300.0   # mm — ระยะเดินสูงสุดแกน X ปรับได้
    y_travel: float = 300.0   # mm — ระยะเดินสูงสุดแกน Y ปรับได้
    z_travel: float = 100.0   # mm — ระยะเดินสูงสุดแกน Z ปรับได้
    z_height: float = 150.0   # mm — ความสูงพื้นถึงใต้ก้นแกน Z (Z ที่ home) ปรับได้ (v02)
 
    DEFAULT_X: float = field(default=300.0, init=False, repr=False)
    DEFAULT_Y: float = field(default=300.0, init=False, repr=False)
    DEFAULT_Z: float = field(default=100.0, init=False, repr=False)
    DEFAULT_Z_HEIGHT: float = field(default=150.0, init=False, repr=False)  # v02