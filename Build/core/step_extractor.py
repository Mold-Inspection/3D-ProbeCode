# core/step_extractor.py
import numpy as np
import math
import copy
from core.models import StepHole


# ---------------------------------------------------------------------------
# Problem 1 fix — sweep-angle threshold.
#
# sweep = arc_length / radius  (radians)
#   True hole boundary : sweep ≈ 2π (full circle) or at least π (half-circle)
#   Fillet / blend arc : sweep ≈ π/2 (90°) or less
# ---------------------------------------------------------------------------
_MIN_SWEEP_RAD = math.pi          # 180° — minimum arc sweep to be a hole boundary

# ---------------------------------------------------------------------------
# Merge tolerances.
#
# HALF-FACE MERGE (_PERP_FRAC_TOL, _EXTENT_TOL):
#   Many STEP exporters (SolidWorks etc.) split each cylindrical hole into two
#   180° half-face patches — a "left" and a "right" shell.  Each half-face
#   produces its own StepHole whose centre is the arc centroid of that half,
#   offset from the TRUE circle centre by exactly 2r/π perpendicular to the
#   hole axis.  The two half-face centroids are therefore separated by 4r/π.
#   We detect these pairs by checking that their perpendicular separation
#   matches 4r/π within _PERP_FRAC_TOL (15%), then merge them by averaging
#   the two centroid positions to recover the true circle centre.
#
# COUNTERBORE MERGE (_AXIS_TOL, _DEPTH_TOL):
#   A counterbored hole produces two concentric cylinder faces at the same XZ
#   location — an outer wide shallow bore and an inner narrow deep bore.
#   After the half-face merge these still appear as two separate entries.
#   We collapse them into one by detecting the containment relationship:
#   inner centre lies within outer radius (perpendicular distance + r_inner
#   < r_outer) and the two cylinders are adjacent along the axis.
# ---------------------------------------------------------------------------
_AXIS_TOL       = 0.02    # cos-angle tolerance for parallel axes
_EXTENT_TOL     = 0.5     # mm — axial extent match tolerance for half-face merge
_PERP_FRAC_TOL  = 0.15    # fractional tolerance on 4r/π separation
_DEPTH_TOL      = 1.0     # mm — max axial gap for counterbore adjacency


def _sweep_angle(edge) -> float:
    """Return the angular sweep (radians) of a CIRCLE-type edge."""
    arc_len = edge.Length()
    if arc_len <= 0:
        return 0.0
    try:
        r = edge.radius()
        if r and r > 0:
            return arc_len / r
    except (AttributeError, Exception):
        pass
    r_approx = arc_len / (2 * math.pi)
    if r_approx > 0:
        return arc_len / r_approx
    return 0.0


def _arc_radius(edge) -> float:
    """
    Return the TRUE geometric radius of a CIRCLE-type edge (mm).

    Problem 2 root-cause fix:
        edge.Length() / (2π) is only correct for a full 360° circle.
        For a 180° semicircle it returns HALF the true radius.
        edge.radius() returns the correct OCC geometric radius regardless
        of arc sweep angle.
    """
    try:
        r = edge.radius()
        if r and r > 0:
            return float(r)
    except (AttributeError, Exception):
        pass
    arc_len = edge.Length()
    if arc_len > 0:
        return arc_len / (2 * math.pi)
    return 0.0


def _merge_half_faces(holes: list) -> list:
    """
    Merge left/right half-face pairs into single holes with correct centres.
    """
    if not holes:
        return holes

    merged = [False] * len(holes)

    for i in range(len(holes)):
        if merged[i]:
            continue
        hi   = holes[i]
        axis = np.array(hi.axis)
        proj = lambda pt: float(np.dot(np.array(pt), axis))

        for j in range(i + 1, len(holes)):
            if merged[j]:
                continue
            hj = holes[j]

            # parallel axes?
            if abs(float(np.dot(hi.axis, hj.axis))) < 1 - _AXIS_TOL:
                continue

            # same radius?
            if abs(hi.radius - hj.radius) > 0.1:
                continue

            # same axial extent?
            ai0, ai1 = sorted([proj(hi.open_3d), proj(hi.deep_3d)])
            aj0, aj1 = sorted([proj(hj.open_3d), proj(hj.deep_3d)])
            if abs(ai0 - aj0) > _EXTENT_TOL or abs(ai1 - aj1) > _EXTENT_TOL:
                continue

            # perpendicular separation ≈ 4r/π ?
            mid_i  = (np.array(hi.open_3d) + np.array(hi.deep_3d)) / 2.0
            mid_j  = (np.array(hj.open_3d) + np.array(hj.deep_3d)) / 2.0
            delta  = mid_j - mid_i
            perp   = delta - float(np.dot(delta, axis)) * axis
            perp_d = float(np.linalg.norm(perp))

            expected = 4.0 * hi.radius / math.pi
            if abs(perp_d - expected) > expected * _PERP_FRAC_TOL:
                continue

            # Merge: true centre = average of the two arc centroids
            true_open  = (np.array(hi.open_3d) + np.array(hj.open_3d)) / 2.0
            true_deep  = (np.array(hi.deep_3d) + np.array(hj.deep_3d)) / 2.0
            hi.open_3d = tuple(true_open)
            hi.deep_3d = tuple(true_deep)
            hi.depth   = float(np.linalg.norm(true_deep - true_open))
            merged[j]  = True
            break

    return [h for i, h in enumerate(holes) if not merged[i]]


def _merge_counterbores(holes: list) -> list:
    """
    Collapse counterbore pairs (outer wide bore + inner narrow bore) into one.
    """
    if not holes:
        return holes

    merged_out = [False] * len(holes)

    for i in range(len(holes)):
        if merged_out[i]:
            continue
        for j in range(len(holes)):
            if i == j or merged_out[j]:
                continue
            hi, hj = holes[i], holes[j]

            # parallel axes?
            dot = abs(float(np.dot(hi.axis, hj.axis)))
            if dot < 1.0 - _AXIS_TOL:
                continue

            # containment: smaller inside larger?
            axis   = np.array(hi.axis)
            mid_i  = (np.array(hi.open_3d) + np.array(hi.deep_3d)) / 2.0
            mid_j  = (np.array(hj.open_3d) + np.array(hj.deep_3d)) / 2.0
            delta  = mid_j - mid_i
            perp   = delta - float(np.dot(delta, axis)) * axis
            perp_d = float(np.linalg.norm(perp))

            r_large = max(hi.radius_open, hj.radius_open)
            r_small = min(hi.radius_open, hj.radius_open)
            if perp_d + r_small >= r_large:
                continue

            # axially adjacent?
            proj   = lambda pt: float(np.dot(np.array(pt), axis))
            seg_i  = sorted([proj(hi.open_3d), proj(hi.deep_3d)])
            seg_j  = sorted([proj(hj.open_3d), proj(hj.deep_3d)])
            gap    = max(seg_j[0] - seg_i[1], seg_i[0] - seg_j[1])
            if gap > _DEPTH_TOL:
                continue

            # Merge: keep inner, extend to outer's open end
            if hi.radius_open <= hj.radius_open:
                inner, outer, outer_idx = hi, hj, j
            else:
                inner, outer, outer_idx = hj, hi, i
                merged_out[i] = True

            inner.open_3d = tuple(np.array(outer.open_3d))
            inner.depth   = float(
                np.linalg.norm(np.array(inner.deep_3d) - np.array(inner.open_3d)))
            merged_out[outer_idx] = True
            break

    return [h for i, h in enumerate(holes) if not merged_out[i]]


class StepExtractor:
    """Extract cylindrical hole geometry from STEP B-Rep data."""

    def __init__(self):
        self._step_holes_cache = []

    def extract(self, step_data, mesh_centroid):
        if step_data is None:
            return []

        cx_off, cy_off, cz_off = mesh_centroid
        holes = []
        seen  = {}

        for face in step_data.faces().vals():
            try:
                if face.geomType() not in ('CYLINDER', 'CONE'):
                    continue

                raw_circle_edges = [e for e in face.Edges()
                                    if e.geomType() == 'CIRCLE']

                circle_edges = [e for e in raw_circle_edges
                                if _sweep_angle(e) >= _MIN_SWEEP_RAD]

                if len(circle_edges) < 2:
                    continue

                circle_data = []
                for edge in circle_edges:
                    c  = edge.Center()
                    ex = float(c.x) - cx_off
                    ey = float(c.y) - cy_off
                    ez = float(c.z) - cz_off
                    r  = _arc_radius(edge)
                    circle_data.append((ex, ey, ez, r))

                if len(circle_data) < 2:
                    continue

                c0   = np.array(circle_data[0][:3])
                c1   = np.array(circle_data[-1][:3])
                diff = c1 - c0
                dist = float(np.linalg.norm(diff))
                if dist < 0.05:
                    continue

                axis_vec = diff / dist
                ax, ay, az = axis_vec
                circle_data.sort(
                    key=lambda d: ax * d[0] + ay * d[1] + az * d[2])

                end_a, end_b = tuple(circle_data[0][:3]), tuple(circle_data[-1][:3])
                r_a,   r_b   = circle_data[0][3],         circle_data[-1][3]

                face_depth = float(np.linalg.norm(np.array(end_b) - np.array(end_a)))
                if face_depth < 0.1:
                    continue

                mid = (np.array(end_a) + np.array(end_b)) / 2.0
                key = (round(mid[0], 1), round(mid[1], 1), round(mid[2], 1),
                       round(max(r_a, r_b), 2))

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

        holes = _merge_half_faces(holes)
        holes = _merge_counterbores(holes)

        self._step_holes_cache = holes
        print(f"[geo] STEP holes extracted: {len(holes)}")
        return holes

    # ------------------------------------------------------------------
    def get_step_holes_in_view(self, projector, view_name: str,
                                screen_rot: int = 0, mesh=None):
        """
        Return the subset of cached STEP holes visible from *view_name*.
        Uses exact 3D ray-casting to determine if a hole is occluded by the mesh.
        """
        if not self._step_holes_cache:
            return []

        p      = projector.get_view_params(view_name, screen_rot)
        matrix = p['matrix']

        # ------------------------------------------------------------------
        # คำนวณหาทิศทางที่พุ่งตรงเข้าหาผู้ใช้ (Viewer Direction) ในพิกัด 3D ดั้งเดิม
        # กล้องมองลงไปที่แนวแกน -Z ดังนั้นผู้ใช้จึงอยู่ที่ +Z 
        # การคูณ Matrix Transpose คือการแปลงเวกเตอร์ [0, 0, 1] กลับไปยังพิกัดต้นฉบับ
        # ------------------------------------------------------------------
        dir_to_viewer = matrix[:3, :3].T @ np.array([0.0, 0.0, 1.0])
        dir_to_viewer = dir_to_viewer / np.linalg.norm(dir_to_viewer) # Normalize

        MIN_DEPTH = 0.1  # ใช้เช็คแค่ความลึกจริงขั้นต่ำ (ปัดตกรูที่ตื้นจน Error)

        result = []
        for h in self._step_holes_cache:
            dx_a, dy_a, d_a = projector.project_point_to_view(
                *h.open_3d, view_name, screen_rot)
            dx_b, dy_b, d_b = projector.project_point_to_view(
                *h.deep_3d, view_name, screen_rot)

            # เลือกฝั่งที่ตื้นกว่าให้เป็น "ปากรู (Mouth)" จากมุมมองปัจจุบัน
            if d_a <= d_b:
                open_depth, deep_depth = d_a, d_b
                display_x, display_y   = dx_a, dy_a
                r_open, r_deep         = h.radius_open, h.radius_deep
                open_3d, deep_3d       = h.open_3d, h.deep_3d
            else:
                open_depth, deep_depth = d_b, d_a
                display_x, display_y   = dx_b, dy_b
                r_open, r_deep         = h.radius_deep, h.radius_open
                open_3d, deep_3d       = h.deep_3d, h.open_3d

            actual_depth = deep_depth - open_depth
            if actual_depth < MIN_DEPTH:
                continue

            # ------------------------------------------------------------------
            # OCCLUSION RAY-CAST TEST (ยิงเลเซอร์เช็คว่าโดนเนื้อชิ้นงานบังไหม)
            # ------------------------------------------------------------------
            if mesh is not None:
                # ดันจุดกำเนิดเลเซอร์ (Ray Origin) ลอยขึ้นมาจากปากรู 0.1 มม. 
                # ป้องกันไม่ให้เลเซอร์ชนขอบตัวเอง (Self-intersection)
                ray_origin = np.array(open_3d) + (dir_to_viewer * 0.1)
                
                # ยิงเลเซอร์พุ่งเข้าหาจอ 1 เส้น
                hit = mesh.ray.intersects_any(
                    ray_origins=[ray_origin],
                    ray_directions=[dir_to_viewer]
                )
                
                if hit[0]:
                    # ถ้าชน (True) แปลว่ามีเนื้อ Mesh ขวางทางอยู่ = รูโดนบัง (ข้ามรูนี้ไป)
                    continue
            # ------------------------------------------------------------------

            hc             = copy.copy(h)
            hc.open_3d     = open_3d
            hc.deep_3d     = deep_3d
            hc.radius_open = r_open
            hc.radius_deep = r_deep
            hc.radius      = r_open
            hc.display_x   = display_x
            hc.display_y   = display_y
            hc.depth_top   = open_depth
            hc.depth_bot   = deep_depth
            hc.depth       = actual_depth
            result.append(hc)

        # จัดเรียง ID รูให้สวยงาม
        result.sort(key=lambda h: (-round(h.display_y / 5.0), h.display_x))
        for i, h in enumerate(result):
            h._id = i + 1

        print(f"[geo] {view_name} view (rot={screen_rot}°) — visible holes: {len(result)}")
        return result