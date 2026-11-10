# ==============================================================================
# core/probe_profile.py — ข้อมูลหัววัดและ Effective Tip
# ==============================================================================
# สรุปหน้าที่:
#   ข้อมูลหัววัด: ความยาวก้าน ⌀ ลูกบอล ⌀ ก้าน Effective Tip (รวม/แยก X-Y)
#   ทริกแกน Z และตรวจว่าหัววัดเข้ารูได้หรือไม่
#
# ไฟล์ที่เกี่ยวข้อง:
#   ถูกใช้งานโดย:
#     - ui/main_window.py — หน้าต่างหลัก UIManager (ProbeProfile)
#   ไลบรารีภายนอก: dataclasses, math
#
# รายละเอียด:
#   ข้อมูลทางกายภาพของ 3D Touch Probe Stylus
#
#   หน้าที่: เก็บขนาดหัวโพรบ (ตัวจับ + ก้าน + ปลายทรงกลม) และตรวจสอบว่าโพรบตัวนี้
#   เข้าไปวัดรู (ความลึก/ขนาด) ที่ต้องการได้จริงหรือไม่ ก่อนจะสั่งวิ่งจริง
#
#   ตัวแปรสำคัญที่ปรับจูนได้:
#     stylus_length  = ความยาวก้านโพรบ (mm) — ระยะลึกสุดที่โพรบลงไปวัดได้
#     tip_diameter   = เส้นผ่าศูนย์กลางหัวโพรบทรงกลม (mm)
#     DEFAULT_LENGTH = ค่าความยาวก้านเริ่มต้นเมื่อกด "Reset to Default"
#     DEFAULT_TIP_D  = ค่าเส้นผ่าศูนย์กลางหัวเริ่มต้นเมื่อกด "Reset to Default"
# ==============================================================================

import math
from dataclasses import dataclass, field
 
@dataclass
class ProbeProfile:
    stylus_length: float = 50.0   # mm — ความยาวก้านโพรบ ปรับได้
    tip_diameter:  float = 2.0    # mm — เส้นผ่าศูนย์กลางหัวโพรบ ปรับได้
    # ระยะว่างขั้นต่ำระหว่างหัวโพรบกับผนังรู (วัดจากจุดศูนย์กลาง layer) — หัวโพรบต้องมีที่
    # ให้เคลื่อนที่ก่อนแตะผนัง รูที่แคบกว่านี้จะถูกเตือน/ข้ามตอน export — ปรับได้
    wall_clearance: float = 0.5   # mm
    # เส้นผ่าศูนย์กลางหัวโพรบ "ที่ใช้งานจริง" จากการ calibrate กับ Ring Gauge — เล็กกว่าขนาด
    # ลูกบอลเล็กน้อยเพราะก้านโพรบโก่งก่อน trigger ใช้ชดเชยรัศมีตอนประเมินผล (0 = ใช้ tip_diameter)
    effective_tip_diameter: float = 0.0   # mm
    # แยกแกน X / Y จากผนังนอกตอน Set up — หัวโพรบ kinematic ทริกไม่เท่ากันแต่ละทิศ (0 = ไม่มี)
    effective_tip_dx: float = 0.0   # mm
    effective_tip_dy: float = 0.0   # mm
    effective_tip_xy_date: str = ""   # YYYY-MM-DD ที่ตั้งค่าแยกแกนจาก Set up ("" = ไม่ทราบ)
    # ระยะว่างขั้นต่ำระหว่างลูกบอลกับพื้น/ขั้นที่อยู่ใต้ชั้นวัดที่ลึกที่สุด — ชั้นจะถูกยกขึ้นให้เอง
    floor_clearance: float = 1.0   # mm
    # หัวโพรบทริกเมื่อถูกดันขึ้นตรง ๆ (แนว Z) ได้ไหม — ปิด = ไม่มีคำสั่งแตะพื้นใน G-code เลย
    z_trigger: bool = False
    # แตะสองครั้ง (เร็ว → ถอย → ช้า) ใช้ค่าครั้งที่สอง
    double_touch: bool = True
    retouch_distance: float = 1.5   # mm — 0.5 ทำให้ ALARM:4 บนเครื่องจริง (2026-10-21); 1.0 → 1.5
    retouch_feed: float = 20.0      # mm/min
    retouch_count: int = 3          # แตะช้ากี่ครั้งต่อจุด (ค่าที่ใช้ = มัธยฐาน — ตัดค่ากระโดดทิ้ง)
    retouch_dwell: float = 0.2      # หน่วงก่อนแตะช้าแต่ละครั้ง (s) ให้เครื่อง/ก้านนิ่งหลังถอย
    # ก้านโพรบ — ใช้หาความลึกที่ก้านเริ่มแตะขอบปากรูก่อนหัวโพรบ (shaft_contact_depth)
    stylus_shaft_diameter: float = 1.0   # mm — ⌀ ก้านตรงส่วนที่ลงไปในรู (วัดด้วยเวอร์เนียร์)
    stylus_tilt_deg: float = 0.0         # องศา — ก้านเอียงจากแนวดิ่ง (0 = ตั้งตรง)
 
    DEFAULT_LENGTH: float = field(default=50.0, init=False, repr=False)
    DEFAULT_TIP_D:  float = field(default=2.0,  init=False, repr=False)
    DEFAULT_CLEARANCE: float = field(default=0.5, init=False, repr=False)
    DEFAULT_EFFECTIVE_TIP_D: float = field(default=0.0, init=False, repr=False)
    DEFAULT_FLOOR_CLEARANCE: float = field(default=1.0, init=False, repr=False)
    DEFAULT_Z_TRIGGER: bool = field(default=False, init=False, repr=False)
    DEFAULT_DOUBLE_TOUCH: bool = field(default=True, init=False, repr=False)
    DEFAULT_RETOUCH_DISTANCE: float = field(default=1.5, init=False, repr=False)  # (1.5)
    DEFAULT_RETOUCH_COUNT: int = field(default=3, init=False, repr=False)
    DEFAULT_RETOUCH_DWELL: float = field(default=0.2, init=False, repr=False)
    DEFAULT_RETOUCH_FEED: float = field(default=20.0, init=False, repr=False)
    DEFAULT_SHAFT_D: float = field(default=1.0, init=False, repr=False)
    DEFAULT_TILT_DEG: float = field(default=0.0, init=False, repr=False)
 
    # ------------------------------------------------------------------
    @property
    def tip_radius(self) -> float:
        return self.tip_diameter / 2.0

    @property
    def effective_tip_radius(self) -> float:
        """รัศมีที่ใช้ชดเชยจุดวัด — ค่าที่ calibrate แล้วถ้ามี ไม่งั้นใช้ขนาดหัวโพรบ"""
        d = self.effective_tip_diameter if self.effective_tip_diameter > 0 else self.tip_diameter
        return d / 2.0
 
    @property
    def effective_tip_radius_xy(self):
        """(rX, rY) จาก Set up — None ถ้ายังไม่มีค่าแยกแกน"""
        if self.effective_tip_dx > 0 and self.effective_tip_dy > 0:
            return self.effective_tip_dx / 2.0, self.effective_tip_dy / 2.0
        return None

    @property
    def pretravel(self) -> float:
        """ระยะที่โพรบเดินเลยจุดแตะก่อนทริก (ต่อด้าน) = (Tip ⌀ − Effective Tip ⌀) / 2 — 0 ถ้ายังไม่ calibrate"""
        if self.effective_tip_diameter <= 0:
            return 0.0
        return max(0.0, (self.tip_diameter - self.effective_tip_diameter) / 2.0)

    def shaft_contact_depth(self):
        """ความลึกของศูนย์กลางลูกบอลใต้ปากรู (mm) ที่ก้านเริ่มแตะขอบปากรูก่อนโพรบทริก
        — None = ไม่เกิด (ก้านตั้งตรงและยังไม่รู้ pre-travel)

        ผนังตั้งตรง ลูกบอลรัศมี R แตะผนัง ก้านรัศมี r ยังห่างผนัง R − r ที่ทุกความสูง แต่:
          - ก้านเอียง θ : ก้านที่สูงเหนือลูกบอล h เข้าใกล้ผนังเพิ่ม h·tanθ
          - pre-travel p: ลูกบอลถูกผนังหยุดไว้ ตัวโพรบเดินต่ออีก p ก่อนทริก ก้านหมุนรอบลูกบอล
                          จุดที่สูง h (ก้านยาว L) เข้าหาผนังเพิ่ม p·h/L
        ก้านแตะขอบปากรู (h = ความลึกของลูกบอล) เมื่อ h·(tanθ + p/L) ≥ R − r
          → ความลึกวิกฤต d = (R − r) / (tanθ + p/L)
        ใช้รัศมีลูกบอลจริง (Tip ⌀) ไม่ใช่ Effective Tip ⌀ — ส่วน p ได้จากผลต่างของสองค่านี้"""
        gap = (self.tip_diameter - self.stylus_shaft_diameter) / 2.0
        if gap <= 0:
            return 0.0           # ก้านใหญ่เท่าลูกบอล — แตะได้ทุกความลึก
        k = math.tan(math.radians(abs(self.stylus_tilt_deg))) + self.pretravel / max(self.stylus_length, 1e-6)
        if k <= 1e-9:
            return None
        return gap / k

    # ------------------------------------------------------------------
    def can_reach_depth(self, hole_depth: float) -> bool:
        """True ถ้าก้านโพรบยาวพอลงไปถึงความลึก hole_depth"""
        return self.stylus_length >= hole_depth
 
    def can_fit_in_hole(self, hole_radius: float) -> bool:
        """True ถ้าหัวโพรบเข้ารูรัศมี hole_radius ได้ โดยเหลือระยะว่างถึงผนัง
        อย่างน้อย wall_clearance (เดิมยอมให้หัวโพรบใหญ่เท่ารูพอดี = ไม่มีที่ขยับเลย)"""
        return self.tip_radius + self.wall_clearance <= hole_radius
 
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
            f"⚠ Tip too large! Tip ⌀{self.tip_diameter:.2f} mm + {self.wall_clearance:.2f} mm "
            f"clearance per side > Hole ⌀{hole_radius*2:.2f} mm"
            if not fit_ok else ""
        )
 
        return {
            'ok':            depth_ok and fit_ok,
            'depth_ok':      depth_ok,
            'fit_ok':        fit_ok,
            'depth_warning': depth_warn,
            'fit_warning':   fit_warn,
        }
 


