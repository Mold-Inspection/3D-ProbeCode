# core/cad_loader.py
# VERSION: 01
# CHANGE LOG (v01):
#   Feature (input validation) — enforce STEP/STP-only input.
#   3D ProbeCode plans CMM touch-probe G-code from exact B-Rep hole
#   geometry parsed from STEP files. Mesh-only formats (STL, OBJ, etc.)
#   cannot supply that B-Rep data, so the old silent "load anything
#   trimesh can open, fall back to mesh approximation" branch has been
#   removed entirely. load() now raises ValueError with a clear message
#   for any non-.step/.stp extension instead of silently degrading.
import trimesh
import cadquery as cq
import os
import numpy as np

SUPPORTED_EXTENSIONS = ('.stp', '.step')


class CADLoader:
    """รับหน้าที่โหลดไฟล์ CAD (STEP/STP เท่านั้น) และเตรียม Mesh Data พื้นฐาน"""
    def __init__(self):
        self.mesh = None
        self.step_data = None
        self.centroid = np.zeros(3)

    def load(self, filepath):
        ext = os.path.splitext(filepath)[1].lower()

        if ext not in SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file type '{ext or '(no extension)'}'. "
                f"3D ProbeCode only accepts .STEP / .STP files."
            )

        print("Loading STEP — tessellating for display, parsing B-Rep for geometry...")
        self.step_data = cq.importers.importStep(filepath)
        tmp = "temp_ui_mesh.stl"
        cq.exporters.export(self.step_data, tmp, exportType='STL',
                            tolerance=0.05, angularTolerance=0.10)
        self.mesh = trimesh.load(tmp)
        if os.path.exists(tmp):
            os.remove(tmp)

        # ปรับจุดศูนย์กลาง (Center Mesh)
        self.centroid = self.mesh.centroid.copy()
        self.mesh.apply_translation(-self.centroid)

        return self.mesh, self.step_data, self.centroid
