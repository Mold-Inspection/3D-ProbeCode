# Build/core/step_extractor10.py
# VERSION: 13
# Based on step_extractor09.py (v12). Only get_step_holes_in_view() changed
# — extract(), _merge_half_faces(), _merge_counterbores(), and
# _sample_side_hole_breach() are all untouched from v12.
#
# CHANGE LOG (v12 -> v13):
#   FEATURE (not a bug fix): get_step_holes_in_view() previously discarded
#   candidates that failed the depth/occlusion/no-breach checks via
#   `continue`, silently losing them forever. This version keeps every
#   candidate: rejected ones are now returned as a copy tagged
#   is_rejected=True with a short human-readable reject_reason, plus a
#   best-effort fallback screen position built by straight-projecting the
#   hole's 3D midpoint (NOT raycast-validated — that's exactly what
#   failed for these). If even that fallback isn't finite,
#   position_unknown=True and display_x/y stay None.
#
#   This lets the UI surface a full "Unselected Holes" list (every
#   candidate the pipeline ever considered, however marginal) instead of
#   hiding rejected geometry outright — per Chanon's request to detect
#   every possible hole and let the user inspect/override manually.
#
#   Geometry extraction, merges, and the accept-path logic for holes that
#   DO pass validation are 100% unchanged from v12.
#
# --- retained from v12 header (unchanged content below) ---
#   BUG CONFIRMED from Log_2026-07-03_09-21-35.txt: the hole reported
#   missing is cache[8] — a horizontal (Y-axis) pin bore at mesh
#   (-150, -54, -54.96), the same near-corner side-bore case documented in
#   v09. It IS extracted correctly (present in FINAL hole[8]), but is
#   dropped at the view stage:
#     - Top view:    "side-hole raycast MISSED mesh"           (correct —
#       this bore genuinely isn't visible from Top)
#     - Bottom view: "side-hole raycast hit REJECTED
#       (perp_dist=43.00 > r_ref*1.5=12.00)"                    (BUG —
#       this bore SHOULD be visible from Bottom, ~2mm from the bottom face)
#
#   Root cause: the v09/v10 side-hole fallback (_raycast_surface_depth)
#   only ever fires ONE ray, straight down the bore's exact axis-midpoint
#   column. That's correct only when the bore's true mouth happens to sit
#   on that exact column. Near a corner/boss (this part has stepped
#   geometry at many heights — see v08 changelog), the real breach point
#   can be offset from that column, so the single ray either misses the
#   mesh outright or lands on an unrelated surface far from the bore
#   (43mm away here, vs. the hole's own 8mm radius).
#
#   Fix: replaced the single-point probe with a small multi-sample search
#   (new _sample_side_hole_breach()) across the bore's actual circular
#   footprint — sampling along the ONE direction that matters
#   (perpendicular to both the bore axis and the view direction — the
#   cylinder's visible "width" in this view) combined with a few
#   positions along the bore's length. Each candidate point reuses the
#   EXISTING _raycast_surface_depth() + the EXISTING validation
#   (perp_dist <= r_ref*1.5, fb_depth > MIN_DEPTH) unchanged — this only
#   broadens where we look, not what we accept as valid. The best
#   (smallest perp_dist) valid hit across all samples is used.
#
#   get_step_holes_in_view()'s side-hole branch now calls this new method
#   instead of the single-point one; the occlusion ray-cast for
#   axis-aligned holes further down is untouched.
import numpy as np
import math
import copy
import os
import datetime
from core.models import StepHole

DEBUG = True

# ---------------------------------------------------------------------------
# file logging setup (unchanged from v06+)
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
        _LOG_FILE_HANDLE.write(f"=== step_extractor debug log started {timestamp} ===\n")
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


_MIN_SWEEP_RAD = math.pi

_AXIS_TOL       = 0.02
_EXTENT_TOL     = 0.5
_PERP_FRAC_TOL  = 0.15
_DEPTH_TOL      = 1.0      # legacy

_STRICT_GAP_TOL    = 0.05  # off-axis counterbore: must be ~touching
_MAX_RADIUS_RATIO  = 1.2   # off-axis counterbore: modest step only

# --- v10: coaxial override thresholds (unchanged) ---
_COAXIAL_PERP_TOL   = 0.3   # mm — absolute floor for "same axis line"
_COAXIAL_PERP_FRAC  = 0.15  # fraction of r_small, whichever is larger
_COAXIAL_GAP_TOL    = 5.0   # mm — relaxed gap tolerance once coaxial confirmed


def _sweep_angle(edge) -> float:
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
    """Unchanged from v05-v12."""
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
    """
    v10 logic, UNCHANGED in v11/v12/v13 — see step_extractor08.py header for
    the coaxial-override rationale. Debug logging already present here was
    kept exactly as-is.
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

            coaxial_threshold = max(_COAXIAL_PERP_TOL, r_small * _COAXIAL_PERP_FRAC)
            is_coaxial = perp_d <= coaxial_threshold

            if DEBUG:
                _dbg(f"counterbore candidate: hole[{i}] mid={tuple(np.round(mid_i,2))} "
                     f"r_open={hi.radius_open:.2f}  vs  hole[{j}] mid={tuple(np.round(mid_j,2))} "
                     f"r_open={hj.radius_open:.2f}  perp_d={perp_d:.3f}  "
                     f"coaxial_threshold={coaxial_threshold:.3f}  is_coaxial={is_coaxial}")

            if not is_coaxial:
                if perp_d + r_small >= r_large:
                    continue

            proj   = lambda pt: float(np.dot(np.array(pt), axis))
            seg_i  = sorted([proj(hi.open_3d), proj(hi.deep_3d)])
            seg_j  = sorted([proj(hj.open_3d), proj(hj.deep_3d)])
            gap    = max(seg_j[0] - seg_i[1], seg_i[0] - seg_j[1])

            gap_tol = _COAXIAL_GAP_TOL if is_coaxial else _STRICT_GAP_TOL
            _dbg(f"  axial gap={gap:.3f}  (using {'COAXIAL' if is_coaxial else 'STRICT'} "
                 f"tol=±{gap_tol})")

            if gap > gap_tol:
                _dbg(f"  REJECTED (gap {gap:.3f} > {gap_tol}) — "
                     f"treating as two separate holes")
                continue

            if not is_coaxial:
                radius_ratio = r_large / r_small if r_small > 0 else float('inf')
                if radius_ratio > _MAX_RADIUS_RATIO:
                    _dbg(f"  REJECTED (radius ratio {radius_ratio:.2f} > "
                         f"{_MAX_RADIUS_RATIO}) — too large a step")
                    continue

            candidates = [
                (hi.open_3d, proj(hi.open_3d), hi.radius_open),
                (hi.deep_3d, proj(hi.deep_3d), hi.radius_deep),
                (hj.open_3d, proj(hj.open_3d), hj.radius_open),
                (hj.deep_3d, proj(hj.deep_3d), hj.radius_deep),
            ]
            candidates.sort(key=lambda c: c[1])
            shallow_pt, _, shallow_r = candidates[0]
            deep_pt,    _, deep_r    = candidates[-1]

            new_depth = float(np.linalg.norm(np.array(deep_pt) - np.array(shallow_pt)))
            if new_depth <= 1e-6:
                _dbg(f"  SKIPPED MERGE (would collapse depth to {new_depth:.4f}) "
                     f"— keeping hole[{i}] and hole[{j}] separate")
                continue

            _dbg(f"{'COAXIAL' if is_coaxial else 'COUNTERBORE'} MERGE: "
                 f"hole[{i}] + hole[{j}]  ->  open_3d={tuple(np.round(shallow_pt,2))} "
                 f"(r={shallow_r:.2f})  deep_3d={tuple(np.round(deep_pt,2))} "
                 f"(r={deep_r:.2f})  depth={new_depth:.2f}")

            hi.open_3d     = tuple(shallow_pt)
            hi.deep_3d     = tuple(deep_pt)
            hi.radius_open = float(shallow_r)
            hi.radius_deep = float(deep_r)
            hi.radius      = float(shallow_r)
            hi.depth       = new_depth
            merged_out[j]  = True
            break

    result = [h for i, h in enumerate(holes) if not merged_out[i]]
    _dbg(f"counterbore merge: {len(holes)} -> {len(result)} holes "
         f"({sum(merged_out)} consumed)")
    return result


class StepExtractor:
    """Extract cylindrical hole geometry from STEP B-Rep data.

    v13: get_step_holes_in_view() no longer discards depth/occlusion/
    no-breach-found candidates. They are returned tagged is_rejected=True
    with a reject_reason and a best-effort (non-raycast-validated)
    fallback screen position, so the UI can surface a full "Unselected
    Holes" list. extract() and the merge stages are unchanged from v12.
    """

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
                    _dbg(f"REJECTED (fewer than 2 CIRCLE edges) face#{total_faces}: "
                         f"geomType={face.geomType()}  raw_circle_edges="
                         f"{len(raw_circle_edges)}")
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
                         f"r=({r_a:.2f},{r_b:.2f})  "
                         f"centre~{tuple(np.round((np.array(end_a)+np.array(end_b))/2,2))}")
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
        _dbg(f"  total_faces            = {total_faces}")
        _dbg(f"  rejected_geomtype      = {rejected_geomtype}  (not CYLINDER/CONE)")
        _dbg(f"  rejected_edges         = {rejected_edges}  (<2 CIRCLE edges)")
        _dbg(f"  rejected_sweep         = {rejected_sweep}  (sweep < 180 deg)")
        _dbg(f"  rejected_dist          = {rejected_dist}  (degenerate axis)")
        _dbg(f"  rejected_depth         = {rejected_depth}  (face_depth < 0.1mm)")
        _dbg(f"  rejected_dup(collision)= {rejected_dup}  (dedup key collision)")
        _dbg(f"  rejected_other(except) = {rejected_other}")
        _dbg(f"  ACCEPTED (pre-merge)   = {len(holes)}")

        for idx, h in enumerate(holes):
            mid = (np.array(h.open_3d) + np.array(h.deep_3d)) / 2.0
            _dbg(f"  pre-merge hole[{idx}]: mid={tuple(np.round(mid,2))} "
                 f"r_open={h.radius_open:.2f} r_deep={h.radius_deep:.2f} "
                 f"depth={h.depth:.2f}  "
                 f"open_3d={tuple(np.round(h.open_3d,2))} "
                 f"deep_3d={tuple(np.round(h.deep_3d,2))} "
                 f"axis={tuple(np.round(h.axis,3))}")

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
                 f"depth={h.depth:.2f}  "
                 f"open_3d={tuple(np.round(h.open_3d,2))} "
                 f"deep_3d={tuple(np.round(h.deep_3d,2))} "
                 f"axis={tuple(np.round(h.axis,3))}")

        self._step_holes_cache = holes
        print(f"[geo] STEP holes extracted: {len(holes)}")
        return holes

    def _raycast_surface_depth(self, mesh, point_3d, dir_to_viewer,
                                projector, view_name, screen_rot):
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

        dists = np.linalg.norm(locs - ray_origin, axis=1)
        hit = locs[int(np.argmin(dists))]

        dx, dy, depth = projector.project_point_to_view(*hit, view_name, screen_rot)
        return dx, dy, depth, hit

    def _sample_side_hole_breach(self, h, dir_to_viewer, mesh, projector,
                                  view_name, screen_rot):
        """
        v12: multi-sample replacement for the old single-point side-hole
        probe. Confirmed failure case: a bore whose axis is perpendicular
        to the view (e.g. axis=(0,-1,0) viewed from Top/Bottom) doesn't
        necessarily breach the surface exactly at its own axis-midpoint
        column — near a corner/boss the true mouth can be offset. A ray
        fired only at that one column can miss the mesh entirely, or
        (worse) sail through and land on an unrelated surface far from
        the bore.

        Samples several candidate points across the bore's own circular
        footprint instead of just one:
          - along the ONE direction that actually matters: perpendicular
            to both the bore axis and the view direction (the cylinder's
            visible "width" in this view) — sampled at fractions of the
            bore radius.
          - combined with a few positions along the bore's length.

        Each candidate reuses the EXISTING _raycast_surface_depth() call
        and the EXISTING validation (perp_dist <= r_ref*1.5,
        fb_depth > MIN_DEPTH) — nothing about what counts as a valid hit
        has changed, only where we look for one. Returns the best
        (smallest perp_dist) valid (fb_x, fb_y, fb_depth, fb_hit,
        perp_dist) tuple, or None if no sample validates.
        """
        MIN_DEPTH = 0.1

        axis_vec = np.array(h.axis, dtype=float)
        norm = np.linalg.norm(axis_vec)
        if norm < 1e-9:
            return None
        axis_vec = axis_vec / norm

        u = np.cross(axis_vec, dir_to_viewer)
        u_norm = np.linalg.norm(u)
        if u_norm < 1e-6:
            u = np.zeros(3)
        else:
            u = u / u_norm

        r_ref   = max(h.radius_open, h.radius_deep)
        open_pt = np.array(h.open_3d, dtype=float)
        deep_pt = np.array(h.deep_3d, dtype=float)
        mid_3d  = (open_pt + deep_pt) / 2.0

        axis_fracs = (0.5, 0.25, 0.75)
        u_fracs    = (0.0, 0.5, -0.5, 0.85, -0.85)

        best = None
        for af in axis_fracs:
            base_pt = open_pt + af * (deep_pt - open_pt)
            for uf in u_fracs:
                sample_pt = base_pt + (uf * r_ref) * u

                fb = self._raycast_surface_depth(
                    mesh, sample_pt, dir_to_viewer, projector, view_name, screen_rot)
                if fb is None:
                    continue
                fb_x, fb_y, fb_depth, fb_hit = fb

                hit_rel   = fb_hit - mid_3d
                along     = float(np.dot(hit_rel, axis_vec))
                perp_vec  = hit_rel - along * axis_vec
                perp_dist = float(np.linalg.norm(perp_vec))

                if perp_dist <= r_ref * 1.5 and fb_depth > MIN_DEPTH:
                    if best is None or perp_dist < best[4]:
                        best = (fb_x, fb_y, fb_depth, fb_hit, perp_dist)

        return best

    def get_step_holes_in_view(self, projector, view_name: str,
                                screen_rot: int = 0, mesh=None):
        """
        v13: candidates previously discarded (too-shallow / occluded /
        no-breach-found) are no longer dropped. Each is now returned as a
        copy tagged is_rejected=True with a short reject_reason and a
        best-effort fallback screen position (straight projection of the
        hole's 3D midpoint — NOT raycast-validated, since raycast is
        exactly what failed). If even that fallback projection is not
        finite, position_unknown=True and display_x/y are left as None.

        Geometry extraction, merge logic, and the accept-path for holes
        that DO pass validation are UNCHANGED from v12.
        """
        if not self._step_holes_cache:
            return []

        p      = projector.get_view_params(view_name, screen_rot)
        matrix = p['matrix']
        dir_to_viewer = matrix[:3, :3].T @ np.array([0.0, 0.0, 1.0])
        dir_to_viewer = dir_to_viewer / np.linalg.norm(dir_to_viewer)

        MIN_DEPTH = 0.1
        SIDE_HOLE_AXIS_THRESHOLD = 0.3

        _dbg(f"get_step_holes_in_view('{view_name}', rot={screen_rot}): "
             f"cache_size={len(self._step_holes_cache)}  "
             f"mesh={'yes' if mesh is not None else 'no'}")

        result = []
        view_rejected_depth    = 0
        view_rejected_occluded = 0
        side_hole_recovered    = 0

        for cache_idx, h in enumerate(self._step_holes_cache):
            dx_a, dy_a, d_a = projector.project_point_to_view(*h.open_3d, view_name, screen_rot)
            dx_b, dy_b, d_b = projector.project_point_to_view(*h.deep_3d, view_name, screen_rot)

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

            # ---- v13: shared fallback-position builder for rejected holes ----
            def _make_rejected(reason: str):
                mid_3d = (np.array(open_3d) + np.array(deep_3d)) / 2.0
                try:
                    fx, fy, fdepth = projector.project_point_to_view(
                        *mid_3d, view_name, screen_rot)
                    pos_ok = (math.isfinite(fx) and math.isfinite(fy)
                              and math.isfinite(fdepth))
                except Exception:
                    fx = fy = fdepth = None
                    pos_ok = False

                hc                   = copy.copy(h)
                hc.open_3d           = open_3d
                hc.deep_3d           = deep_3d
                hc.radius_open       = r_open
                hc.radius_deep       = r_deep
                hc.radius            = r_open
                hc.is_rejected       = True
                hc.reject_reason     = reason
                hc.position_unknown  = not pos_ok

                if pos_ok:
                    hc.display_x = fx
                    hc.display_y = fy
                    hc.depth_top = max(0.0, fdepth - r_open)
                    hc.depth_bot = fdepth
                    hc.depth     = max(0.0, hc.depth_bot - hc.depth_top)
                else:
                    hc.display_x = None
                    hc.display_y = None
                    hc.depth_top = 0.0
                    hc.depth_bot = 0.0
                    hc.depth     = 0.0
                return hc
            # --------------------------------------------------------------

            if actual_depth < MIN_DEPTH:
                axis_align = abs(float(np.dot(np.array(h.axis), dir_to_viewer)))
                if mesh is not None and axis_align < SIDE_HOLE_AXIS_THRESHOLD:
                    r_ref = max(h.radius_open, h.radius_deep)
                    best  = self._sample_side_hole_breach(
                        h, dir_to_viewer, mesh, projector, view_name, screen_rot)
                    if best is not None:
                        fb_x, fb_y, fb_depth, fb_hit, perp_dist = best
                        hc                   = copy.copy(h)
                        hc.open_3d           = open_3d
                        hc.deep_3d           = deep_3d
                        hc.radius_open       = r_open
                        hc.radius_deep       = r_deep
                        hc.radius            = r_open
                        hc.display_x         = fb_x
                        hc.display_y         = fb_y
                        hc.depth_top         = max(0.0, fb_depth - r_ref)
                        hc.depth_bot         = fb_depth
                        hc.depth             = max(MIN_DEPTH, hc.depth_bot - hc.depth_top)
                        hc.is_rejected       = False
                        hc.reject_reason     = ""
                        hc.position_unknown  = False
                        result.append(hc)
                        side_hole_recovered += 1
                        _dbg(f"  cache[{cache_idx}] SIDE-HOLE RECOVERED via multi-sample "
                             f"raycast: axis_align={axis_align:.3f}  "
                             f"perp_dist={perp_dist:.2f}  "
                             f"display=({fb_x:.2f},{fb_y:.2f})  depth={hc.depth:.2f}")
                        continue
                    else:
                        _dbg(f"  cache[{cache_idx}] side-hole multi-sample raycast found "
                             f"no valid breach point (axis_align={axis_align:.3f}, "
                             f"r_ref={r_ref:.2f})")

                _dbg(f"  cache[{cache_idx}] REJECTED->kept as unselected "
                     f"(actual_depth too small): "
                     f"actual_depth={actual_depth:.3f} < {MIN_DEPTH}  "
                     f"open_3d={tuple(np.round(h.open_3d,2))}  "
                     f"deep_3d={tuple(np.round(h.deep_3d,2))}  "
                     f"axis={tuple(np.round(h.axis,3))}")
                view_rejected_depth += 1
                result.append(_make_rejected("Too shallow / no breach found"))
                continue

            if mesh is not None:
                ray_origin = np.array(open_3d) + (dir_to_viewer * 0.1)
                hit = mesh.ray.intersects_any(
                    ray_origins=[ray_origin], ray_directions=[dir_to_viewer])
                if hit[0]:
                    _dbg(f"  cache[{cache_idx}] REJECTED->kept as unselected "
                         f"(occluded by mesh): "
                         f"display=({display_x:.2f},{display_y:.2f})  "
                         f"mouth={tuple(np.round(open_3d,2))}")
                    view_rejected_occluded += 1
                    result.append(_make_rejected("Occluded by mesh from this view"))
                    continue

            hc                   = copy.copy(h)
            hc.open_3d           = open_3d
            hc.deep_3d           = deep_3d
            hc.radius_open       = r_open
            hc.radius_deep       = r_deep
            hc.radius            = r_open
            hc.display_x         = display_x
            hc.display_y         = display_y
            hc.depth_top         = open_depth
            hc.depth_bot         = deep_depth
            hc.depth             = actual_depth
            hc.is_rejected       = False
            hc.reject_reason     = ""
            hc.position_unknown  = False
            result.append(hc)

        # v13: rejected-with-known-position sort alongside visible holes using
        # the same top-to-bottom/left-to-right key; position-unknown ones sort
        # last (they have no meaningful screen coordinate anyway).
        def _sort_key(hh):
            if hh.display_x is None or hh.display_y is None:
                return (1, 0, 0)
            return (0, -round(hh.display_y / 5.0), hh.display_x)

        result.sort(key=_sort_key)
        for i, h in enumerate(result):
            h._id = i + 1

        n_rejected = sum(1 for h in result if getattr(h, 'is_rejected', False))
        _dbg(f"  view_rejected_depth={view_rejected_depth}  "
             f"view_rejected_occluded={view_rejected_occluded}  "
             f"side_hole_recovered={side_hole_recovered}  "
             f"total_result={len(result)}  (visible={len(result)-n_rejected}, "
             f"unselected={n_rejected})")
        print(f"[geo] {view_name} view (rot={screen_rot}°) — "
              f"visible: {len(result)-n_rejected}  unselected: {n_rejected}")
        return result