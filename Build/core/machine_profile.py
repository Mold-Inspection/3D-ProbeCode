# ==============================================================================
# core/machine_profile.py — ระยะเดินของเครื่อง
# ==============================================================================
# สรุปหน้าที่:
#   ระยะเดินของเครื่อง X/Y/Z (Machine Travel)
#
# ไฟล์ที่เกี่ยวข้อง:
#   ถูกใช้งานโดย:
#     - ui/hardware_setting_dialog.py — หน้าต่าง Hardware Setting และ Set up (MachineProfile)
#     - ui/main_window.py — หน้าต่างหลัก UIManager (MachineProfile)
#   ไลบรารีภายนอก: dataclasses
#
# รายละเอียด:
#   ขนาดพื้นที่ทำงานจริงของเครื่อง CNC (physical
#   machine travel / work area) — ส่วนหนึ่งของ "Hardware Setting" ใน sidebar ซ้าย
#
#   หน้าที่: เก็บระยะเดินสูงสุดของแต่ละแกน (X/Y/Z, mm) ตามสเปกเครื่องจริง
#   — ใช้ตรวจระยะเดินตอน export G-code (Travel Check ใน core/gcode_export_panel.py)
#
#   ตัวแปรสำคัญที่ปรับจูนได้:
#     x_travel / y_travel / z_travel = ระยะเดินสูงสุดแต่ละแกน (mm) — ปรับตามสเปกเครื่อง
#     DEFAULT_X / DEFAULT_Y / DEFAULT_Z = ค่าเริ่มต้นเมื่อกด "Reset to Default"
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