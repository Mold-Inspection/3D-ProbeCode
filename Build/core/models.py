# ==============================================================================
# core/models.py — โครงสร้างข้อมูล (data classes) ของรูและ segment
# ==============================================================================
# หน้าที่: เก็บโครงสร้างข้อมูลกลางที่ใช้ส่งต่อกันทั่วโปรแกรม
#   - HoleSegment        : เรขาคณิตดิบของรู 1 ช่วง (ก่อน merge เป็นรู counterbore)
#   - HoleSegmentSetting : ค่าตั้งค่าการตรวจสอบต่อ segment เดียว (รูหลายระดับเส้นผ่านศูนย์กลาง)
#   - HoleFeature        : ข้อมูลรูที่ตรวจพบ ใช้แสดงผลฝั่ง UI
#   - StepHole           : รูทรงกระบอกที่สกัดมาจาก B-Rep ของไฟล์ STEP
#   - validate_segment_reachability() : ตรวจสอบว่า segment ที่ลึกกว่าจะถูก
#     probe เข้าไปถึงได้จริงหรือไม่ เทียบกับคอขวดของ segment ที่ตื้นกว่า
#
# ตัวแปรสำคัญที่ปรับจูนได้ (ค่าเริ่มต้นการตรวจสอบต่อรู/segment):
#   layers            = จำนวนชั้น (layer) ที่จะตรวจสอบตามความลึกของรู
#   points_per_layer  = จำนวนจุดสัมผัสผนังรูต่อ 1 ชั้น
#   zigzag_inspection = เปิด/ปิดโหมดหมุนมุมโพรบทีละชั้น (ลดจุดบอดจากการสัมผัสซ้ำมุมเดิม)
#   zigzag_degree     = องศาสะสมที่หมุนต่อ 1 ชั้น เมื่อเปิดโหมด zigzag
#   selected_for_inspection (HoleSegmentSetting) = segment นี้ถูกรวมใน
#     probe path / G-code หรือไม่ (ผู้ใช้ปรับได้ผ่าน checkbox ใน sidebar
#     ขวา — ค่าเริ่มต้นคำนวณจาก validate_segment_reachability())
#
# NOTE (v03): hole.segments / sh.segments ถูกเรียงโดย
# core/step_extractor.py :: _order_segments_deepest_first() เสมอ ให้
# index 0 = segment ที่ลึกที่สุด และ index สุดท้าย = segment ที่ตื้นที่สุด
# (ปากรู) — validate_segment_reachability() ด้านล่างถูกปรับให้ตรงกับ
# ลำดับนี้แล้ว
# ==============================================================================
import numpy as np


class HoleSegment:
    """เรขาคณิตดิบของรู 1 ช่วง (segment) ก่อนถูก merge ใน step_extractor.py
    ใช้เป็นข้อมูลอ้างอิงสำหรับ path planning แบบแยกตามขั้น (แต่ละ segment มี
    รัศมีเป็นของตัวเอง ไม่ interpolate ข้ามขั้นไปยัง segment อื่น)"""
    def __init__(self, open_3d, deep_3d, radius_open, radius_deep):
        self.open_3d     = tuple(open_3d)
        self.deep_3d     = tuple(deep_3d)
        self.radius_open = float(radius_open)
        self.radius_deep = float(radius_deep)
        self.depth       = float(np.linalg.norm(np.array(deep_3d) - np.array(open_3d)))

    def radius_at(self, t: float) -> float:
        """รัศมี ณ ตำแหน่ง t (0.0=ปาก segment นี้ .. 1.0=ก้น segment นี้)"""
        return self.radius_open + t * (self.radius_deep - self.radius_open)


class HoleSegmentSetting:
    """การตั้งค่าการตรวจสอบ (inspection) ต่อ segment เดียวของรูหลายระดับ
    เส้นผ่านศูนย์กลาง — แสดงเป็น sub-tab ที่กางออกมาจากการ์ดรูหลักใน
    sidebar ขวา (การ์ดรู 1 ใบ = 1 display_id, กดขยายแล้วเห็น segment ย่อย)
    v03: seg_idx=0 ตอนนี้คือ segment ที่ลึกที่สุด (mouth = seg_idx สุดท้าย)"""
    def __init__(self, seg_idx: int, radius_open: float, radius_deep: float, depth: float):
        self.seg_idx      = seg_idx          # ลำดับ segment: 0 = ลึกที่สุด (v03)
        self.radius_open  = radius_open
        self.radius_deep  = radius_deep
        self.depth        = depth

        self.layers             = 3      # จำนวนชั้นตรวจสอบเริ่มต้น — ปรับได้
        self.points_per_layer   = 4      # จำนวนจุดสัมผัสผนังต่อชั้นเริ่มต้น — ปรับได้
        self.zigzag_inspection  = False  # เปิด/ปิดโหมด zigzag เริ่มต้น — ปรับได้
        self.zigzag_degree      = 45.0   # องศาสะสมต่อชั้นเมื่อเปิด zigzag — ปรับได้

        self.selected_for_inspection = True  # segment นี้ถูกรวมใน probe path / G-code หรือไม่
        self.size_warning            = ""    # ข้อความเตือนถ้า probe เข้าไม่ถึง segment นี้ (คอขวด)

        self.is_expanded = False             # UI state: sub-tab กางอยู่หรือไม่


def validate_segment_reachability(segments: list) -> None:
    """ตรวจสอบว่าแต่ละ segment จะถูก probe เข้าไปถึงได้จริงหรือไม่ เทียบกับ
    segment ที่ตื้นกว่าติดกัน"""
    
    # ค่าเผื่อความคลาดเคลื่อน (Tolerance) 1 ไมครอน ป้องกันปัญหา Floating-point precision
    # เวลารอยต่อของ Segment มีขนาดเท่ากันพอดี
    TOLERANCE = 0.001 

    for i in range(len(segments) - 1):
        deep    = segments[i]       # segment นี้กำลังถูกตรวจสอบว่าเข้าถึงได้ไหม
        shallow = segments[i + 1]   # เพื่อนบ้านที่ตื้นกว่า/ใกล้ปากรูกว่า (v03: i+1 ไม่ใช่ i-1)

        shallow_narrow = min(shallow.radius_open, shallow.radius_deep)
        deep_wide      = max(deep.radius_open, deep.radius_deep)

        # เพิ่ม TOLERANCE เข้าไปในการเปรียบเทียบ
        if (deep_wide - shallow_narrow) > TOLERANCE:
            deep.selected_for_inspection = False
            deep.size_warning = (
                f"⚠ Counterbore ด้านบน (Segment {i + 2}) มีขนาดเล็กกว่า — "
                f"probe เข้าไม่ถึง Segment {i + 1} นี้ (auto-unselected)")


class HoleFeature:
    """โครงสร้างข้อมูลสำหรับเก็บคุณลักษณะของรูที่ตรวจพบเพื่อใช้ในฝั่ง UI"""
    def __init__(self, hid, x, y, surface_z, bottom_z, depth, radius):
        self.id = hid
        self.x = x
        self.y = y
        self.surface_z = surface_z
        self.bottom_z = bottom_z
        self.depth = depth
        self.radius = radius
        self.layers = 3
        self.points_per_layer = 4
        self.hole_top_z = surface_z
        self._step_hole = None

        self.selected_for_inspection = False
        self.zigzag_inspection = False
        self.zigzag_degree = 45.0

        self.is_rejected = False
        self.reject_reason = ""
        self.position_unknown = False

        # segments ว่างเปล่า = รูปกติ (segment เดียว) ; มี 2+ = รูหลายระดับเส้นผ่านศูนย์กลาง
        # v03: segments[0] = segment ที่ลึกที่สุด
        self.segments: list = []


class StepHole:
    """โครงสร้างข้อมูลรูทรงกระบอกที่สกัดมาจาก B-Rep ของไฟล์ STEP
    v03: self.segments ถูกเรียงแบบ "ลึกสุดก่อน" เสมอโดย
    core/step_extractor.py :: _order_segments_deepest_first()"""
    def __init__(self, open_3d, deep_3d, radius_open, radius_deep, axis_vec, segments=None):
        self.open_3d     = tuple(open_3d)
        self.deep_3d     = tuple(deep_3d)
        self.radius_open = float(radius_open)
        self.radius_deep = float(radius_deep)
        self.radius      = float(radius_open)   # สำหรับใช้งานร่วมกับระบบเดิม
        self.axis        = axis_vec
        self.depth       = float(np.linalg.norm(np.array(deep_3d) - np.array(open_3d)))

        self.display_x = None
        self.display_y = None
        self.depth_top = None
        self.depth_bot = None

        self.segments = segments if segments is not None else [
            HoleSegment(self.open_3d, self.deep_3d, self.radius_open, self.radius_deep)
        ]

    def radius_at(self, t: float) -> float:
        """รัศมี ณ ตำแหน่งความลึก t สัดส่วนระหว่าง 0.0 (ปากรู) ถึง 1.0 (ก้นรู)"""
        return self.radius_open + t * (self.radius_deep - self.radius_open)