# core/models.py
# VERSION: 02
# CHANGE LOG (v01 -> v02):
#   FEATURE: multi-diameter ("counterbore-style") hole support.
#     Problem: a hole with 2+ true steps in radius (e.g. counterbore +
#     main bore) was collapsed by step_extractor._merge_counterbores()
#     into ONE StepHole holding only the outermost open_3d/deep_3d and
#     radius_open/radius_deep. Probe path generation then interpolated
#     radius LINEARLY between those two extremes (StepHole.radius_at),
#     which is correct for a taper/cone but wrong for a stepped hole —
#     it produced a smooth ramp across what should be a sudden jump,
#     causing the probe path to miss the actual wall at each step.
#   Fix (this file only — geometry/UI wiring comes in later files):
#     1. New HoleSegment class: holds the RAW per-segment geometry
#        (open_3d/deep_3d/radius_open/radius_deep/depth) for one
#        contiguous constant-or-tapered piece of a hole, exactly as it
#        was before any counterbore merge. StepHole now carries a
#        `segments` list of these — for an ordinary (never-merged) hole
#        this list has exactly one entry mirroring the hole itself, so
#        all existing single-segment code paths keep working unchanged.
#     2. New HoleSegmentSetting class: per-segment INSPECTION config
#        (layers, points_per_layer, zigzag_inspection, zigzag_degree,
#        is_expanded) — the UI-facing counterpart of HoleSegment, one
#        per segment. HoleFeature.segments is a list of these; it stays
#        EMPTY for ordinary single-segment holes (legacy behavior, no
#        folder UI shown) and is only populated (by main_window.py, next
#        file in this change) when a hole has 2+ raw segments.
#   No existing attribute was renamed, removed, or changed in meaning.
import numpy as np


class HoleSegment:
    """
    เก็บเรขาคณิตดิบของรู 1 ช่วง (segment) ก่อนถูก merge ทับใน
    step_extractor._merge_counterbores() — ใช้เป็นข้อมูลอ้างอิงสำหรับ
    path planning แบบแยกตามขั้น (แต่ละ segment มีรัศมีเป็นของตัวเอง
    ไม่ interpolate ข้ามขั้นไปยัง segment อื่น)
    """
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
    """
    การตั้งค่าการตรวจสอบ (inspection) ต่อ segment เดียวของรูหลายระดับ
    เส้นผ่านศูนย์กลาง — แสดงเป็น sub-tab ที่กางออกมาจากการ์ดรูหลักใน
    sidebar ขวา (ดีไซน์แบบ "folder": การ์ดรู 1 ใบ = 1 display_id,
    กดขยายแล้วเห็น segment ย่อยแต่ละอันซ้อนข้างใน)

    layers / points_per_layer / zigzag_inspection / zigzag_degree
    ตั้งค่าแยกอิสระต่อ segment ไม่ผูกกับ segment อื่นในรูเดียวกัน
    """
    def __init__(self, seg_idx: int, radius_open: float, radius_deep: float, depth: float):
        self.seg_idx      = seg_idx          # ลำดับ segment: 0 = ใกล้ปากรูสุด
        self.radius_open  = radius_open
        self.radius_deep  = radius_deep
        self.depth        = depth

        self.layers             = 3
        self.points_per_layer   = 4
        self.zigzag_inspection  = False
        self.zigzag_degree      = 45.0

        self.is_expanded = False             # UI state: sub-tab กางอยู่หรือไม่


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
        self.layers = 3              # ค่า Default ขั้นต่ำ 3 ชั้น
        self.points_per_layer = 4    # ค่า Default ขั้นต่ำ 4 จุด
        self.hole_top_z = surface_z  # ขอบปากรูจริง
        self._step_hole = None       # ลิงก์กลับไปยัง StepHole (ถ้ามาจากไฟล์ STEP)

        # --- Feature: Inspection Selection & Zigzag ---
        self.selected_for_inspection = False  # ✅ Checkbox: เลือกรูนี้เพื่อ inspect
        self.zigzag_inspection = False        # ↕ Checkbox: ใช้รูปแบบ zigzag ในการ probe
        self.zigzag_degree = 45.0             # องศาหมุนสะสมต่อ layer (ค่า default 45°)

        # --- Feature: Unselected/Rejected Hole Tracking (v01) ---
        self.is_rejected = False        # ⛔ True = ถูก reject โดย depth/occlusion filter
        self.reject_reason = ""         # เหตุผลสั้น ๆ ที่ถูก reject
        self.position_unknown = False   # True = ไม่สามารถระบุตำแหน่งบนจอได้เลย

        # --- Feature: Multi-diameter hole segments (v02) ---
        # ว่างเปล่า = รูปกติ (segment เดียว) ไม่มี folder UI
        # มี 2+ รายการ = รูหลายระดับเส้นผ่านศูนย์กลาง -> sidebar แสดงเป็น
        # การ์ดเดียวที่กดขยายเห็น sub-tab ต่อ segment
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

        # v02: รายการ segment ดิบ เรียงจากปากรูไปก้นรู ใช้สำหรับ
        # path planning แบบแยกตามขั้น. รูปกติ (ไม่เคยถูก merge เลย)
        # จะมี segment เดียวที่เรขาคณิตตรงกับตัว StepHole เอง —
        # ทำให้โค้ดเดิมที่ยังไม่รู้จัก segments (เช่น radius_at เก่า)
        # ทำงานเหมือนเดิมทุกกรณี
        self.segments = segments if segments is not None else [
            HoleSegment(self.open_3d, self.deep_3d, self.radius_open, self.radius_deep)
        ]

    def radius_at(self, t: float) -> float:
        """คำนวณรัศมี ณ ตำแหน่งความลึก t สัดส่วน بين 0.0 (ปากรู) ถึง 1.0 (ก้นรู)"""
        return self.radius_open + t * (self.radius_deep - self.radius_open)