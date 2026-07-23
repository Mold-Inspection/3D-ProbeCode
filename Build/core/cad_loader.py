import trimesh
import cadquery as cq
import os
import numpy as np

SUPPORTED_EXTENSIONS = ('.stp', '.step')


class CADLoader:
    """รับหน้าที่โหลดไฟล์ CAD (STEP/STP เท่านั้น) และเตรียม Mesh Data พื้นฐาน"""

    def load(self, filepath):
        ext = os.path.splitext(filepath)[1].lower()

        if ext not in SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file type '{ext or '(no extension)'}'. "
                f"3D ProbeCode only accepts .STEP / .STP files."
            )

        print("Loading STEP — tessellating for display, parsing B-Rep for geometry...")
        step_data = cq.importers.importStep(filepath)
        tmp = "temp_ui_mesh.stl"
        cq.exporters.export(step_data, tmp, exportType='STL',
                            tolerance=0.05, angularTolerance=0.10)
        mesh = trimesh.load(tmp)
        if os.path.exists(tmp):
            os.remove(tmp)

        # ปรับจุดศูนย์กลาง (Center Mesh)
        centroid = mesh.centroid.copy()
        mesh.apply_translation(-centroid)

        return mesh, step_data, centroid
