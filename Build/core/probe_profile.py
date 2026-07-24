# ==============================================================================
# core/probe_profile.py — ข้อมูลทางกายภาพของ 3D Touch Probe Stylus
# ==============================================================================
# หน้าที่: เก็บขนาดหัวโพรบ (ก้าน + ปลายทรงกลม) และตรวจสอบว่าโพรบตัวนี้
# เข้าไปวัดรู (ความลึก/ขนาด) ที่ต้องการได้จริงหรือไม่ ก่อนจะสั่งวิ่งจริง
#
# ตัวแปรสำคัญที่ปรับจูนได้:
#   stylus_length  = ความยาวก้านโพรบ (mm) — ระยะลึกสุดที่โพรบลงไปวัดได้
#   tip_diameter   = เส้นผ่าศูนย์กลางหัวโพรบทรงกลม (mm)
#   DEFAULT_LENGTH = ค่าความยาวก้านเริ่มต้นเมื่อกด "Reset to Default"
#   DEFAULT_TIP_D  = ค่าเส้นผ่าศูนย์กลางหัวเริ่มต้นเมื่อกด "Reset to Default"
# ==============================================================================
from dataclasses import dataclass, field

@dataclass
class ProbeProfile:
    stylus_length: float = 50.0   # mm — ความยาวก้านโพรบ ปรับได้
    tip_diameter:  float = 2.0    # mm — เส้นผ่าศูนย์กลางหัวโพรบ ปรับได้

    DEFAULT_LENGTH: float = field(default=50.0, init=False, repr=False)
    DEFAULT_TIP_D:  float = field(default=2.0,  init=False, repr=False)

    # ------------------------------------------------------------------
    @property
    def tip_radius(self) -> float:
        return self.tip_diameter / 2.0

    # ------------------------------------------------------------------
    def can_reach_depth(self, hole_depth: float) -> bool:
        """True ถ้าก้านโพรบยาวพอลงไปถึงความลึก hole_depth"""
        return self.stylus_length >= hole_depth

    def can_fit_in_hole(self, hole_radius: float) -> bool:
        """True ถ้าหัวโพรบเล็กพอที่จะเข้ารูรัศมี hole_radius ได้"""
        return self.tip_radius <= hole_radius

    def check_hole(self, hole_depth: float, hole_radius: float) -> dict:
        """ตรวจสอบทั้งความลึกและขนาดหัวโพรบสำหรับรูหนึ่งรู คืนค่า dict:
        {ok, depth_ok, fit_ok, depth_warning, fit_warning}"""
        depth_ok = self.can_reach_depth(hole_depth)
        fit_ok   = self.can_fit_in_hole(hole_radius)

        depth_warn = (
            f"⚠ Probe too short! Depth {hole_depth:.2f} mm > Stylus {self.stylus_length:.2f} mm"
            if not depth_ok else ""
        )
        fit_warn = (
            f"⚠ Tip too large! Tip ⌀{self.tip_diameter:.2f} mm > Hole ⌀{hole_radius*2:.2f} mm"
            if not fit_ok else ""
        )

        return {
            'ok':            depth_ok and fit_ok,
            'depth_ok':      depth_ok,
            'fit_ok':        fit_ok,
            'depth_warning': depth_warn,
            'fit_warning':   fit_warn,
        }
