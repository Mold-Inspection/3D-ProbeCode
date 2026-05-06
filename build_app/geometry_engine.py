import trimesh
import numpy as np
from trimesh.transformations import euler_matrix
import os
import cadquery as cq  # [NEW] เพิ่มไลบรารีสำหรับจัดการไฟล์ STEP (B-Rep)

class MoldGeometry:
    def __init__(self, filepath=None):
        self.mesh = None
        self.triangles = None
        self.step_data = None  # [NEW] ตัวแปรนี้จะเก็บข้อมูลสมการคณิตศาสตร์ที่แท้จริง รอไว้ใช้ดึงพิกัดทำ G-Code
        if filepath:
            self.load_file(filepath)
    
    def load_file(self, filepath):
        ext = os.path.splitext(filepath)[1].lower()
        
        # --- NEW: ระบบตรวจจับไฟล์และ Tessellation อัตโนมัติ ---
        if ext in ['.stp', '.step']:
            print("Loading STEP file and tessellating for UI...")
            # 1. โหลดข้อมูล B-Rep เข้ามาเก็บไว้เป็น Backend (เอาไว้คำนวณ Pathing วันหลัง)
            self.step_data = cq.importers.importStep(filepath)
            
            # 2. จำลองสร้างโครงข่าย Mesh เป็นไฟล์ชั่วคราว เพื่อส่งต่อให้ UI
            temp_stl_path = "temp_ui_mesh.stl"
            # [MODIFIED] เพิ่มพารามิเตอร์ tolerance (ระยะห่าง) และ angularTolerance (องศา)
            # ค่าที่สูงขึ้น = โหลดไวขึ้นมาก แต่ภาพอาจจะดูเป็นเหลี่ยมขึ้นเล็กน้อย
            cq.exporters.export(
                self.step_data, 
                temp_stl_path, 
                exportType='STL', 
                tolerance=0.5,           # ปกติจะเป็น 0.001 ซึ่งละเอียดเกินไป
                angularTolerance=0.5     # ปกติจะเป็น 0.1
            )
            
            # 3. ให้ trimesh โหลดตัว Mesh เข้ามา (ทำให้โค้ดที่เหลือของคุณทำงานได้ปกติต่อไป)
            self.mesh = trimesh.load(temp_stl_path)
            
            # 4. ลบไฟล์ชั่วคราวทิ้งเพื่อความสะอาด
            if os.path.exists(temp_stl_path):
                os.remove(temp_stl_path)
        else:
            # กรณีผู้ใช้อัปโหลดไฟล์ STL แบบเดิม ก็ยังรองรับอยู่
            self.mesh = trimesh.load(filepath)
            self.step_data = None 

        # --- โค้ดด้านล่างนี้คือของเดิมของคุณเป๊ะๆ ไม่มีการเปลี่ยนแปลง ---
        self.mesh.apply_translation(-self.mesh.centroid)
        
        extents = self.mesh.extents
        min_axis = np.argmin(extents) 
        
        if min_axis == 0: 
            self.mesh.apply_transform(euler_matrix(0, np.radians(90), 0))
        elif min_axis == 1: 
            self.mesh.apply_transform(euler_matrix(np.radians(90), 0, 0))
            
        self.triangles = self.mesh.faces

    def get_physical_dimensions(self):
        if self.mesh is None: return (0, 0, 0)
        return self.mesh.extents 

    def get_2d_projection(self, rx_deg=0, ry_deg=0, rz_deg=0, screen_rot=0):
        rx, ry, rz = np.radians([rx_deg, ry_deg, rz_deg])
        matrix = euler_matrix(rx, ry, rz)
        
        rotated_vertices = trimesh.transformations.transform_points(self.mesh.vertices, matrix)
        rotated_normals = np.dot(self.mesh.face_normals, matrix[:3, :3].T)
        
        # Calculate 2D Area to prevent Matplotlib crashes
        v0 = rotated_vertices[self.triangles[:, 0]]
        v1 = rotated_vertices[self.triangles[:, 1]]
        v2 = rotated_vertices[self.triangles[:, 2]]
        area = (v1[:, 0] - v0[:, 0]) * (v2[:, 1] - v0[:, 1]) - (v1[:, 1] - v0[:, 1]) * (v2[:, 0] - v0[:, 0])
        
        # KEEP triangles that face the camera (+Z) AND have actual 2D surface area (not edge-on)
        front_facing = (rotated_normals[:, 2] > 0.001) & (np.abs(area) > 1e-5)
        
        # Fallback if the STL file was saved inside-out
        if np.sum(front_facing) == 0:
            front_facing = (rotated_normals[:, 2] < -0.001) & (np.abs(area) > 1e-5)

        visible_triangles = self.triangles[front_facing]

        x_2d = rotated_vertices[:, 0]
        y_2d = rotated_vertices[:, 1]
        
        if screen_rot != 0:
            rad = np.radians(screen_rot)
            c, s = np.cos(rad), np.sin(rad)
            x_new = x_2d * c - y_2d * s
            y_new = x_2d * s + y_2d * c
            x_2d, y_2d = x_new, y_new

        x_2d = x_2d - np.min(x_2d)
        y_2d = y_2d - np.min(y_2d)
        
        z_raw = rotated_vertices[:, 2]
        surface_z = np.max(z_raw)
        z_depth = surface_z - z_raw 
        
        z_faces = np.mean(z_depth[visible_triangles], axis=1)
        
        return x_2d, y_2d, z_depth, z_faces, visible_triangles

    # Add the screen_rot parameter to all standard views
    def get_top_view(self, rot=0):
        return self.get_2d_projection(rx_deg=0, ry_deg=0, rz_deg=0, screen_rot=rot)
    def get_bottom_view(self, rot=0):
        return self.get_2d_projection(rx_deg=180, ry_deg=0, rz_deg=0, screen_rot=rot)
    def get_front_view(self, rot=0):
        return self.get_2d_projection(rx_deg=90, ry_deg=0, rz_deg=0, screen_rot=rot)
    def get_back_view(self, rot=0):
        return self.get_2d_projection(rx_deg=90, ry_deg=0, rz_deg=180, screen_rot=rot)
    def get_left_view(self, rot=0):
        return self.get_2d_projection(rx_deg=90, ry_deg=0, rz_deg=-90, screen_rot=rot)
    def get_right_view(self, rot=0):
        return self.get_2d_projection(rx_deg=90, ry_deg=0, rz_deg=90, screen_rot=rot)
    
    # --- NEW: STEP 1 - CALCULATE Z HEIGHT ---
    def calculate_optimal_z_height(self, laser_ref):
        if self.mesh is None:
            return "Please load an STL file first."
            
        # 1. ดึงค่าความหนาและความลึกจาก 3D Mesh
        extents = self.get_physical_dimensions()
        mold_thickness = extents[2] # ความหนารวมแกน Z
        
        z_raw = self.mesh.vertices[:, 2]
        surface_z = np.max(z_raw)
        z_depth = surface_z - z_raw
        max_pocket_depth = np.max(z_depth) # ความลึกที่สุดของร่อง

        # 2. คำนวณหาจุดกึ่งกลางและระยะ Z
        mid_scan_z = mold_thickness - (max_pocket_depth / 2)
        recommended_z_height = mid_scan_z + laser_ref

        # 3. เช็คความปลอดภัย
        clearance = recommended_z_height - mold_thickness
        if clearance <= 5.0:
            return f"⚠️ ระวังชน! แนะนำคาน Z: {recommended_z_height:.1f} mm (ห่างชิ้นงาน {clearance:.1f} mm)"
            
        return f"✅ Setup Z-Height: {recommended_z_height:.1f} mm"