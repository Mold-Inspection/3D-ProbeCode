# core/probe_profile.py
from dataclasses import dataclass, field

@dataclass
class ProbeProfile:
    """
    โปรไฟล์ข้อมูลทางกายภาพของ 3D Touch Probe Stylus
    ใช้สำหรับตรวจสอบว่า probe สามารถเข้าถึงความลึกของรูที่ต้องการวัดได้หรือไม่

    Attributes
    ----------
    stylus_length : float
        ความยาวก้านโพรบ (mm) — ระยะสูงสุดที่ probe สามารถลงลึกเข้าไปในรูได้
        ถ้า hole.depth > stylus_length → probe ไม่ถึงก้นรู → แสดงคำเตือนสีแดง

    tip_diameter : float
        เส้นผ่าศูนย์กลางหัวโพรบทรงกลม (mm) → tip_radius = tip_diameter / 2
        ถ้า tip_radius > hole.radius → หัว probe ใหญ่เกินไปจนเข้ารูไม่ได้

    DEFAULT_LENGTH : float = 50.0   ความยาวก้าน default (mm)
    DEFAULT_TIP_D  : float = 2.0    เส้นผ่าศูนย์กลางหัว default (mm)
    """

    stylus_length: float = 50.0   # mm — ความยาวก้านโพรบ
    tip_diameter:  float = 2.0    # mm — เส้นผ่าศูนย์กลางหัวโพรบ

    # ค่า default สำรองสำหรับ reset
    DEFAULT_LENGTH: float = field(default=50.0, init=False, repr=False)
    DEFAULT_TIP_D:  float = field(default=2.0,  init=False, repr=False)

    # ------------------------------------------------------------------
    # Derived Properties
    # ------------------------------------------------------------------
    @property
    def tip_radius(self) -> float:
        """รัศมีหัวโพรบ (mm) = tip_diameter / 2"""
        return self.tip_diameter / 2.0

    # ------------------------------------------------------------------
    # Validation Helpers
    # ------------------------------------------------------------------
    def can_reach_depth(self, hole_depth: float) -> bool:
        """
        คืน True ถ้า probe ยาวพอที่จะลงไปถึงความลึก hole_depth
        False = probe สั้นเกินไป → แสดงคำเตือน / popup error
        """
        return self.stylus_length >= hole_depth

    def can_fit_in_hole(self, hole_radius: float) -> bool:
        """
        คืน True ถ้าหัว probe เล็กพอที่จะเข้าไปในรูที่มีรัศมี hole_radius
        False = หัว probe ใหญ่เกินไป → probe ชนขอบรู
        """
        return self.tip_radius <= hole_radius

    def check_hole(self, hole_depth: float, hole_radius: float) -> dict:
        """
        ตรวจสอบทั้งความลึกและขนาดหัวโพรบสำหรับรูหนึ่งรู
        คืนค่า dict ที่มีผลการตรวจสอบและข้อความเตือน

        Returns
        -------
        {
            'ok'            : bool   — True ถ้าผ่านทุกเงื่อนไข
            'depth_ok'      : bool   — probe ยาวพอหรือไม่
            'fit_ok'        : bool   — หัวโพรบเล็กพอหรือไม่
            'depth_warning' : str    — ข้อความเตือนเรื่องความลึก ('' ถ้าไม่มีปัญหา)
            'fit_warning'   : str    — ข้อความเตือนเรื่องขนาดหัว ('' ถ้าไม่มีปัญหา)
        }
        """
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
