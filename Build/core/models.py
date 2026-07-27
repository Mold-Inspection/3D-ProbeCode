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
# ==============================================================================
# VERSION: 02
# CHANGE LOG (v01 -> v02):
#   FEATURE: HoleSegmentSetting ได้ field ใหม่ 2 ตัว:
#     - selected_for_inspection (bool) : segment นี้ถูกเลือกตรวจสอบหรือไม่
#       (ค่าเริ่มต้น True, ผู้ใช้กด checkbox ใน sidebar ขวาปรับเองได้)
#     - size_warning (str)             : ข้อความเตือนถ้า segment นี้ probe
#       เข้าไม่ถึง (คอขวดของ segment ด้านบนแคบกว่า) — "" ถ้าไม่มีปัญหา
#   FEATURE: ฟังก์ชันใหม่ validate_segment_reachability(segments) — เทียบ
#     แต่ละ segment กับ segment ที่ตื้นกว่าติดกัน (index ก่อนหน้า) ถ้า
#     "จุดกว้างสุด" ของ segment ที่ลึกกว่า มากกว่า "จุดแคบสุด" ของ segment
#     ที่ตื้นกว่า → segment ลึกนั้นถูก probe เข้าไม่ถึง (ชนคอขวด) → ตั้ง
#     selected_for_inspection=False + size_warning อัตโนมัติ เรียกครั้งเดียว
#     ตอนสร้างรายการ segment สด (ui/main_window.py _build_segment_settings())
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
    sidebar ขวา (การ์ดรู 1 ใบ = 1 display_id, กดขยายแล้วเห็น segment ย่อย)"""
    def __init__(self, seg_idx: int, radius_open: float, radius_deep: float, depth: float):
        self.seg_idx      = seg_idx          # ลำดับ segment: 0 = ใกล้ปากรูสุด
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
    """ตรวจสอบว่าแต่ละ segment (เรียงจากปากรูก่อน index 0 = ตื้นสุด) จะถูก
    probe เข้าไปถึงได้จริงหรือไม่ เทียบกับ segment ที่ตื้นกว่าติดกัน

    หลักการ: probe ต้องสอดผ่าน segment ที่ตื้นกว่าก่อนถึงจะไปแตะผนัง
    segment ที่ลึกกว่าได้ — ถ้า "จุดกว้างสุด" ของ segment ที่ลึกกว่า
    มากกว่า "จุดแคบสุด" ของ segment ที่ตื้นกว่า (คอขวด) แสดงว่า probe
    ชนขอบคอขวดตอนเข้า/ถอยแนวรัศมีกว้างกว่าช่องที่ผ่านได้ → segment ลึก
    นั้นถูกตั้ง selected_for_inspection=False + size_warning อัตโนมัติ
    (ผู้ใช้ยัง override เปิดกลับได้เองผ่าน checkbox ใน sidebar)

    Parameters
    ----------
    segments : list ของ HoleSegmentSetting เรียงจากปากรู (index 0) ไปก้นรู
               ฟังก์ชันนี้ mutate ตัว object ใน list โดยตรง ไม่ return ค่า
    """
    for i in range(1, len(segments)):
        shallow = segments[i - 1]
        deep    = segments[i]

        shallow_narrow = min(shallow.radius_open, shallow.radius_deep)
        deep_wide      = max(deep.radius_open, deep.radius_deep)

        if deep_wide > shallow_narrow:
            deep.selected_for_inspection = False
            deep.size_warning = (
                f"⚠ Counterbore ด้านบน (Segment {i}) มีขนาดเล็กกว่า — "
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
        self.layers = 3              # จำนวนชั้นตรวจสอบเริ่มต้น — ปรับได้
        self.points_per_layer = 4    # จำนวนจุดสัมผัสผนังต่อชั้นเริ่มต้น — ปรับได้
        self.hole_top_z = surface_z  # ขอบปากรูจริง
        self._step_hole = None       # ลิงก์กลับไปยัง StepHole (ถ้ามาจากไฟล์ STEP)

        self.selected_for_inspection = False  # เลือกรูนี้เพื่อตรวจสอบหรือไม่
        self.zigzag_inspection = False        # ใช้รูปแบบ zigzag ในการ probe หรือไม่
        self.zigzag_degree = 45.0             # องศาสะสมต่อชั้นเมื่อเปิด zigzag — ปรับได้

        self.is_rejected = False        # True = ถูก reject โดยเงื่อนไข depth/occlusion
        self.reject_reason = ""         # เหตุผลที่ถูก reject
        self.position_unknown = False   # True = ไม่สามารถระบุตำแหน่งบนจอได้

        # segments ว่างเปล่า = รูปกติ (segment เดียว) ; มี 2+ = รูหลายระดับเส้นผ่านศูนย์กลาง
        self.segments: list = []


class StepHole:
    """โครงสร้างข้อมูลรูทรงกระบอกที่สกัดมาจาก B-Rep ของไฟล์ STEP"""
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