# core/models.py
# VERSION: 01
# CHANGE LOG (v01):
#   Added is_rejected / reject_reason / position_unknown to HoleFeature so
#   depth/occlusion-rejected STEP hole candidates (previously silently
#   dropped in step_extractor.get_step_holes_in_view) can be listed in a
#   separate "Unselected Holes" section in the UI instead of vanishing.
import numpy as np

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

class StepHole:
    """โครงสร้างข้อมูลรูทรงกระบอกที่สกัดมาจาก B-Rep ของไฟล์ STEP"""
    def __init__(self, open_3d, deep_3d, radius_open, radius_deep, axis_vec):
        self.open_3d     = tuple(open_3d)
        self.deep_3d     = tuple(deep_3d)
        self.radius_open = float(radius_open)
        self.radius_deep = float(radius_deep)
        self.radius      = float(radius_open)   # สำหรับใช้งานร่วมกับระบบเดิม
        self.axis        = axis_vec
        self.depth       = float(np.linalg.norm(np.array(deep_3d) - np.array(open_3d)))

        mid = (np.array(open_3d) + np.array(deep_3d)) / 2.0
        self.cx_mesh = float(mid[0])
        self.cy_mesh = float(mid[1])
        self.cz_mesh = float(mid[2])

        self.display_x = None
        self.display_y = None
        self.depth_top = None
        self.depth_bot = None

    def radius_at(self, t: float) -> float:
        """คำนวณรัศมี ณ ตำแหน่งความลึก t สัดส่วน بين 0.0 (ปากรู) ถึง 1.0 (ก้นรู)"""
        return self.radius_open + t * (self.radius_deep - self.radius_open)