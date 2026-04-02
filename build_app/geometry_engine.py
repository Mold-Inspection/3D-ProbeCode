import trimesh
import numpy as np
from trimesh.transformations import euler_matrix

class MoldGeometry:
    def __init__(self, filepath=None):
        # Allow starting with an empty engine or a default file
        self.mesh = None
        self.triangles = None
        
        if filepath:
            self.load_file(filepath)
    
    def load_file(self, filepath):
        """โหลดไฟล์ STL ใหม่และจัดให้อยู่กึ่งกลาง"""
        self.mesh = trimesh.load(filepath)
        self.mesh.apply_translation(-self.mesh.centroid)
        self.triangles = self.mesh.faces

    def get_physical_dimensions(self):
        """
        ดึงขนาดจริงของชิ้นงาน (เตรียมไว้สำหรับทำ Grid and Scale)
        Returns the (width, length, height) in millimeters.
        """
        if self.mesh is None: return (0, 0, 0)
        return self.mesh.extents 

    def get_2d_projection(self, rx_deg=0, ry_deg=0, rz_deg=0):
        rx, ry, rz = np.radians([rx_deg, ry_deg, rz_deg])
        matrix = euler_matrix(rx, ry, rz)
        
        rotated_vertices = trimesh.transformations.transform_points(self.mesh.vertices, matrix)
        
        x_2d = rotated_vertices[:, 0]
        y_2d = rotated_vertices[:, 1]
        
        # --- NEW ZERO-POINT CALCULATION (G54) ---
        # Shift all X and Y coordinates so the bottom-left corner is exactly 0,0
        # This removes all negative numbers and makes CNC G-Code generation easy.
        x_2d = x_2d - np.min(x_2d)
        y_2d = y_2d - np.min(y_2d)
        
        # --- DEPTH CALCULATION (Surface is 0) ---
        z_raw = rotated_vertices[:, 2]
        surface_z = np.max(z_raw)
        z_depth = surface_z - z_raw 
        
        z_faces = np.mean(z_depth[self.triangles], axis=1)
        
        return x_2d, y_2d, z_faces, self.triangles

    def get_top_view(self):
        return self.get_2d_projection(rx_deg=0, ry_deg=0, rz_deg=0)

    def get_bottom_view(self):
        return self.get_2d_projection(rx_deg=180, ry_deg=0, rz_deg=0)
        
    def get_front_view(self):
        return self.get_2d_projection(rx_deg=90, ry_deg=0, rz_deg=0)
    
    def get_back_view(self):
        return self.get_2d_projection(rx_deg=90, ry_deg=0, rz_deg=180)
        
    def get_left_view(self):
        return self.get_2d_projection(rx_deg=90, ry_deg=0, rz_deg=-90)
        
    def get_right_view(self):
        return self.get_2d_projection(rx_deg=90, ry_deg=0, rz_deg=90)