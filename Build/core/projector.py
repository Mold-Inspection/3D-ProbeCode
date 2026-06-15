# core/projector.py
import numpy as np
import trimesh
from trimesh.transformations import euler_matrix

_VIEW_ROTATIONS = {
    'Top':    (0,    0,   0,   0),
    'Bottom': (180,  0,   0,   0),
    'Front':  (-90,  0,   0,   0),
    'Back':   (90,   0, 180,   0),
    'Left':   (-90,  0,  90,   0),
    'Right':  (-90,  0, -90,   0),
}

class Projector:
    """จัดการการหมุนโมเดล 3D และฉายพิกัดลงระนาบ 2D"""
    def __init__(self):
        self.mesh = None
        self.triangles = None
        self._view_params_cache = {}

    def update_mesh(self, mesh):
        self.mesh = mesh
        self.triangles = mesh.faces if mesh else None
        self._view_params_cache = {}

    def get_2d_projection(self, rx_deg=0, ry_deg=0, rz_deg=0, screen_rot=0):
        if self.mesh is None: return [], [], [], [], []
        
        matrix = euler_matrix(*np.radians([rx_deg, ry_deg, rz_deg]))
        rv = trimesh.transformations.transform_points(self.mesh.vertices, matrix)
        rn = np.dot(self.mesh.face_normals, matrix[:3, :3].T)

        v0, v1, v2 = rv[self.triangles[:,0]], rv[self.triangles[:,1]], rv[self.triangles[:,2]]
        area = ((v1[:,0]-v0[:,0])*(v2[:,1]-v0[:,1]) - (v1[:,1]-v0[:,1])*(v2[:,0]-v0[:,0]))
        
        front = (rn[:,2] > 0.001) & (np.abs(area) > 1e-5)
        if front.sum() == 0:
            front = (rn[:,2] < -0.001) & (np.abs(area) > 1e-5)
        vis_tri = self.triangles[front]

        x2d, y2d = rv[:,0].copy(), rv[:,1].copy()
        if screen_rot != 0:
            c, s = np.cos(np.radians(screen_rot)), np.sin(np.radians(screen_rot))
            x2d, y2d = x2d*c - y2d*s, x2d*s + y2d*c

        xc = (x2d.min() + x2d.max()) / 2.0
        yc = (y2d.min() + y2d.max()) / 2.0
        x2d -= xc; y2d -= yc

        z_raw = rv[:,2]
        surface_z = z_raw.max()
        z_depth = surface_z - z_raw
        z_faces = np.mean(z_depth[vis_tri], axis=1)
        
        return x2d, y2d, z_depth, z_faces, vis_tri

    def get_view_params(self, view_name: str):
        if view_name in self._view_params_cache:
            return self._view_params_cache[view_name]

        rx_deg, ry_deg, rz_deg, screen_rot = _VIEW_ROTATIONS.get(view_name, (0,0,0,0))
        matrix = euler_matrix(*np.radians([rx_deg, ry_deg, rz_deg]))
        rv = trimesh.transformations.transform_points(self.mesh.vertices, matrix)

        x2d, y2d = rv[:,0].copy(), rv[:,1].copy()
        if screen_rot != 0:
            c, s = np.cos(np.radians(screen_rot)), np.sin(np.radians(screen_rot))
            x2d, y2d = x2d*c - y2d*s, x2d*s + y2d*c

        params = {
            'matrix':     matrix,
            'x_center':   (x2d.min() + x2d.max()) / 2.0,
            'y_center':   (y2d.min() + y2d.max()) / 2.0,
            'surface_z':  rv[:,2].max(),
            'total_depth': rv[:,2].max() - rv[:,2].min(),
            'screen_rot': screen_rot,
        }
        self._view_params_cache[view_name] = params
        return params

    def project_point_to_view(self, x_mesh, y_mesh, z_mesh, view_name: str):
        p = self.get_view_params(view_name)
        pt = np.array([[x_mesh, y_mesh, z_mesh]])
        rp = trimesh.transformations.transform_points(pt, p['matrix'])[0]
        px, py, pz = rp

        if p['screen_rot'] != 0:
            c, s = np.cos(np.radians(p['screen_rot'])), np.sin(np.radians(p['screen_rot']))
            px, py = px*c - py*s, px*s + py*c

        display_x = px - p['x_center']
        display_y = py - p['y_center']
        depth = p['surface_z'] - pz
        return float(display_x), float(display_y), float(depth)

    def get_view(self, view_name, rot=0):
        rx, ry, rz, _ = _VIEW_ROTATIONS.get(view_name, (0,0,0,0))
        return self.get_2d_projection(rx, ry, rz, rot)