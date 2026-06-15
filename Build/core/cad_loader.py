# core/cad_loader.py
import trimesh
import cadquery as cq
import os
import numpy as np

class CADLoader:
    """รับหน้าที่โหลดไฟล์ CAD และเตรียม Mesh Data พื้นฐาน"""
    def __init__(self):
        self.mesh = None
        self.step_data = None
        self.centroid = np.zeros(3)

    def load(self, filepath):
        ext = os.path.splitext(filepath)[1].lower()

        if ext in ['.stp', '.step']:
            print("Loading STEP — tessellating for display, parsing B-Rep for geometry...")
            self.step_data = cq.importers.importStep(filepath)
            tmp = "temp_ui_mesh.stl"
            cq.exporters.export(self.step_data, tmp, exportType='STL',
                                tolerance=0.05, angularTolerance=0.10)
            self.mesh = trimesh.load(tmp)
            if os.path.exists(tmp):
                os.remove(tmp)
        else:
            self.mesh = trimesh.load(filepath)
            self.step_data = None
            print("Loaded STL — calculations use mesh approximation")

        # ปรับจุดศูนย์กลาง (Center Mesh)
        self.centroid = self.mesh.centroid.copy()
        self.mesh.apply_translation(-self.centroid)
        
        return self.mesh, self.step_data, self.centroid