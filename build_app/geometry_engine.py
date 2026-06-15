import trimesh
import numpy as np
from trimesh.transformations import euler_matrix
import os
import cadquery as cq

# ══════════════════════════════════════════════════════════════════════════════
# Coordinate systems:
#   mesh space  : STEP space − mesh_centroid
#   view space  : mesh rotated by view matrix, then x/y centered,
#                 z_depth = surface_z − z_rotated  (0 = top surface, positive = deeper)
# ══════════════════════════════════════════════════════════════════════════════

_VIEW_ROTATIONS = {
    'Top':    (0,    0,   0,   0),
    'Bottom': (180,  0,   0,   0),
    'Front':  (-90,  0,   0,   0),
    'Back':   (90,   0, 180,   0),
    'Left':   (-90,  0,  90,   0),
    'Right':  (-90,  0, -90,   0),
}


class StepHole:
    """รูทรงกระบอกจาก STEP B-Rep — เก็บ 3D coords เต็มของปากรู/ก้นรู"""

    def __init__(self, open_3d, deep_3d, radius_open, radius_deep, axis_vec):
        """
        Parameters
        ----------
        open_3d      : (x, y, z) ใน mesh space ของ ปากรู
        deep_3d      : (x, y, z) ใน mesh space ของ ก้นรู
        radius_open  : รัศมีที่ปากรู (mm)
        radius_deep  : รัศมีที่ก้นรู (mm) — อาจต่างกันสำหรับ cone/taper
        axis_vec     : (ax, ay, az) unit vector ตามแกนรู
        """
        self.open_3d     = tuple(open_3d)
        self.deep_3d     = tuple(deep_3d)
        self.radius_open = float(radius_open)
        self.radius_deep = float(radius_deep)
        self.radius      = float(radius_open)   # compat: ใช้ radius ปากรู
        self.axis        = axis_vec
        self.depth       = float(np.linalg.norm(
                               np.array(deep_3d) - np.array(open_3d)))

        mid = (np.array(open_3d) + np.array(deep_3d)) / 2.0
        self.cx_mesh = float(mid[0])
        self.cy_mesh = float(mid[1])
        self.cz_mesh = float(mid[2])

        self.display_x = None
        self.display_y = None
        self.depth_top = None
        self.depth_bot = None

    def radius_at(self, t: float) -> float:
        """radius ที่ตำแหน่ง t ∈ [0,1] ระหว่างปากรู (0) → ก้นรู (1)"""
        return self.radius_open + t * (self.radius_deep - self.radius_open)


class MoldGeometry:
    def __init__(self, filepath=None):
        self.mesh      = None
        self.triangles = None
        self.step_data = None

        self._mesh_centroid      = np.zeros(3)
        self._step_holes_cache   = []
        self._view_params_cache  = {}   # cache projection params per view

        if filepath:
            self.load_file(filepath)

    # ═══════════════════════════════════════════════════════════════════════
    # 1. FILE LOADING
    # ═══════════════════════════════════════════════════════════════════════
    def load_file(self, filepath):
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
            self.mesh      = trimesh.load(filepath)
            self.step_data = None
            print("Loaded STL — calculations use mesh approximation")

        self._mesh_centroid = self.mesh.centroid.copy()
        self.mesh.apply_translation(-self._mesh_centroid)
        self.triangles = self.mesh.faces
        self._view_params_cache = {}

        self._step_holes_cache = self._extract_step_holes()

    # ═══════════════════════════════════════════════════════════════════════
    # 2. 2D PROJECTION (ไม่เปลี่ยน)
    # ═══════════════════════════════════════════════════════════════════════
    def get_physical_dimensions(self):
        return self.mesh.extents if self.mesh is not None else (0, 0, 0)

    def get_2d_projection(self, rx_deg=0, ry_deg=0, rz_deg=0, screen_rot=0):
        matrix           = euler_matrix(*np.radians([rx_deg, ry_deg, rz_deg]))
        rv               = trimesh.transformations.transform_points(self.mesh.vertices, matrix)
        rn               = np.dot(self.mesh.face_normals, matrix[:3, :3].T)

        v0, v1, v2 = rv[self.triangles[:,0]], rv[self.triangles[:,1]], rv[self.triangles[:,2]]
        area = ((v1[:,0]-v0[:,0])*(v2[:,1]-v0[:,1])
              - (v1[:,1]-v0[:,1])*(v2[:,0]-v0[:,0]))
        front = (rn[:,2] > 0.001) & (np.abs(area) > 1e-5)
        if front.sum() == 0:
            front = (rn[:,2] < -0.001) & (np.abs(area) > 1e-5)
        vis_tri = self.triangles[front]

        x2d, y2d = rv[:,0].copy(), rv[:,1].copy()
        if screen_rot != 0:
            c, s  = np.cos(np.radians(screen_rot)), np.sin(np.radians(screen_rot))
            x2d, y2d = x2d*c - y2d*s, x2d*s + y2d*c

        xc = (x2d.min() + x2d.max()) / 2.0
        yc = (y2d.min() + y2d.max()) / 2.0
        x2d -= xc; y2d -= yc

        z_raw     = rv[:,2]
        surface_z = z_raw.max()
        z_depth   = surface_z - z_raw
        z_faces   = np.mean(z_depth[vis_tri], axis=1)
        return x2d, y2d, z_depth, z_faces, vis_tri

    def get_top_view(self,    rot=0): return self.get_2d_projection(0,    0,   0,   rot)
    def get_bottom_view(self, rot=0): return self.get_2d_projection(180,  0,   0,   rot)
    def get_front_view(self,  rot=0): return self.get_2d_projection(-90,  0,   0,   rot)
    def get_back_view(self,   rot=0): return self.get_2d_projection(90,   0, 180,   rot)
    def get_left_view(self,   rot=0): return self.get_2d_projection(-90,  0,  90,   rot)
    def get_right_view(self,  rot=0): return self.get_2d_projection(-90,  0, -90,   rot)

    # ═══════════════════════════════════════════════════════════════════════
    # 3. STEP B-REP HOLE EXTRACTION
    # ═══════════════════════════════════════════════════════════════════════
    def _extract_step_holes(self) -> list:
        if self.step_data is None:
            return []

        import math

        cx_off, cy_off, cz_off = self._mesh_centroid
        holes  = []
        seen   = {}

        for face in self.step_data.faces().vals():
            try:
                # ── ใช้ CadQuery API โดยตรง — ไม่ต้อง import OCC/OCP ──────────
                if face.geomType() not in ('CYLINDER', 'CONE'):
                    continue

                # หา circular edges (ขอบบน/ล่างของรู)
                circle_edges = [e for e in face.Edges()
                                if e.geomType() == 'CIRCLE']
                if len(circle_edges) < 2:
                    continue

                circle_data = []
                for edge in circle_edges:
                    c  = edge.Center()          # Vector (ใน STEP space)
                    ex = float(c.x) - cx_off
                    ey = float(c.y) - cy_off
                    ez = float(c.z) - cz_off
                    # radius จาก edge.Length() / 2π (ทำงานได้ทุกทิศทาง)
                    r  = edge.Length() / (2 * math.pi)
                    circle_data.append((ex, ey, ez, r))

                if len(circle_data) < 2:
                    continue

                # หา axis direction จากสองศูนย์กลางวง
                c0 = np.array(circle_data[0][:3])
                c1 = np.array(circle_data[-1][:3])
                diff = c1 - c0
                dist = float(np.linalg.norm(diff))
                if dist < 0.05:
                    continue   # degenerate
                axis_vec = diff / dist
                ax, ay, az = axis_vec

                # เรียง circle_data ตาม projection บน axis
                circle_data.sort(key=lambda d:
                    ax*d[0] + ay*d[1] + az*d[2])

                end_a  = tuple(circle_data[0][:3])
                end_b  = tuple(circle_data[-1][:3])
                r_a    = circle_data[0][3]    # radius ที่ end_a
                r_b    = circle_data[-1][3]   # radius ที่ end_b

                # กรองเฉพาะรูที่เจาะในแนวแกน Z เท่านั้น
                # รูที่ด้านข้าง (เจาะแนว X หรือ Y) จะถูกกรองออก
                # threshold 0.70 ≈ cos(45°) — รองรับชิ้นงานที่วางเอียงเล็กน้อย
                if abs(az) < 0.70:
                    continue

                face_depth = float(np.linalg.norm(
                    np.array(end_b) - np.array(end_a)))
                if face_depth < 0.1:
                    continue

                mid = (np.array(end_a) + np.array(end_b)) / 2.0
                key = (round(mid[0], 1), round(mid[1], 1),
                       round(mid[2], 1), round(max(r_a, r_b), 2))

                if key in seen:
                    idx = seen[key]
                    if face_depth > holes[idx].depth:
                        holes[idx] = StepHole(end_a, end_b, r_a, r_b,
                                              (ax, ay, az))
                    continue

                seen[key] = len(holes)
                holes.append(StepHole(end_a, end_b, r_a, r_b, (ax, ay, az)))

            except Exception:
                continue

        print(f"[geo] STEP holes extracted: {len(holes)}")
        return holes

    # ═══════════════════════════════════════════════════════════════════════
    # 4. PROJECT POINT TO VIEW SPACE
    # ═══════════════════════════════════════════════════════════════════════
    def _get_view_params(self, view_name: str):
        """Cache projection params per view"""
        if view_name in self._view_params_cache:
            return self._view_params_cache[view_name]

        rx_deg, ry_deg, rz_deg, screen_rot = _VIEW_ROTATIONS.get(view_name, (0,0,0,0))
        matrix = euler_matrix(*np.radians([rx_deg, ry_deg, rz_deg]))
        rv     = trimesh.transformations.transform_points(self.mesh.vertices, matrix)

        x2d, y2d = rv[:,0].copy(), rv[:,1].copy()
        if screen_rot != 0:
            c, s  = np.cos(np.radians(screen_rot)), np.sin(np.radians(screen_rot))
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

    def project_point_to_view(self, x_mesh, y_mesh, z_mesh,
                               view_name: str):
        """แปลง mesh-space point → (display_x, display_y, depth) ใน view space"""
        p  = self._get_view_params(view_name)
        pt = np.array([[x_mesh, y_mesh, z_mesh]])
        rp = trimesh.transformations.transform_points(pt, p['matrix'])[0]
        px, py, pz = rp

        if p['screen_rot'] != 0:
            c, s  = np.cos(np.radians(p['screen_rot'])), np.sin(np.radians(p['screen_rot']))
            px, py = px*c - py*s, px*s + py*c

        display_x = px - p['x_center']
        display_y = py - p['y_center']
        depth     = p['surface_z'] - pz   # ≥ 0 เสมอ
        return float(display_x), float(display_y), float(depth)

    # ═══════════════════════════════════════════════════════════════════════
    # 5. STEP HOLES IN VIEW  ← KEY FIX
    # ═══════════════════════════════════════════════════════════════════════
    def get_step_holes_in_view(self, view_name: str) -> list:
        """
        คืนเฉพาะรูที่ "ปากรูหันมาหากล้อง" ใน view ที่ระบุ

        Logic:
        - Project ทั้งสอง end ของแต่ละรูลงบน view space
        - end ที่ depth น้อยกว่า = ใกล้กล้องกว่า = ปากรู
        - กรอง: ปากรูต้องอยู่ใกล้ผิวของชิ้นงาน (depth_open < threshold)
        - กรอง: ความลึกของรูต้องมีนัยสำคัญ
        """
        p = self._get_view_params(view_name)
        part_total_depth = p['total_depth']

        # ปากรูต้องอยู่ภายใน 3% ของความหนาชิ้นงานจากผิว
        # (ลดจาก 12% เพื่อไม่ให้ fillet/โค้งมุมผ่าน filter)
        OPEN_THRESHOLD = max(part_total_depth * 0.03, 1.5)
        MIN_DEPTH      = max(part_total_depth * 0.05, 0.5)

        import copy
        result = []
        for h in self._step_holes_cache:
            # project ทั้งสอง end
            dx_a, dy_a, d_a = self.project_point_to_view(*h.open_3d, view_name)
            dx_b, dy_b, d_b = self.project_point_to_view(*h.deep_3d, view_name)

            # เลือก end ที่ depth น้อยกว่า = ปากรู (opening facing camera)
            if d_a <= d_b:
                open_depth   = d_a;        deep_depth   = d_b
                display_x    = dx_a;       display_y    = dy_a
                r_open       = h.radius_open
                r_deep       = h.radius_deep
                open_3d      = h.open_3d
                deep_3d      = h.deep_3d
            else:
                open_depth   = d_b;        deep_depth   = d_a
                display_x    = dx_b;       display_y    = dy_b
                r_open       = h.radius_deep   # swap
                r_deep       = h.radius_open
                open_3d      = h.deep_3d       # swap
                deep_3d      = h.open_3d

            actual_depth = deep_depth - open_depth

            # ── Filter 1: ปากรูต้องอยู่ใกล้ผิว ──────────────────────────────
            if open_depth > OPEN_THRESHOLD:
                continue

            # ── Filter 2: ต้องมีความลึกจริง ──────────────────────────────────
            if actual_depth < MIN_DEPTH:
                continue

            # สร้าง copy แล้ว set ทุก attribute
            hc              = copy.copy(h)
            hc.open_3d      = open_3d
            hc.deep_3d      = deep_3d
            hc.radius_open  = r_open
            hc.radius_deep  = r_deep
            hc.radius       = r_open
            hc.display_x    = display_x
            hc.display_y    = display_y
            hc.depth_top    = open_depth
            hc.depth_bot    = deep_depth
            hc.depth        = actual_depth
            result.append(hc)

        # เรียงตาม Y ลดลงก่อน (บนก่อน) แล้วตาม X
        result.sort(key=lambda h: (-round(h.display_y / 5.0), h.display_x))
        for i, h in enumerate(result):
            h._id = i + 1   # assign ชั่วคราว (ui.py จะ set HoleFeature.id แทน)

        print(f"[geo] {view_name} view — visible holes: {len(result)}")
        return result

    # ═══════════════════════════════════════════════════════════════════════
    # 6. PATH PLANNING
    # ═══════════════════════════════════════════════════════════════════════
    def get_probe_path_layers(self, hole: StepHole, n_layers: int,
                               view_name: str) -> list:
        """
        คำนวณ probing layers จาก B-Rep — interpolate ทั้ง xyz + radius ตามรูปทรงจริง

        สำหรับรูเอียง/taper: center XY และ radius เปลี่ยนตาม t
        คืน list of dict: {z_display, x_display, y_display, radius}
        เรียงจากปากรู → ก้นรู (ไม่รวม endpoint เพื่อหลีกเลี่ยงชนขอบ)
        """
        t_vals = np.linspace(0.0, 1.0, n_layers + 2)[1:-1]
        o = np.array(hole.open_3d)
        d = np.array(hole.deep_3d)

        layers = []
        for t in t_vals:
            # interpolate ตำแหน่งกึ่งกลาง layer ใน mesh space
            pt = o + t * (d - o)

            # project center point → display coords (ได้ทั้ง x, y, depth)
            dx, dy, depth = self.project_point_to_view(*pt, view_name)

            # interpolate radius ตามรูปทรงจริง (cylinder → คงที่, cone → เปลี่ยน)
            r_layer = hole.radius_at(t)

            layers.append({
                'z_display': depth,
                'x_display': dx,      # center X ของ layer นี้ (เปลี่ยนถ้ารูเอียง)
                'y_display': dy,      # center Y ของ layer นี้
                'radius':    r_layer, # radius ของ layer นี้ (เปลี่ยนถ้า taper)
            })
        return layers

    # ═══════════════════════════════════════════════════════════════════════
    # 7. LEGACY
    # ═══════════════════════════════════════════════════════════════════════
    def calculate_optimal_z_height(self, laser_ref):
        if self.mesh is None:
            return "Please load an STL file first."
        mold_thickness   = self.mesh.extents[2]
        z_raw            = self.mesh.vertices[:, 2]
        max_pocket_depth = np.max(np.max(z_raw) - z_raw)
        mid_scan_z       = mold_thickness - (max_pocket_depth / 2)
        rz               = mid_scan_z + laser_ref
        clearance        = rz - mold_thickness
        if clearance <= 5.0:
            return f"⚠️ ระวังชน! แนะนำคาน Z: {rz:.1f} mm (ห่างชิ้นงาน {clearance:.1f} mm)"
        return f"✅ Setup Z-Height: {rz:.1f} mm"
