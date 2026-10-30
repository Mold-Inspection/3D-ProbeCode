# ==============================================================================
# core/machine_profile.py — ขนาดพื้นที่ทำงานจริงของเครื่อง CNC (physical
# machine travel / work area) — ส่วนหนึ่งของ "Hardware Setting" ใน sidebar ซ้าย
# ==============================================================================
# VERSION: 03
# CHANGE LOG (v02 -> v03):
#   ตัด z_height ออก — ใช้คำนวณ Padding Height อย่างเดียว ซึ่งตัดออกแล้ว
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
# — ใช้ตรวจระยะเดินตอน export G-code (Travel Check ใน core/gcode_export_panel.py)
#
# ตัวแปรสำคัญที่ปรับจูนได้:
#   x_travel / y_travel / z_travel = ระยะเดินสูงสุดแต่ละแกน (mm) — ปรับตามสเปกเครื่อง
#   DEFAULT_X / DEFAULT_Y / DEFAULT_Z = ค่าเริ่มต้นเมื่อกด "Reset to Default"
# ==============================================================================
from dataclasses import dataclass, field
 
@dataclass
class MachineProfile:
    x_travel: float = 300.0   # mm — ระยะเดินสูงสุดแกน X ปรับได้
    y_travel: float = 300.0   # mm — ระยะเดินสูงสุดแกน Y ปรับได้
    z_travel: float = 100.0   # mm — ระยะเดินสูงสุดแกน Z ปรับได้
 
    DEFAULT_X: float = field(default=300.0, init=False, repr=False)
    DEFAULT_Y: float = field(default=300.0, init=False, repr=False)
    DEFAULT_Z: float = field(default=100.0, init=False, repr=False)