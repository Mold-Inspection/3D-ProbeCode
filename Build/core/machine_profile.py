# ==============================================================================
# core/machine_profile.py — ขนาดพื้นที่ทำงานจริงของเครื่อง CNC (physical
# machine travel / work area) — ส่วนหนึ่งของ "Hardware Setting" ใน sidebar ซ้าย
# ==============================================================================
# VERSION: 01
# หน้าที่: เก็บระยะเดินสูงสุดของแต่ละแกน (X/Y/Z, mm) ตามสเปกเครื่องจริง —
# ปัจจุบันใช้ "เก็บและแสดงผล" เท่านั้น (ยังไม่ผูกกับการตรวจสอบ/บล็อกใด ๆ)
# วางไว้เป็นข้อมูลอ้างอิงสำหรับงานความปลอดภัย probe collision ในอนาคต
# (ดู PLAN probe-safety Phase 1–3 ใน memory — ยังไม่ implement ที่นี่)
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