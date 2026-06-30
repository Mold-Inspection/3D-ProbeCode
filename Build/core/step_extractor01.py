# core/step_extractor.py
# VERSION: 02
# CHANGE LOG (v01 -> v02):
#   - Added DEBUG instrumentation only. No geometry/merge logic changed.
#   - Logs hole counts at every pipeline stage: raw face scan, pre-merge,
#     post half-face merge, post counterbore merge.
#   - Logs WHY a candidate face is rejected (geomType, edge count, sweep
#     angle, dedup key collision) so we can pinpoint where a hole disappears.
#   - Logs every half-face merge and counterbore merge event with the
#     coordinates/radii involved, so a wrongly-merged or wrongly-dropped
#     hole can be traced directly from the console output.
#
# Toggle DEBUG = False to silence all of this once the root cause is found.
import numpy as np
import math
import copy
from core.models import StepHole

DEBUG = True


def _dbg(msg):
    if DEBUG:
        print(f"[step_extractor] {msg}")


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

            _dbg(f"HALF-FACE MERGE: hole[{i}] mid={tuple(np.round(mid_i,2))} "
                 f"r={hi.radius:.2f}  +  hole[{j}] mid={tuple(np.round(mid_j,2))} "
                 f"r={hj.radius:.2f}  perp_d={perp_d:.3f} (expected={expected:.3f}) "
                 f"-> merged centre={tuple(np.round((true_open+true_deep)/2,2))}")

            hi.open_3d = tuple(true_open)
            hi.deep_3d = tuple(true_deep)
            hi.depth   = float(np.linalg.norm(true_deep - true_open))
            merged[j]  = True
            break

    result = [h for i, h in enumerate(holes) if not merged[i]]
    _dbg(f"half-face merge: {len(holes)} -> {len(result)} holes "
         f"({sum(merged)} consumed)")
    return result


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

    NOTE (debug pass): this loop has a known directional-asymmetry risk —
    the inner `j` loop scans from 0 (not i+1), and `break`s out of the inner
    loop on first match. With holes that are mirror-symmetric and similar in
    radius, this can cause a merge decision to consume a hole that should
    have remained independent. The _dbg() calls below log every candidate
    pair considered AND every merge actually performed, so we can see
    exactly which holes triggered (or narrowly avoided) a false merge.
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

            if DEBUG:
                _dbg(f"counterbore candidate: hole[{i}] mid={tuple(np.round(mid_i,2))} "
                     f"r_open={hi.radius_open:.2f}  vs  hole[{j}] mid={tuple(np.round(mid_j,2))} "
                     f"r_open={hj.radius_open:.2f}  perp_d={perp_d:.3f}  "
                     f"containment_check={perp_d + r_small:.3f} < {r_large:.3f} ? "
                     f"{perp_d + r_small < r_large}")

            if perp_d + r_small >= r_large:
                continue

            # axially adjacent?
            proj   = lambda pt: float(np.dot(np.array(pt), axis))
            seg_i  = sorted([proj(hi.open_3d), proj(hi.deep_3d)])
            seg_j  = sorted([proj(hj.open_3d), proj(hj.deep_3d)])
            gap    = max(seg_j[0] - seg_i[1], seg_i[0] - seg_j[1])

            _dbg(f"  axial gap={gap:.3f}  (tol={_DEPTH_TOL})")

            if gap > _DEPTH_TOL:
                continue

            # Merge: keep inner, extend to outer's open end
            if hi.radius_open <= hj.radius_open:
                inner, outer, outer_idx = hi, hj, j
            else:
                inner, outer, outer_idx = hj, hi, i
                merged_out[i] = True

            _dbg(f"COUNTERBORE MERGE: keeping hole[{i if inner is hi else j}] "
                 f"(inner, r={inner.radius_open:.2f}) , dropping hole[{outer_idx}] "
                 f"(outer, r={outer.radius_open:.2f}) at mid="
                 f"{tuple(np.round((mid_i if outer is hi else mid_j),2))}")

            inner.open_3d = tuple(np.array(outer.open_3d))
            inner.depth   = float(
                np.linalg.norm(np.array(inner.deep_3d) - np.array(inner.open_3d)))
            merged_out[outer_idx] = True
            break

    result = [h for i, h in enumerate(holes) if not merged_out[i]]
    _dbg(f"counterbore merge: {len(holes)} -> {len(result)} holes "
         f"({sum(merged_out)} consumed)")
    return result


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

        total_faces       = 0
        rejected_geomtype = 0
        rejected_edges    = 0
        rejected_sweep    = 0
        rejected_dist     = 0
        rejected_depth    = 0
        rejected_dup      = 0
        rejected_other    = 0

        for face in step_data.faces().vals():
            total_faces += 1
            try:
                if face.geomType() not in ('CYLINDER', 'CONE'):
                    rejected_geomtype += 1
                    continue

                # Bug Fix A (preserved): accept ALL CIRCLE edges.
                # Problem 1 filter: drop arcs with sweep < π (180°).
                raw_circle_edges = [e for e in face.Edges()
                                    if e.geomType() == 'CIRCLE']

                if len(raw_circle_edges) < 2:
                    rejected_edges += 1
                    continue

                circle_edges = [e for e in raw_circle_edges
                                if _sweep_angle(e) >= _MIN_SWEEP_RAD]

                if len(circle_edges) < 2:
                    sweeps = [round(math.degrees(_sweep_angle(e)), 1)
                              for e in raw_circle_edges]
                    _dbg(f"REJECTED (sweep too small) face#{total_faces}: "
                         f"geomType={face.geomType()}  "
                         f"raw_edges={len(raw_circle_edges)}  "
                         f"sweeps_deg={sweeps}  (need >= 180.0 on >=2 edges)")
                    rejected_sweep += 1
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
                    rejected_edges += 1
                    continue

                c0   = np.array(circle_data[0][:3])
                c1   = np.array(circle_data[-1][:3])
                diff = c1 - c0
                dist = float(np.linalg.norm(diff))
                if dist < 0.05:
                    _dbg(f"REJECTED (degenerate axis dist={dist:.4f}) "
                         f"face#{total_faces}  geomType={face.geomType()}  "
                         f"centre~{tuple(np.round(c0,2))}")
                    rejected_dist += 1
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
                    _dbg(f"REJECTED (face_depth too small={face_depth:.4f}) "
                         f"face#{total_faces}  geomType={face.geomType()}  "
                         f"r=({r_a:.2f},{r_b:.2f})  centre~{tuple(np.round((np.array(end_a)+np.array(end_b))/2,2))}")
                    rejected_depth += 1
                    continue

                mid = (np.array(end_a) + np.array(end_b)) / 2.0
                key = (round(mid[0], 1), round(mid[1], 1), round(mid[2], 1),
                       round(max(r_a, r_b), 2))

                if key in seen:
                    idx = seen[key]
                    _dbg(f"DEDUP KEY COLLISION face#{total_faces}: key={key}  "
                         f"existing_depth={holes[idx].depth:.2f}  "
                         f"new_face_depth={face_depth:.2f}  "
                         f"-> {'REPLACED' if face_depth > holes[idx].depth else 'kept existing'}")
                    rejected_dup += 1
                    if face_depth > holes[idx].depth:
                        holes[idx] = StepHole(end_a, end_b, r_a, r_b,
                                              (ax, ay, az))
                    continue

                seen[key] = len(holes)
                holes.append(StepHole(end_a, end_b, r_a, r_b, (ax, ay, az)))
                _dbg(f"ACCEPTED face#{total_faces}: geomType={face.geomType()}  "
                     f"mid={tuple(np.round(mid,2))}  r=({r_a:.2f},{r_b:.2f})  "
                     f"depth={face_depth:.2f}  key={key}")

            except Exception as exc:
                rejected_other += 1
                _dbg(f"REJECTED (exception) face#{total_faces}: {exc!r}")
                continue

        _dbg(f"=== RAW FACE SCAN SUMMARY ===")
        _dbg(f"  total_faces           = {total_faces}")
        _dbg(f"  rejected_geomtype     = {rejected_geomtype}  (not CYLINDER/CONE)")
        _dbg(f"  rejected_edges        = {rejected_edges}  (<2 CIRCLE edges)")
        _dbg(f"  rejected_sweep        = {rejected_sweep}  (sweep < 180 deg)")
        _dbg(f"  rejected_dist         = {rejected_dist}  (degenerate axis)")
        _dbg(f"  rejected_depth        = {rejected_depth}  (face_depth < 0.1mm)")
        _dbg(f"  rejected_dup(collision)= {rejected_dup}  (dedup key collision)")
        _dbg(f"  rejected_other(except)= {rejected_other}")
        _dbg(f"  ACCEPTED (pre-merge)  = {len(holes)}")

        for idx, h in enumerate(holes):
            mid = (np.array(h.open_3d) + np.array(h.deep_3d)) / 2.0
            _dbg(f"  pre-merge hole[{idx}]: mid={tuple(np.round(mid,2))} "
                 f"r_open={h.radius_open:.2f} r_deep={h.radius_deep:.2f} "
                 f"depth={h.depth:.2f}")

        # ------------------------------------------------------------------
        # Post-pass 1: merge left/right half-face pairs → true circle centres.
        # Post-pass 2: merge counterbore outer+inner → single hole entry.
        # ------------------------------------------------------------------
        pre_merge_count = len(holes)
        holes = _merge_half_faces(holes)
        post_half_face_count = len(holes)
        holes = _merge_counterbores(holes)
        post_counterbore_count = len(holes)

        _dbg(f"=== PIPELINE STAGE COUNTS ===")
        _dbg(f"  pre-merge          : {pre_merge_count}")
        _dbg(f"  post half-face     : {post_half_face_count}")
        _dbg(f"  post counterbore   : {post_counterbore_count}")
        if post_half_face_count < pre_merge_count:
            _dbg(f"  -> half-face merge consumed "
                 f"{pre_merge_count - post_half_face_count} hole(s)")
        if post_counterbore_count < post_half_face_count:
            _dbg(f"  -> counterbore merge consumed "
                 f"{post_half_face_count - post_counterbore_count} hole(s)")

        for idx, h in enumerate(holes):
            mid = (np.array(h.open_3d) + np.array(h.deep_3d)) / 2.0
            _dbg(f"  FINAL hole[{idx}]: mid={tuple(np.round(mid,2))} "
                 f"r_open={h.radius_open:.2f} r_deep={h.radius_deep:.2f} "
                 f"depth={h.depth:.2f}")

        self._step_holes_cache = holes
        print(f"[geo] STEP holes extracted: {len(holes)}")
        return holes

    # ------------------------------------------------------------------
    def get_step_holes_in_view(self, projector, view_name: str,
                                screen_rot: int = 0):
        """
        Return the subset of cached STEP holes visible from *view_name*.
        """
        if not self._step_holes_cache:
            return []

        p                = projector.get_view_params(view_name, screen_rot)
        part_total_depth = p['total_depth']

        # Bug Fix C (preserved): OPEN_THRESHOLD uses 0.08 multiplier.
        OPEN_THRESHOLD = max(part_total_depth * 0.08, 2.0)
        MIN_DEPTH      = max(part_total_depth * 0.05, 0.5)

        _dbg(f"get_step_holes_in_view('{view_name}', rot={screen_rot}): "
             f"cache_size={len(self._step_holes_cache)}  "
             f"total_depth={part_total_depth:.2f}  "
             f"OPEN_THRESHOLD={OPEN_THRESHOLD:.2f}  MIN_DEPTH={MIN_DEPTH:.2f}")

        result = []
        view_rejected_open  = 0
        view_rejected_depth = 0

        for cache_idx, h in enumerate(self._step_holes_cache):
            dx_a, dy_a, d_a = projector.project_point_to_view(
                *h.open_3d, view_name, screen_rot)
            dx_b, dy_b, d_b = projector.project_point_to_view(
                *h.deep_3d, view_name, screen_rot)

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

            if open_depth > OPEN_THRESHOLD:
                _dbg(f"  VIEW-REJECTED cache[{cache_idx}] (open_depth too deep): "
                     f"display=({display_x:.2f},{display_y:.2f})  "
                     f"open_depth={open_depth:.2f} > {OPEN_THRESHOLD:.2f}")
                view_rejected_open += 1
                continue
            if actual_depth < MIN_DEPTH:
                _dbg(f"  VIEW-REJECTED cache[{cache_idx}] (actual_depth too small): "
                     f"display=({display_x:.2f},{display_y:.2f})  "
                     f"actual_depth={actual_depth:.2f} < {MIN_DEPTH:.2f}")
                view_rejected_depth += 1
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

        _dbg(f"  view_rejected_open={view_rejected_open}  "
             f"view_rejected_depth={view_rejected_depth}  "
             f"visible_result={len(result)}")
        print(f"[geo] {view_name} view (rot={screen_rot}°) — visible holes: {len(result)}")
        return result
