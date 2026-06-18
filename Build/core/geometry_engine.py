# core/geometry_engine.py
import numpy as np

# เรียกใช้แผนกต่างๆ ที่เราเพิ่งสร้าง
from core.cad_loader import CADLoader
from core.projector import Projector
from core.step_extractor import StepExtractor
from core.path_planner03 import PathPlanner

class MoldGeometry:
    """แกนกลางระบบเรขาคณิต (Facade Manager) ประสานงานโมดูลย่อยทั้งหมด"""
    def __init__(self, filepath=None):
        # สร้างผู้ช่วยของแต่ละระบบ
        self.loader = CADLoader()
        self.projector = Projector()
        self.extractor = StepExtractor()
        self.planner = PathPlanner()

        # ตัวแปรสถานะหลัก
        self.mesh = None
        self.triangles = None
        self.step_data = None
        self._mesh_centroid = np.zeros(3)
        self._step_holes_cache = []

        if filepath:
            self.load_file(filepath)

    def load_file(self, filepath):
        """โหลดไฟล์และอัปเดตข้อมูลไปยังแผนกที่เกี่ยวข้อง"""
        self.mesh, self.step_data, self._mesh_centroid = self.loader.load(filepath)
        self.triangles = self.mesh.faces
        
        # ส่งต่อ Mesh ให้แผนก Projector จัดการพล็อต
        self.projector.update_mesh(self.mesh)
        
        # ส่งต่อ Step Data ให้แผนก Extractor หารู
        if self.step_data:
            self._step_holes_cache = self.extractor.extract(self.step_data, self._mesh_centroid)
        else:
            self._step_holes_cache = []

    def get_physical_dimensions(self):
        return self.mesh.extents if self.mesh is not None else (0, 0, 0)

    # ------------------------------------------------------------------------
    # Routing Request: ส่งคำสั่งจาก UI ไปให้แผนกเฉพาะทางคำนวณ
    # ทำให้ UI พิมพ์โค้ดเหมือนเดิมเป๊ะๆ แต่หลังบ้านถูกแยกระบบแล้ว
    # ------------------------------------------------------------------------
    def get_top_view(self, rot=0):    return self.projector.get_view('Top', rot)
    def get_bottom_view(self, rot=0): return self.projector.get_view('Bottom', rot)
    def get_front_view(self, rot=0):  return self.projector.get_view('Front', rot)
    def get_back_view(self, rot=0):   return self.projector.get_view('Back', rot)
    def get_left_view(self, rot=0):   return self.projector.get_view('Left', rot)
    def get_right_view(self, rot=0):  return self.projector.get_view('Right', rot)

    def get_step_holes_in_view(self, view_name: str):
        return self.extractor.get_step_holes_in_view(self.projector, view_name)

    def get_probe_path_layers(self, hole, n_layers: int, view_name: str):
        return self.planner.get_probe_path_layers(hole, n_layers, self.projector, view_name)