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

    Root cause:
        STEP exporters split each cylindrical hole into two 180° half-face
        patches.  edge.Center() on a 180° arc returns the arc centroid, which
        is offset from the TRUE circle centre by 2r/π along the perpendicular
        direction.  The two half-faces therefore produce centroids that are
        4r/π apart, and their deduplication keys never match.

    Fix:
        For each pair of holes with:
          • parallel axes
          • same radius (within 0.1 mm)
          • same axial extent (open and deep positions match within _EXTENT_TOL)
          • perpendicular centroid separation ≈ 4r/π  (±_PERP_FRAC_TOL)
        → average their open_3d and deep_3d to recover the true circle centre.
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

    A counterbore pair satisfies:
      1. Parallel axes.
      2. Inner hole centre lies inside outer hole radius (perp_dist + r_inner
         < r_outer).
      3. The two cylinders are axially adjacent (gap ≤ _DEPTH_TOL).

    The inner hole is kept; its open_3d is extended to the outer hole's open
    end so the depth covers the full counterbore stack.
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

                # Bug Fix A (preserved): accept ALL CIRCLE edges.
                # Problem 1 filter: drop arcs with sweep < π (180°).
                raw_circle_edges = [e for e in face.Edges()
                                    if e.geomType() == 'CIRCLE']

                circle_edges = [e for e in raw_circle_edges
                                if _sweep_angle(e) >= _MIN_SWEEP_RAD]

                if len(circle_edges) < 2:
                    continue

                # Problem 2 fix: use _arc_radius() for correct geometric radius.
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

                # Bug Fix B (preserved): Z-axis filter removed.

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

        # ------------------------------------------------------------------
        # Post-pass 1: merge left/right half-face pairs → true circle centres.
        # Post-pass 2: merge counterbore outer+inner → single hole entry.
        # ------------------------------------------------------------------
        holes = _merge_half_faces(holes)
        holes = _merge_counterbores(holes)

        self._step_holes_cache = holes
        print(f"[geo] STEP holes extracted: {len(holes)}")
        return holes

    # ------------------------------------------------------------------
    def get_step_holes_in_view(self, projector, view_name: str,
                                screen_rot: int = 0):
        """
        Return the subset of cached STEP holes visible from *view_name*.

        Visibility rule (replaces the old hard OPEN_THRESHOLD):
        A hole is visible when its open end faces toward the observer AND
        no solid mesh wall covers the hole opening.  Concretely:

          1. The hole must have a meaningful internal depth
             (actual_depth >= MIN_DEPTH).

          2. The open end must be closer to the observer than the deep end
             (open_depth < deep_depth) — this is the axis-direction test.

          3. The open end must not be buried behind the far wall of the part.
             We require open_depth < total_depth * _BURIED_FRAC.

          4. Occlusion check — no solid surface sits in front of the hole
             opening.  We sample the mesh depth at the hole's display (X, Y)
             position using the projector's face-depth grid and require that
             the nearest mesh surface depth at that location is NOT
             significantly shallower than open_depth.  If it is, the hole is
             covered by solid material and must not be shown.

             This correctly handles both failure modes from the images:
               • Image 1 (partial detection): holes on the left/centre of the
                 part were rejected because OPEN_THRESHOLD was too tight.
                 Now every exposed hole passes regardless of its XY position.
               • Image 2 (recessed holes): holes that start inside a pocket
                 have open_depth >> 0 but are still genuinely open to the
                 observer because the pocket has been cut away.  The occlusion
                 check confirms no mesh covers their opening, so they pass.
        """
        if not self._step_holes_cache:
            return []

        p                = projector.get_view_params(view_name, screen_rot)
        part_total_depth = p['total_depth']

        # --- tuneable constants -----------------------------------------
        # Minimum hole depth to bother showing (absolute + relative guard).
        MIN_DEPTH      = max(part_total_depth * 0.02, 0.3)

        # A hole whose open end is deeper than this fraction of total part
        # depth is considered buried inside the far wall and is hidden.
        # 0.95 is intentionally generous — it only rejects holes whose open
        # end is within 5 % of the back wall, i.e. genuinely inaccessible.
        _BURIED_FRAC   = 0.95

        # When comparing the hole-opening depth to the nearest mesh surface
        # depth at the same XY: if the mesh is shallower by more than
        # _OCCLUSION_TOL the hole is considered covered (occluded).
        # A positive tolerance lets slightly recessed pocket-floor holes
        # still be detected even if the mesh triangulation is not perfectly
        # flush with the STEP circle plane.
        _OCCLUSION_TOL = max(part_total_depth * 0.06, 1.5)   # mm

        # Build a fast mesh-depth lookup from the 2-D projection.
        # get_view() returns (x2d, y2d, z_depth_verts, z_depth_faces, vis_tri).
        # z_depth_faces[i] = depth of face i from the observer (0 = surface).
        # We store triangle centroids + face depths for the lookup.
        try:
            x2d, y2d, z_vert, z_face, vis_tri = projector.get_view(
                view_name, screen_rot)
            _has_mesh = (len(vis_tri) > 0)
        except Exception:
            _has_mesh = False

        if _has_mesh:
            # Pre-compute triangle centroids in 2-D display space
            tri_cx = (x2d[vis_tri[:, 0]] + x2d[vis_tri[:, 1]] + x2d[vis_tri[:, 2]]) / 3.0
            tri_cy = (y2d[vis_tri[:, 0]] + y2d[vis_tri[:, 1]] + y2d[vis_tri[:, 2]]) / 3.0
            tri_dz = z_face   # depth of each visible face

        def _nearest_mesh_depth(cx, cy, search_r):
            """
            Return the minimum (shallowest) mesh surface depth within
            search_r display-units of (cx, cy).  Returns None if no
            triangles are found nearby.
            """
            if not _has_mesh:
                return None
            dists = np.hypot(tri_cx - cx, tri_cy - cy)
            mask  = dists < search_r
            if not np.any(mask):
                return None
            return float(np.min(tri_dz[mask]))

        result = []
        for h in self._step_holes_cache:
            dx_a, dy_a, d_a = projector.project_point_to_view(
                *h.open_3d, view_name, screen_rot)
            dx_b, dy_b, d_b = projector.project_point_to_view(
                *h.deep_3d, view_name, screen_rot)

            # Orient so that open end is the one closer to the observer.
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

            # --- filter 1: meaningful depth ---
            if actual_depth < MIN_DEPTH:
                continue

            # --- filter 2: open end must face observer (not behind far wall) ---
            if open_depth >= part_total_depth * _BURIED_FRAC:
                continue

            # --- filter 3: occlusion check ---
            # Sample the mesh depth at the hole centre with a search radius
            # of r_open (display units ≈ mm in orthographic projection).
            # If the nearest mesh surface is shallower than the hole opening
            # by more than _OCCLUSION_TOL, solid material covers the hole.
            search_r       = max(r_open * 0.8, 2.0)
            mesh_depth_min = _nearest_mesh_depth(display_x, display_y, search_r)

            if mesh_depth_min is not None:
                # mesh_depth_min < open_depth − tol  →  surface covers hole
                if mesh_depth_min < open_depth - _OCCLUSION_TOL:
                    continue

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

        result.sort(key=lambda h: (-round(h.display_y / 5.0), h.display_x))
        for i, h in enumerate(result):
            h._id = i + 1

        print(f"[geo] {view_name} view (rot={screen_rot}°) — visible holes: {len(result)}")
        return result
