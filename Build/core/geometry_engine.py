# ==============================================================================
# core/geometry_engine.py — MoldGeometry: ศูนย์กลางเชื่อมโมดูล Backend ทั้งหมด
# ==============================================================================
# หน้าที่: เป็น facade ที่รวม 4 โมดูลย่อยเข้าด้วยกัน แล้วเปิด method กลาง
# ให้ฝั่ง UI เรียกใช้โดยไม่ต้องรู้รายละเอียดภายใน
#   - loader    (CADLoader)    โหลดไฟล์ STEP/STP
#   - projector (Projector)    แปลงพิกัด 3D → 2D ตามมุมมอง
#   - extractor (StepExtractor) สกัดข้อมูลรูจาก B-Rep
#   - planner   (PathPlanner)  คำนวณเส้นทางโพรบทีละชั้น
#
# ไฟล์นี้ไม่มีตัวแปรที่ต้องปรับจูนโดยตรง — ค่าคงที่ต่าง ๆ อยู่ในแต่ละโมดูลย่อย
# ==============================================================================
import numpy as np

from core.cad_loader import CADLoader
from core.projector import Projector
from core.step_extractor import StepExtractor
from core.path_planner import PathPlanner


class MoldGeometry:
    """Facade Manager — ประสานงานระหว่างโมดูลย่อยทั้งหมด"""

    def __init__(self, filepath=None):
        self.loader    = CADLoader()
        self.projector = Projector()
        self.extractor = StepExtractor()
        self.planner   = PathPlanner()

        self.mesh             = None
        self.step_data        = None
        self._mesh_centroid   = np.zeros(3)

        if filepath:
            self.load_file(filepath)

    def load_file(self, filepath):
        self.mesh, self.step_data, self._mesh_centroid = self.loader.load(filepath)
        self.projector.update_mesh(self.mesh)
        if self.step_data:
            self.extractor.extract(self.step_data, self._mesh_centroid)

    def get_physical_dimensions(self):
        return self.mesh.extents if self.mesh is not None else (0, 0, 0)

    # ------------------------------------------------------------------
    # View routing — ส่ง screen_rot ต่อให้ projector เพื่อให้แคชตรงกับ canvas
    # ------------------------------------------------------------------
    def get_top_view(self,    rot=0): return self.projector.get_view('Top',    rot)
    def get_bottom_view(self, rot=0): return self.projector.get_view('Bottom', rot)
    def get_front_view(self,  rot=0): return self.projector.get_view('Front',  rot)
    def get_back_view(self,   rot=0): return self.projector.get_view('Back',   rot)
    def get_left_view(self,   rot=0): return self.projector.get_view('Left',   rot)
    def get_right_view(self,  rot=0): return self.projector.get_view('Right',  rot)

    def get_step_holes_in_view(self, view_name: str, screen_rot: int = 0):
        """ต้องส่ง screen_rot เพื่อให้ตำแหน่งรูที่แสดงตรงกับ canvas"""
        return self.extractor.get_step_holes_in_view(self.projector, view_name, screen_rot, mesh=self.mesh)

    def get_probe_path_layers(self, hole, n_layers: int, view_name: str,
                               screen_rot: int = 0,
                               zigzag_inspection: bool = False,
                               zigzag_degree: float = 45.0):
        return self.planner.get_probe_path_layers(
            hole, n_layers, self.projector, view_name,
            screen_rot=screen_rot,
            zigzag_inspection=zigzag_inspection,
            zigzag_degree=zigzag_degree)

    def get_probe_path_layers_multi(self, hole, segment_settings: list,
                                     view_name: str, screen_rot: int = 0):
        """เส้นทางแบบแยกตาม segment สำหรับรูหลายระดับเส้นผ่านศูนย์กลาง
        hole คือ StepHole ที่มี .segments (เรขาคณิตดิบ); segment_settings คือ
        list ของ HoleSegmentSetting ที่จับคู่กัน (ดู path_planner.py)"""
        return self.planner.get_probe_path_layers_multi(
            hole, segment_settings, self.projector, view_name,
            screen_rot=screen_rot)
