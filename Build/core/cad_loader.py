# ==============================================================================
# core/cad_loader.py — โหลดไฟล์ CAD (STEP/STP) และเตรียม Mesh สำหรับแสดงผล
# ==============================================================================
# หน้าที่: อ่านไฟล์ .step/.stp ด้วย cadquery แล้วแปลง (tessellate) เป็น mesh
# สำหรับแสดงผลบนจอ พร้อมเก็บข้อมูล B-Rep ดิบ (step_data) ไว้ใช้คำนวณรูละเอียด
# และย้าย mesh ให้จุดศูนย์กลางอยู่ที่ (0,0,0)
#
# ตัวแปรสำคัญที่ปรับจูนได้:
#   SUPPORTED_EXTENSIONS = นามสกุลไฟล์ที่โปรแกรมยอมรับ
#   tolerance / angularTolerance = ความละเอียดของ mesh ที่แปลงจาก STEP
#                                  (ค่ายิ่งน้อย = mesh ละเอียดขึ้นแต่ช้าลง)
# ==============================================================================
import trimesh
import cadquery as cq
import os
import numpy as np

SUPPORTED_EXTENSIONS = ('.stp', '.step')   # นามสกุลไฟล์ที่โปรแกรมยอมรับ — ปรับได้


class CADLoader:
    """โหลดไฟล์ CAD (STEP/STP เท่านั้น) และเตรียม Mesh Data พื้นฐาน"""

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
        # ความละเอียด mesh ที่แปลงจาก STEP (mm / องศา) — ลดค่าเพื่อความละเอียดสูงขึ้น (ช้าลง)
        cq.exporters.export(step_data, tmp, exportType='STL',
                            tolerance=0.05, angularTolerance=0.10)
        mesh = trimesh.load(tmp)
        if os.path.exists(tmp):
            os.remove(tmp)

        centroid = mesh.centroid.copy()
        mesh.apply_translation(-centroid)

        return mesh, step_data, centroid
