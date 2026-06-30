# core/step_extractor.py
# VERSION: 09
# CHANGE LOG:
#   v01 -> v07: see step_extractor05.py history (half-face merge, counterbore
#               merge with strict gap/radius guards, debug instrumentation).
#   v07 -> v08: BUG FIX — restored real ray-cast occlusion in
#               get_step_holes_in_view(), replacing the OPEN_THRESHOLD /
#               MIN_DEPTH(part-relative) heuristic introduced during the
#               v06/v07 debug branch.
#   v08 -> v09: BUG FIX — side-bored holes (bore axis roughly perpendicular
#               to the current view's depth axis, e.g. a horizontal pin hole
#               drilled in from a side face) were silently dropped from
#               EVERY view, because the normal "open_depth/deep_depth"
#               projection method measures depth along the view axis only —
#               for a hole whose axis is perpendicular to that, both ends
#               project to ~the same depth, giving actual_depth ≈ 0.00,
#               which always fails MIN_DEPTH regardless of true visibility.
#               Confirmed case: hole open_3d=(-150,-48.91,-54.96),
#               deep_3d=(-150,-59.09,-54.96), axis=(0,-1,0) — bored along Y,
#               both ends at the same Z, but it visibly breaches the
#               top/bottom surface near the part's corner.
#
#               Fix: added a fallback path that activates ONLY when a hole
#               fails the normal depth test AND its axis is roughly
#               perpendicular to the view direction. Instead of subtracting
#               two B-Rep endpoint depths (meaningless for this axis
#               orientation), it ray-casts straight at the hole from outside
#               the part and reads the actual tessellated mesh surface depth
#               at that location — a direct "is there really a dip here"
#               check. A hit is only accepted if it lands close to the
#               hole's own axis line (within 1.5x its radius), so this can't
#               accidentally grab an unrelated surface point. This is purely
#               additive — it cannot change results for holes that already
#               pass the normal (axis-aligned) depth test.
#
#               Root cause confirmed from field log (Log_2026-06-30_11-30-25):
#               OPEN_THRESHOLD compares a hole's projected mouth-depth
#               against a single global cutoff (part_total_depth * k). That
#               assumption only holds for a flat part. This part has bosses
#               and pockets at many different heights, so legitimate holes
#               whose mouths sit on the visible face but happen to be
#               "deeper" than the part's tallest feature were being
#               rejected outright (e.g. cache[10] at (133,83) rejected with
#               open_depth=79.30 > 44.91 in the Top view, despite genuinely
#               opening on the top face). Result: Top view showed 9-ish
#               holes instead of 10, Bottom view showed 12 instead of 14.
#
#               Fix: determine the shallower end the same way as before
#               (compare d_a vs d_b — no threshold needed for that part),
#               then test TRUE visibility by ray-casting from that mouth
#               point toward the viewer and checking mesh.ray.intersects_any().
#               This is geometry-correct and threshold-free — it doesn't
#               care how tall any other feature on the part is, only
#               whether something is physically in front of this specific
#               hole's mouth from this specific viewing direction.
#
#               MIN_DEPTH is now a small FIXED value (0.1mm) used only to
#               discard truly-degenerate zero-depth projections (holes lying
#               flat in the view plane), not a part-relative cutoff.
#
# Toggle DEBUG = False to silence all logging (console AND file).
import numpy as np
import math
import copy
import os
import datetime
from core.models import StepHole

DEBUG = True

# ---------------------------------------------------------------------------
# v06 — file logging setup
# ---------------------------------------------------------------------------
_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Log")
_LOG_FILE_HANDLE = None
_LOG_FILE_PATH = None
_LOG_INIT_ATTEMPTED = False


def _init_log_file():
    global _LOG_FILE_HANDLE, _LOG_FILE_PATH, _LOG_INIT_ATTEMPTED

    if _LOG_INIT_ATTEMPTED:
        return
    _LOG_INIT_ATTEMPTED = True

    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        _LOG_FILE_PATH = os.path.join(_LOG_DIR, f"Log_{timestamp}.txt")
        _LOG_FILE_HANDLE = open(_LOG_FILE_PATH, "w", encoding="utf-8")
        _LOG_FILE_HANDLE.write(
            f"=== step_extractor debug log started {timestamp} ===\n")
        _LOG_FILE_HANDLE.flush()
        print(f"[step_extractor] Logging to file: {_LOG_FILE_PATH}")
    except Exception as exc:
        _LOG_FILE_HANDLE = None
        print(f"[step_extractor] WARNING: could not initialize log file "
              f"({exc!r}) — continuing with console logging only")


def _dbg(msg):
    if not DEBUG:
        return

    line = f"[step_extractor] {msg}"
    print(line)

    if not _LOG_INIT_ATTEMPTED:
        _init_log_file()

    if _LOG_FILE_HANDLE is not None:
        try:
            _LOG_FILE_HANDLE.write(line + "\n")
            _LOG_FILE_HANDLE.flush()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Problem 1 fix — sweep-angle threshold.
# ---------------------------------------------------------------------------
_MIN_SWEEP_RAD = math.pi          # 180° — minimum arc sweep to be a hole boundary

# ---------------------------------------------------------------------------
# Merge tolerances (unchanged from v05 — these are correct, keep as-is).
# ---------------------------------------------------------------------------
_AXIS_TOL       = 0.02    # cos-angle tolerance for parallel axes
_EXTENT_TOL     = 0.5     # mm — axial extent match tolerance for half-face merge
_PERP_FRAC_TOL  = 0.15    # fractional tolerance on 4r/π separation
_DEPTH_TOL      = 1.0     # mm — legacy, superseded by _STRICT_GAP_TOL below

_STRICT_GAP_TOL    = 0.05   # mm — counterbore segments must be ~touching
_MAX_RADIUS_RATIO  = 1.2    # outer radius must be <= this multiple of inner


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
    """Return the TRUE geometric radius of a CIRCLE-type edge (mm)."""
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
    """Merge left/right half-face pairs into single holes with correct centres."""
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

            if abs(float(np.dot(hi.axis, hj.axis))) < 1 - _AXIS_TOL:
                continue
            if abs(hi.radius - hj.radius) > 0.1:
                continue

            ai0, ai1 = sorted([proj(hi.open_3d), proj(hi.deep_3d)])
            aj0, aj1 = sorted([proj(hj.open_3d), proj(hj.deep_3d)])
            if abs(ai0 - aj0) > _EXTENT_TOL or abs(ai1 - aj1) > _EXTENT_TOL:
                continue

            mid_i  = (np.array(hi.open_3d) + np.array(hi.deep_3d)) / 2.0
            mid_j  = (np.array(hj.open_3d) + np.array(hj.deep_3d)) / 2.0
            delta  = mid_j - mid_i
            perp   = delta - float(np.dot(delta, axis)) * axis
            perp_d = float(np.linalg.norm(perp))

            expected = 4.0 * hi.radius / math.pi
            if abs(perp_d - expected) > expected * _PERP_FRAC_TOL:
                continue

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
    """Collapse counterbore pairs (outer wide bore + inner narrow bore) into one."""
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

            dot = abs(float(np.dot(hi.axis, hj.axis)))
            if dot < 1.0 - _AXIS_TOL:
                continue

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

            proj   = lambda pt: float(np.dot(np.array(pt), axis))
            seg_i  = sorted([proj(hi.open_3d), proj(hi.deep_3d)])
            seg_j  = sorted([proj(hj.open_3d), proj(hj.deep_3d)])
            gap    = max(seg_j[0] - seg_i[1], seg_i[0] - seg_j[1])

            _dbg(f"  axial gap={gap:.3f}  (strict_tol=±{_STRICT_GAP_TOL}, "
                 f"legacy_tol={_DEPTH_TOL})")

            if gap > _STRICT_GAP_TOL:
                _dbg(f"  REJECTED (gap {gap:.3f} > strict tol "
                     f"{_STRICT_GAP_TOL}) — treating as two separate "
                     f"stacked holes, not a counterbore")
                continue

            radius_ratio = r_large / r_small if r_small > 0 else float('inf')
            if radius_ratio > _MAX_RADIUS_RATIO:
                _dbg(f"  REJECTED (radius ratio {radius_ratio:.2f} > "
                     f"{_MAX_RADIUS_RATIO}) — too large a step to be a "
                     f"plausible counterbore")
                continue

            if hi.radius_open <= hj.radius_open:
                inner, outer, outer_idx = hi, hj, j
            else:
                inner, outer, outer_idx = hj, hi, i
                merged_out[i] = True

            _dbg(f"COUNTERBORE MERGE: keeping hole[{i if inner is hi else j}] "
                 f"(inner, r={inner.radius_open:.2f}) , dropping hole[{outer_idx}] "
                 f"(outer, r={outer.radius_open:.2f}) at mid="
                 f"{tuple(np.round((mid_i if outer is hi else mid_j),2))}")

            inner_deep_proj  = float(np.dot(np.array(inner.deep_3d), axis))
            outer_open_proj  = float(np.dot(np.array(outer.open_3d), axis))
            outer_deep_proj  = float(np.dot(np.array(outer.deep_3d), axis))

            if abs(outer_open_proj - inner_deep_proj) >= abs(outer_deep_proj - inner_deep_proj):
                new_open_3d = outer.open_3d
            else:
                new_open_3d = outer.deep_3d

            new_depth = float(np.linalg.norm(
                np.array(inner.deep_3d) - np.array(new_open_3d)))

            if new_depth <= 1e-6:
                _dbg(f"  SKIPPED MERGE (would collapse depth to {new_depth:.4f}) "
                     f"— keeping hole[{i}] and hole[{j}] separate")
                continue

            inner.open_3d = tuple(np.array(new_open_3d))
            inner.depth   = new_depth
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

        pre_merge_count = len(holes)
        holes = _merge_half_faces(holes)
        post_half_face_count = len(holes)
        holes = _merge_counterbores(holes)
        post_counterbore_count = len(holes)

        _dbg(f"=== PIPELINE STAGE COUNTS ===")
        _dbg(f"  pre-merge          : {pre_merge_count}")
        _dbg(f"  post half-face     : {post_half_face_count}")
        _dbg(f"  post counterbore   : {post_counterbore_count}")

        self._step_holes_cache = holes
        print(f"[geo] STEP holes extracted: {len(holes)}")
        return holes

    # ------------------------------------------------------------------
    def _raycast_surface_depth(self, mesh, point_3d, dir_to_viewer,
                                projector, view_name, screen_rot):
        """
        Cast a ray from outside the part, straight at `point_3d`, along
        `dir_to_viewer` (i.e. coming from the viewer's side), and return
        (display_x, display_y, depth, hit_point_3d) for the first real
        mesh surface it strikes. Returns None if the ray misses the mesh
        entirely (e.g. point_3d is outside the part's silhouette here).

        Used as a fallback for holes whose bore axis is roughly
        perpendicular to the view — their B-Rep open/deep endpoints don't
        carry meaningful "depth in this view" information, so this checks
        the actual tessellated surface instead.
        """
        try:
            bbox_diag = float(np.linalg.norm(mesh.bounds[1] - mesh.bounds[0]))
        except Exception:
            return None

        ray_origin = np.array(point_3d) + dir_to_viewer * (bbox_diag + 5.0)
        try:
            locs, _, _ = mesh.ray.intersects_location(
                ray_origins=[ray_origin], ray_directions=[-dir_to_viewer])
        except Exception:
            return None

        if len(locs) == 0:
            return None

        # First surface struck by a ray coming from the viewer = the one
        # closest to ray_origin.
        dists = np.linalg.norm(locs - ray_origin, axis=1)
        hit = locs[int(np.argmin(dists))]

        dx, dy, depth = projector.project_point_to_view(
            *hit, view_name, screen_rot)
        return dx, dy, depth, hit

    # ------------------------------------------------------------------
    def get_step_holes_in_view(self, projector, view_name: str,
                                screen_rot: int = 0, mesh=None):
        """
        Return the subset of cached STEP holes visible from *view_name*.

        v08: uses TRUE geometric occlusion via ray-casting against the
        tessellated mesh — NOT a depth-threshold heuristic. For each hole,
        the shallower of its two ends (by projected depth in this view) is
        treated as the candidate "mouth". A ray is cast from just outside
        that mouth toward the viewer; if it hits the mesh before leaving
        the part, the hole's mouth is physically blocked by other geometry
        and is excluded. If `mesh` is not provided, occlusion testing is
        skipped (all holes with nonzero projected depth are kept) — this
        keeps the method usable even if a caller doesn't have a mesh handy.
        """
        if not self._step_holes_cache:
            return []

        p      = projector.get_view_params(view_name, screen_rot)
        matrix = p['matrix']

        # Direction from a surface point toward the viewer, in original
        # (untransformed) part coordinates. The viewer is fixed looking
        # down -Z in the rotated/view frame, so +Z in that frame maps back
        # via the transpose of the rotation submatrix.
        dir_to_viewer = matrix[:3, :3].T @ np.array([0.0, 0.0, 1.0])
        dir_to_viewer = dir_to_viewer / np.linalg.norm(dir_to_viewer)

        MIN_DEPTH = 0.1  # mm — only discards genuinely-degenerate (zero) depth
        SIDE_HOLE_AXIS_THRESHOLD = 0.3  # |dot(axis, view_dir)| below this = side-bored

        _dbg(f"get_step_holes_in_view('{view_name}', rot={screen_rot}): "
             f"cache_size={len(self._step_holes_cache)}  mesh={'yes' if mesh is not None else 'no'}")

        result = []
        view_rejected_depth     = 0
        view_rejected_occluded  = 0
        side_hole_recovered     = 0

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

            if actual_depth < MIN_DEPTH:
                # ------------------------------------------------------
                # v09 fallback: this hole may simply be bored perpendicular
                # to the current view (its endpoints carry no meaningful
                # "depth in this view"). If so, check the real tessellated
                # surface directly instead of giving up.
                # ------------------------------------------------------
                axis_align = abs(float(np.dot(np.array(h.axis), dir_to_viewer)))
                if mesh is not None and axis_align < SIDE_HOLE_AXIS_THRESHOLD:
                    mid_3d = (np.array(h.open_3d) + np.array(h.deep_3d)) / 2.0
                    fb = self._raycast_surface_depth(
                        mesh, mid_3d, dir_to_viewer, projector, view_name, screen_rot)

                    if fb is not None:
                        fb_x, fb_y, fb_depth, fb_hit = fb

                        # Sanity check: the surface hit must actually belong
                        # to THIS hole's own bore, not some unrelated patch
                        # of the part. Measure perpendicular distance from
                        # the hit point to the hole's own axis line.
                        axis_vec  = np.array(h.axis)
                        hit_rel   = fb_hit - mid_3d
                        along     = float(np.dot(hit_rel, axis_vec))
                        perp_vec  = hit_rel - along * axis_vec
                        perp_dist = float(np.linalg.norm(perp_vec))

                        r_ref = max(h.radius_open, h.radius_deep)
                        if perp_dist <= r_ref * 1.5 and fb_depth > MIN_DEPTH:
                            hc             = copy.copy(h)
                            hc.open_3d     = open_3d
                            hc.deep_3d     = deep_3d
                            hc.radius_open = r_open
                            hc.radius_deep = r_deep
                            hc.radius      = r_open
                            hc.display_x   = fb_x
                            hc.display_y   = fb_y
                            hc.depth_top   = max(0.0, fb_depth - r_ref)
                            hc.depth_bot   = fb_depth
                            hc.depth       = max(MIN_DEPTH, hc.depth_bot - hc.depth_top)
                            result.append(hc)
                            side_hole_recovered += 1
                            _dbg(f"  cache[{cache_idx}] SIDE-HOLE RECOVERED via surface "
                                 f"raycast: axis_align={axis_align:.3f}  "
                                 f"perp_dist={perp_dist:.2f}  display=({fb_x:.2f},{fb_y:.2f})  "
                                 f"depth={hc.depth:.2f}")
                            continue

                _dbg(f"  cache[{cache_idx}] REJECTED (actual_depth too small): "
                     f"actual_depth={actual_depth:.3f} < {MIN_DEPTH}")
                view_rejected_depth += 1
                continue

            if mesh is not None:
                # Lift the ray origin a hair off the mouth so it doesn't
                # immediately self-intersect the hole's own wall.
                ray_origin = np.array(open_3d) + (dir_to_viewer * 0.1)
                hit = mesh.ray.intersects_any(
                    ray_origins=[ray_origin],
                    ray_directions=[dir_to_viewer]
                )
                if hit[0]:
                    _dbg(f"  cache[{cache_idx}] REJECTED (occluded by mesh): "
                         f"display=({display_x:.2f},{display_y:.2f})")
                    view_rejected_occluded += 1
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

        _dbg(f"  view_rejected_depth={view_rejected_depth}  "
             f"view_rejected_occluded={view_rejected_occluded}  "
             f"side_hole_recovered={side_hole_recovered}  "
             f"visible_result={len(result)}")
        print(f"[geo] {view_name} view (rot={screen_rot}°) — visible holes: {len(result)}")
        return result
