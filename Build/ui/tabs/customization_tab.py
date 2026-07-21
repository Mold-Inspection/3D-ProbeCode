# ui/tabs/customization_tab.py
# VERSION: 11
# CHANGELOG:
#   - V11 FIX: "deepest segment" (the one allowed to show the bottom-depth
#     star) is now decided by comparing each segment's own PROJECTED
#     depth through the CURRENT VIEW, not by trusting hole.segments' list
#     order (segments[-1]). List order comes from B-Rep/mesh axis
#     direction conventions (step_extractor.py) which can still end up
#     ambiguous for some geometry even after the v25 mesh-orientation
#     check; "bottom of the workpiece" is unambiguous once you look at
#     actual projected depth (surface_z minus the projected point — the
#     same convention driving every other depth value in this app) —
#     whichever segment reaches the largest depth value IS the one
#     closest to the real workpiece bottom, independent of list order.
#     deepest_seg_idx is now computed once (alongside isolate_raw_seg,
#     near the top of draw_cross_section) by projecting every raw
#     segment's open_3d/deep_3d through projector.project_point_to_view()
#     and taking whichever segment's deepest point is largest. Isolating
#     any OTHER segment withholds the star, same as before — only the
#     comparison basis changed.
#   - V10 FIX (2 items):
#     1. Isolate-mode bottom depth star suppressed for non-deepest
#        segments. hole.segments is always sorted shallow->deep by
#        step_extractor.py's _merge_counterbores() (open end at index 0,
#        true hole bottom at index len-1 — see that file's v24 changelog),
#        so segments[-1] is always the one that actually reaches the real
#        hole bottom. Isolating any OTHER (shallower) segment no longer
#        draws the yellow star / "Bottom Depth Point" marker or its
#        "Depth=... mm" text, since that segment's own end is really just
#        the boundary into the next segment, not the hole's true bottom —
#        showing a star there was misleading. The wall/toolpath for that
#        segment still draws normally; only the star+text is withheld.
#     2. Whole-hole (non-isolated) wall-highlight mask no longer uses a
#        single h.radius (the OPEN end's radius only) as its search
#        radius across the ENTIRE depth. For any hole that's wider at a
#        deeper point than at its mouth (counterbore, ball-nose bottom,
#        reverse taper, etc.) that single narrow radius silently excluded
#        the wider triangles further down, making the highlighted mesh
#        look cut off partway through. Now uses the MAX radius found
#        across the hole's full geometry (StepHole.radius_open/
#        radius_deep, plus every raw segment's own radius_open/
#        radius_deep when present) so nothing at any depth is excluded.
#        Isolate mode is unaffected — it already used that segment's own
#        max(radius_open, radius_deep).
#   - V09 FEATURE: segment isolate. When the user expands one segment's
#     folder row in the sidebar (main_window.py v11 sets
#     app.selected_segment_idx), draw_cross_section() now shows ONLY that
#     segment — its own wall-highlight mesh slice and its own toolpath —
#     instead of the combined all-segments view. Other segments of the
#     same hole are hidden entirely (not just dimmed), same as how an
#     unselected hole is skipped today.
#       - Isolate's path is built by calling the plain single-segment
#         app.geo.get_probe_path_layers() directly on the raw HoleSegment
#         (StepHole.segments[i] — it already exposes open_3d/deep_3d/
#         radius_at, the exact interface get_probe_path_layers expects),
#         using that segment's OWN HoleSegmentSetting
#         (layers/points/zigzag/degree). No new geometry/path code was
#         needed — this reuses the existing single-segment function with
#         segment-scoped inputs instead of whole-hole inputs.
#       - The wall-highlight mesh mask (white "Selected Hole Mesh" outline
#         drawn from the loop above) is scoped to that segment's own
#         projected z-range/radius instead of the whole hole's, so the
#         highlighted mesh band matches what's being probed.
#       - 3D camera zoom (xlim/ylim/zlim) now frames just the isolated
#         segment's z-span instead of the whole hole's, so isolating a
#         short segment usefully zooms in on it.
#       - Collapsing the segment (selected_segment_idx back to None) or
#         switching holes reverts to the original v08 "whole hole, all
#         segments" rendering — zero behavior change for ordinary
#         single-segment holes or multi-segment holes with nothing
#         expanded.
#   - V08 FEATURE: multi-diameter ("counterbore-style") hole support.
#     Problem: draw_cross_section() always called the single-segment
#     app.geo.get_probe_path_layers(sh, hole.layers, ...), which
#     interpolates radius linearly across the WHOLE hole (open_3d to
#     deep_3d). For a hole with a true step in diameter, this produced a
#     toolpath that ramped smoothly through what should be a sudden
#     jump, missing the wall right around the step.
#     Fix: when `hole.segments` is non-empty (see main_window.py v10 /
#     path_planner.py v02 / models.py v02), this now calls
#     app.geo.get_probe_path_layers_multi(sh, hole.segments, ...)
#     instead — each segment's own layers/points_per_layer/
#     zigzag_inspection/zigzag_degree (set per-segment in the sidebar
#     "folder" UI) drives its own slice of the path, and radius is only
#     ever interpolated within that segment. The wall-point loop now
#     reads 'points_per_layer' off each layer dict (present only for the
#     multi-segment path) instead of a single shared `points` value.
#     Zigzag layer coloring/spoke-line rendering now iterates the actual
#     layer indices present (sorted(layer_centers.keys())) instead of
#     range(hole.layers), so it works whether those layers came from one
#     segment or several. Title bar / legend text summarizes per-segment
#     config for multi-diameter holes instead of a single "NL × NP".
#     Ordinary single-segment holes (hole.segments empty — the
#     overwhelming majority) take the exact same code path as before,
#     byte-for-byte unchanged behavior.
#   - V07 BUG FIX: Restored the missing `px_list.append(star_z)` lines that were 
#     accidentally removed during the V06 merge. The yellow dashed toolpath will 
#     now correctly reach the bottom depth star again.
#   - V06 UX: Unselected holes have 10% opacity in 3D to reduce visual clutter.
#   - V06 UX: Hovering over items in the right sidebar highlights the hole in 3D.

import numpy as np
import trimesh
from trimesh.transformations import euler_matrix
from mpl_toolkits.mplot3d import proj3d

# Layer colours for Zigzag mode — 24 colours, cycling if more layers
# Avoids yellow/gold shades to stay clear of the Tool Path / star marker
ZIGZAG_LAYER_COLORS = [
    '#00bcd4', '#ff4d6d', '#7c4dff', '#69f0ae', '#ff9100', '#40c4ff',
    '#f06292', '#aeea00', '#ea80fc', '#ff6e40', '#18ffff', '#b9f6ca',
    '#ff4081', '#b388ff', '#00e676', '#ff6d00', '#82b1ff', '#f48fb1',
    '#1de9b6', '#ff8a65', '#ce93d8', '#80d8ff', '#a5d6a7', '#ef9a9a',
]

def _layer_color(lidx: int) -> str:
    return ZIGZAG_LAYER_COLORS[lidx % len(ZIGZAG_LAYER_COLORS)]

_VIEW_ROTATIONS = {
    'Top':    (  0,  0,   0),
    'Bottom': (180,  0,   0),
    'Front':  (-90,  0,   0),
    'Back':   (-90,  180, 0),
    'Left':   (-90,  -90, 0),
    'Right':  (-90,  90,  0),
}

def _build_combined_matrix(view_name: str, screen_rot: int):
    """
    Return the combined 4×4 transform that matches what the Projector applies:
      1. Apply the view rotation (object rotated so the named face points up).
      2. Apply an additional Z-axis spin of `screen_rot` degrees (on-screen rotation).
    """
    rx, ry, rz = _VIEW_ROTATIONS.get(view_name, (0, 0, 0))
    m_view = euler_matrix(*np.radians([rx, ry, rz]))
    if screen_rot != 0:
        m_scrn = euler_matrix(0, 0, np.radians(screen_rot))
        return m_scrn @ m_view
    return m_view

def _hole_display_label(h) -> str:
    did = getattr(h, 'display_id', getattr(h, 'id', '?'))
    if getattr(h, 'selected_for_inspection', False):
        return str(did)
    return f"U{did}"


def _hole_max_radius(h) -> float:
    """
    v10: best-effort MAXIMUM radius across a hole's full depth, used for
    the whole-hole wall-highlight mask so it never excludes real wall
    triangles at a wider point (counterbore mouth, ball-nose bottom,
    reverse taper, etc.) — a single open-end radius alone isn't enough.
    Falls back to h.radius for mesh-only holes (no _step_hole).
    """
    sh = getattr(h, '_step_hole', None)
    if sh is None:
        return h.radius
    candidates = [sh.radius_open, sh.radius_deep]
    for seg in (getattr(sh, 'segments', None) or []):
        candidates.append(seg.radius_open)
        candidates.append(seg.radius_deep)
    return max(candidates) if candidates else h.radius


class CustomizationTab:
    def __init__(self, app):
        self.app = app
        self._text_objects = {}

    def draw_cross_section(self):
        app = self.app
        app.fig.clf()
        app.cax = None

        has_mesh = app.geo.mesh is not None
        has_hole = (app.selected_hole_idx is not None and len(app.current_holes) > 0)

        if not has_mesh:
            app.ax = app.fig.add_subplot(111, facecolor='#1e1e1e')
            app.ax.set_title("Please upload a model and generate holes first.", color="white", fontsize=15)
            app.ax.set_axis_off()
            app.canvas.draw()
            return

        app.fig.subplots_adjust(left=0.0, right=1.0, top=1.0, bottom=0.0)
        ax3d = app.fig.add_subplot(111, projection='3d', facecolor='#1e1e1e')
        app.ax = ax3d
        self._text_objects = {}

        screen_rot = app.screen_rotation
        _matrix    = _build_combined_matrix(app.current_view, screen_rot)
        _rotated = trimesh.transformations.transform_points(app.geo.mesh.vertices, _matrix)

        faces = app.geo.mesh.faces
        x3    = _rotated[:, 0]
        y3    = _rotated[:, 1]
        z3    = -_rotated[:, 2]
        tris  = faces

        x3 = x3 - (float(np.min(x3)) + float(np.max(x3))) / 2.0
        y3 = y3 - (float(np.min(y3)) + float(np.max(y3))) / 2.0

        n_tri    = len(tris)
        MAX_TRIS = 16000
        step     = max(1, n_tri // MAX_TRIS)
        sampled  = tris[::step]

        SURF_Z_GLOBAL = float(np.min(z3))

        tx_m    = x3[sampled]
        ty_m    = y3[sampled]
        tz_m    = z3[sampled] - SURF_Z_GLOBAL
        nan_col = np.full((len(sampled), 1), np.nan)
        seg_x   = np.hstack([tx_m[:, [0, 1, 2, 0]], nan_col]).ravel()
        seg_y   = np.hstack([ty_m[:, [0, 1, 2, 0]], nan_col]).ravel()
        seg_z   = np.hstack([tz_m[:, [0, 1, 2, 0]], nan_col]).ravel()

        if not has_hole:
            ax3d.plot(seg_x, seg_y, seg_z, color="#1f538d", linewidth=0.8, alpha=0.6)

        tri_cx = x3[tris].mean(axis=1)
        tri_cy = y3[tris].mean(axis=1)
        tri_cz = z3[tris].mean(axis=1) - SURF_Z_GLOBAL

        xmin, xmax = float(np.min(x3)), float(np.max(x3))
        ymin, ymax = float(np.min(y3)), float(np.max(y3))
        zmin_d     = 0.0
        zmax_d     = float(np.max(z3)) - SURF_Z_GLOBAL
        cx         = (xmin + xmax) / 2.0
        cy         = (ymin + ymax) / 2.0
        cz         = (zmin_d + zmax_d) / 2.0
        half       = max(xmax - xmin, ymax - ymin, zmax_d - zmin_d) / 2.0 * 1.1

        # v09: determine whether a specific segment is "isolated" (set by
        # main_window.py's _toggle_segment_expand -> selected_segment_idx).
        # Used both by the wall-highlight loop right below and by the
        # toolpath-building block further down. None = show the whole
        # hole (original v08 behavior, zero change).
        #
        # v11: also determine which segment is the TRUE bottom of the
        # workpiece, for the "only the deepest segment shows the star"
        # rule. This is now decided by comparing each segment's own
        # PROJECTED depth through the current view (the same depth
        # convention already used everywhere else — surface_z minus the
        # projected point, via projector.project_point_to_view), NOT by
        # trusting hole.segments' list order. List order comes from
        # B-Rep/mesh axis conventions that can still be ambiguous;
        # projected depth is unambiguous — whichever segment actually
        # reaches the largest depth value IS the one closest to the
        # workpiece's true bottom, full stop.
        isolate_raw_seg  = None
        deepest_seg_idx  = None
        if has_hole:
            sel_hole      = app.current_holes[app.selected_hole_idx]
            sel_segments  = getattr(sel_hole, 'segments', None)
            isolate_idx   = getattr(app, 'selected_segment_idx', None)
            sel_step_hole = getattr(sel_hole, '_step_hole', None)
            raw_segments  = getattr(sel_step_hole, 'segments', None) if sel_step_hole else None

            if sel_segments and isolate_idx is not None and 0 <= isolate_idx < len(sel_segments):
                if raw_segments and isolate_idx < len(raw_segments):
                    isolate_raw_seg = raw_segments[isolate_idx]

            if raw_segments and len(raw_segments) > 1:
                deepest_depth = None
                for si, seg in enumerate(raw_segments):
                    d_open = app.geo.projector.project_point_to_view(*seg.open_3d, app.current_view, screen_rot)[2]
                    d_deep = app.geo.projector.project_point_to_view(*seg.deep_3d, app.current_view, screen_rot)[2]
                    seg_deepest = max(d_open, d_deep)
                    if deepest_depth is None or seg_deepest > deepest_depth:
                        deepest_depth  = seg_deepest
                        deepest_seg_idx = si

        for i, h in enumerate(app.current_holes):
            r_z    = getattr(h, 'hole_top_z', h.surface_z)
            is_sel = (i == app.selected_hole_idx)

            is_selected_cat = getattr(h, 'selected_for_inspection', False)
            base_alpha = 1.0 if is_selected_cat else 0.1
            
            txt = ax3d.text(h.x, h.y, r_z + half * 0.02,
                            _hole_display_label(h), color='white', fontsize=7,
                            ha='center', va='bottom', alpha=base_alpha)
            
            self._text_objects[i] = {
                'text': txt,
                'base_alpha': base_alpha,
                'base_color': 'white',
                'base_zorder': txt.get_zorder()
            }

            if has_hole and not is_sel:
                continue

            dist_h = np.hypot(tri_cx - h.x, tri_cy - h.y)

            if is_sel and isolate_raw_seg is not None:
                # v09: isolating one segment — scope the highlight band to
                # THAT segment's own projected z-range/radius instead of
                # the whole hole's, so the white mesh outline matches what
                # is actually being probed.
                d_open   = app.geo.projector.project_point_to_view(*isolate_raw_seg.open_3d, app.current_view, screen_rot)
                d_deep   = app.geo.projector.project_point_to_view(*isolate_raw_seg.deep_3d, app.current_view, screen_rot)
                z_lo_h   = min(d_open[2], d_deep[2])
                z_hi_h   = max(d_open[2], d_deep[2]) + 0.5
                radius_h = max(isolate_raw_seg.radius_open, isolate_raw_seg.radius_deep)
            else:
                z_lo_h   = min(h.bottom_z, r_z)
                z_hi_h   = max(h.bottom_z, r_z) + 0.5
                radius_h = _hole_max_radius(h)

            mask_wall = ((dist_h <= radius_h * 1.2) & (tri_cz >= z_lo_h - 0.3) & (tri_cz <= z_hi_h))
            mask_rim  = ((dist_h <= radius_h * 1.3) & (tri_cz >= -0.5) & (tri_cz < z_lo_h + 0.3))
            htris = tris[mask_wall | mask_rim]

            if len(htris) > 0 and is_sel:
                htx = x3[htris]; hty = y3[htris]
                htz = z3[htris] - SURF_Z_GLOBAL
                nan_h = np.full((len(htris), 1), np.nan)
                hxs   = np.hstack([htx[:, [0, 1, 2, 0]], nan_h]).ravel()
                hys   = np.hstack([hty[:, [0, 1, 2, 0]], nan_h]).ravel()
                hzs   = np.hstack([htz[:, [0, 1, 2, 0]], nan_h]).ravel()
                ax3d.plot(hxs, hys, hzs, color="white", linewidth=1.6, alpha=0.76, label='Selected Hole Mesh')

        probe_warn_lines = []
        probe_ok         = True

        if has_hole:
            hole_for_check = app.current_holes[app.selected_hole_idx]
            if hasattr(app, 'probe_profile') and app.probe_profile is not None:
                chk = app.probe_profile.check_hole(hole_for_check.depth, hole_for_check.radius)
                probe_ok = chk['ok']
                if chk['depth_warning']: probe_warn_lines.append(chk['depth_warning'])
                if chk['fit_warning']:   probe_warn_lines.append(chk['fit_warning'])

        if has_hole:
            hole       = app.current_holes[app.selected_hole_idx]
            layers     = hole.layers
            points     = hole.points_per_layer
            use_zigzag = getattr(hole, 'zigzag_inspection', False)
            step_deg   = getattr(hole, 'zigzag_degree', 45.0)

            # v08: multi-diameter ("counterbore-style") hole — hole.segments
            # is a list of HoleSegmentSetting (models.py v02), non-empty only
            # for holes step_extractor.py v24 merged from 2+ real-diameter
            # segments. Empty (ordinary hole) => every branch below behaves
            # exactly as before.
            is_multi_seg = bool(getattr(hole, 'segments', None))

            # v09: isolate_raw_seg was resolved earlier (before the
            # wall-highlight loop) from app.selected_segment_idx. When set,
            # treat this hole exactly like an ordinary single-segment hole
            # for path/label purposes, but scoped to THIS segment's own
            # raw geometry + own HoleSegmentSetting — never the whole hole.
            isolate_active = (is_multi_seg and isolate_raw_seg is not None)
            isolate_cfg    = hole.segments[app.selected_segment_idx] if isolate_active else None
            # multi_seg_display: True only when the ALL-segments combined
            # view is actually being drawn (multi-segment hole, nothing
            # isolated). Drives the "N segments" vs "NL x NP" labeling
            # further down.
            multi_seg_display = is_multi_seg and not isolate_active

            # v11: the deepest segment is decided by comparing PROJECTED
            # depth through the current view (deepest_seg_idx, computed
            # above from the real workpiece surface via the projector) —
            # not by trusting hole.segments' list order, which can still
            # be ambiguous coming from B-Rep/mesh axis conventions.
            # Isolating any segment that ISN'T that true-deepest one must
            # not show the bottom-depth star — its own "end" is really
            # just the boundary into the next segment, not the workpiece's
            # actual bottom.
            show_bottom_star = True
            if isolate_active:
                show_bottom_star = (app.selected_segment_idx == deepest_seg_idx)

            if isolate_active:
                layers     = isolate_cfg.layers
                points     = isolate_cfg.points_per_layer
                use_zigzag = isolate_cfg.zigzag_inspection
                step_deg   = isolate_cfg.zigzag_degree

            zigzag_any = (any(cfg.zigzag_inspection for cfg in hole.segments)
                          if multi_seg_display else use_zigzag)

            rim_z = getattr(hole, 'hole_top_z', hole.surface_z)
            bot_z = hole.bottom_z

            raw_rim_z = rim_z + SURF_Z_GLOBAL
            raw_bot_z = bot_z + SURF_Z_GLOBAL

            dist_v = np.hypot(x3 - hole.x, y3 - hole.y)
            z_lo_v = min(raw_rim_z, raw_bot_z) - 2.0
            z_hi_v = max(raw_rim_z, raw_bot_z) + 2.0
            vmask  = ((dist_v <= hole.radius * 1.6) & (z3 >= z_lo_v) & (z3 <= z_hi_v))
            vx = x3[vmask]; vy = y3[vmask]; vz = z3[vmask]

            has_step_hole = (hasattr(hole, '_step_hole') and hole._step_hole is not None and
                             hasattr(app.geo, 'step_data') and app.geo.step_data is not None)

            def dz(z_raw): return z_raw - SURF_Z_GLOBAL

            if has_step_hole:
                sh     = hole._step_hole

                if isolate_active:
                    # v09: scope z_start/star_z to THIS segment's own
                    # projected depth range, not the whole hole's — so the
                    # camera zoom (further below) frames just the isolated
                    # segment instead of the whole hole.
                    d_open  = app.geo.projector.project_point_to_view(
                        *isolate_raw_seg.open_3d, app.current_view, screen_rot)
                    d_deep  = app.geo.projector.project_point_to_view(
                        *isolate_raw_seg.deep_3d, app.current_view, screen_rot)
                    z_start = min(d_open[2], d_deep[2])
                    star_z  = max(d_open[2], d_deep[2])
                else:
                    z_start = sh.depth_top
                    star_z  = sh.depth_bot
                star_x  = hole.x
                star_y  = hole.y

                # v08/v09: segment-aware path for multi-diameter holes —
                # radius is only ever interpolated WITHIN one segment,
                # never across a real step boundary.
                #   isolate_active -> ONE segment only, via the plain
                #     single-segment get_probe_path_layers() called
                #     directly on the raw HoleSegment (it already exposes
                #     open_3d/deep_3d/radius_at) with that segment's own
                #     HoleSegmentSetting.
                #   multi_seg_display -> ALL segments combined (v08,
                #     unchanged).
                #   else -> ordinary single-segment hole (unchanged).
                if isolate_active:
                    step_layers = app.geo.get_probe_path_layers(
                        isolate_raw_seg, layers, app.current_view,
                        screen_rot=screen_rot,
                        zigzag_inspection=use_zigzag,
                        zigzag_degree=step_deg)
                elif multi_seg_display:
                    step_layers = app.geo.get_probe_path_layers_multi(
                        sh, hole.segments, app.current_view,
                        screen_rot=screen_rot)
                else:
                    step_layers = app.geo.get_probe_path_layers(
                        sh, layers, app.current_view,
                        screen_rot=screen_rot,
                        zigzag_inspection=use_zigzag,
                        zigzag_degree=step_deg)

                px_list, py_list, pz_list = [hole.x], [hole.y], [z_start]
                wall_pts     = []
                layer_centers = {}

                for lyr in step_layers:
                    z_disp     = lyr['z_display']
                    r_at_z     = lyr['radius'] * 0.92
                    cx_lyr     = lyr['x_display']
                    cy_lyr     = lyr['y_display']
                    ang_offset = lyr.get('angle_offset', 0.0)
                    lidx       = lyr.get('layer_idx', 0)
                    # v08: multi-segment layers carry their OWN
                    # points_per_layer (that segment's setting); ordinary
                    # holes fall back to the single shared `points` value.
                    pts_this_layer = lyr.get('points_per_layer', points)

                    layer_centers[lidx] = (cx_lyr, cy_lyr, z_disp, ang_offset, r_at_z)
                    px_list.append(cx_lyr); py_list.append(cy_lyr); pz_list.append(z_disp)

                    for ang in np.linspace(0, 2 * np.pi, pts_this_layer, endpoint=False):
                        a   = ang + ang_offset
                        ppx = cx_lyr + r_at_z * np.cos(a)
                        ppy = cy_lyr + r_at_z * np.sin(a)
                        wall_pts.append((ppx, ppy, z_disp, lidx))
                        px_list += [ppx, cx_lyr]; py_list += [ppy, cy_lyr]; pz_list += [z_disp, z_disp]

            else:
                vz_disp = vz - SURF_Z_GLOBAL

                if len(vz_disp) >= 6:
                    n_bins    = max(20, layers * 4)
                    z_bins    = np.linspace(float(np.min(vz_disp)), float(np.max(vz_disp)), n_bins + 1)
                    z_profile, r_profile = [], []
                    for bi in range(n_bins):
                        b_mask = ((vz_disp >= z_bins[bi]) & (vz_disp < z_bins[bi + 1]))
                        if b_mask.sum() >= 2:
                            r_vals = np.hypot(vx[b_mask] - hole.x, vy[b_mask] - hole.y)
                            z_profile.append(float((z_bins[bi] + z_bins[bi+1]) / 2))
                            r_profile.append(float(np.percentile(r_vals, 72)))
                    z_profile = np.array(z_profile)
                    r_profile = np.array(r_profile)

                    def mesh_radius_at_z(target_z_disp):
                        if len(z_profile) < 2: return hole.radius
                        return float(np.interp(target_z_disp, z_profile, r_profile, left=r_profile[0], right=r_profile[-1]))
                else:
                    def mesh_radius_at_z(target_z_disp): return hole.radius

                NEAR_CENTER_RATIO = 0.3
                if len(vz) == 0:
                    TRUE_TOP_Z = raw_rim_z; TRUE_BOT_Z = raw_bot_z
                else:
                    TRUE_TOP_Z   = float(np.min(vz))
                    dist_vmask   = dist_v[vmask]
                    near_c_mask  = dist_vmask < (hole.radius * NEAR_CENTER_RATIO)
                    if near_c_mask.sum() < 1: near_c_mask = np.ones(len(vz), dtype=bool)
                    TRUE_BOT_Z = float(np.max(vz[near_c_mask]))

                z_start       = dz(TRUE_TOP_Z)
                star_z        = min(z_start + hole.depth, dz(TRUE_BOT_Z))
                star_x        = hole.x
                star_y        = hole.y
                z_levels_path = np.linspace(z_start, star_z, layers)

                px_list, py_list, pz_list = [hole.x], [hole.y], [z_start]
                wall_pts      = []
                layer_centers = {}

                for layer_idx, z_disp in enumerate(z_levels_path):
                    r_at_z     = mesh_radius_at_z(z_disp) * 0.92
                    ang_offset = (np.radians(layer_idx * step_deg) if use_zigzag else 0.0)

                    layer_centers[layer_idx] = (hole.x, hole.y, z_disp, ang_offset, r_at_z)
                    px_list.append(hole.x); py_list.append(hole.y); pz_list.append(z_disp)

                    for ang in np.linspace(0, 2 * np.pi, points, endpoint=False):
                        a   = ang + ang_offset
                        ppx = hole.x + r_at_z * np.cos(a)
                        ppy = hole.y + r_at_z * np.sin(a)
                        wall_pts.append((ppx, ppy, z_disp, layer_idx))
                        px_list += [ppx, hole.x]; py_list += [ppy, hole.x]; pz_list += [z_disp, z_disp]

            # ✅ V07 FIX: Restored the lines connecting the toolpath to the bottom depth star!
            px_list.append(star_x); py_list.append(star_y); pz_list.append(star_z)
            px_list.append(hole.x); py_list.append(hole.y); pz_list.append(z_start)

            ax3d.plot(px_list, py_list, pz_list, color='yellow', linestyle='--', linewidth=1.2, label='Tool Path', alpha=0.85)

            if wall_pts:
                if zigzag_any:
                    # v08: iterate the ACTUAL layer indices present (works
                    # whether they came from one segment or several) instead
                    # of range(hole.layers), which only made sense for a
                    # single-segment hole.
                    for lidx in sorted(layer_centers.keys()):
                        pts_l = [(wx, wy, wz) for wx, wy, wz, li in wall_pts if li == lidx]
                        if not pts_l: continue
                        wx_l, wy_l, wz_l = zip(*pts_l)
                        color_l  = _layer_color(lidx)
                        if multi_seg_display:
                            lbl = f'Layer {lidx + 1}'
                        else:
                            deg_here = int(round(lidx * step_deg)) % 360
                            lbl = (f'Layer {lidx+1} (+{deg_here}°)' if lidx > 0 else 'Layer 1 (0°)')
                        ax3d.scatter(wx_l, wy_l, wz_l, color=color_l, s=26, depthshade=False, edgecolors='white', linewidths=0.4, label=lbl)

                        if lidx in layer_centers:
                            cx_lyr, cy_lyr, z_disp, ang_offset, r_at_z = layer_centers[lidx]
                            spoke_x = cx_lyr + r_at_z * np.cos(ang_offset)
                            spoke_y = cy_lyr + r_at_z * np.sin(ang_offset)
                            ax3d.plot([cx_lyr, spoke_x], [cy_lyr, spoke_y], [z_disp, z_disp], color=color_l, linewidth=2.4, alpha=0.95, zorder=12, solid_capstyle='round')
                else:
                    wx_a, wy_a, wz_a = zip(*[(wp[0], wp[1], wp[2]) for wp in wall_pts])
                    wall_label = (f'Wall Contact ({len(layer_centers)}L)' if multi_seg_display
                                  else f'Wall Contact ({layers}L×{points}P)')
                    ax3d.scatter(wx_a, wy_a, wz_a, color='red', s=22, depthshade=False, label=wall_label)

            if show_bottom_star:
                ax3d.scatter([star_x], [star_y], [star_z], color='#ffea00', s=110, marker='*', depthshade=False, label='Bottom Depth Point', zorder=10)

                text_color = '#ff3333' if has_step_hole else '#ffea00'
                source_tag = ' [STEP]' if has_step_hole else ' [Mesh]'
                ax3d.text(star_x, star_y, star_z,
                          f" ★{source_tag} X={star_x:.2f}, Y={star_y:.2f}\n   Depth={hole.depth:.2f} mm",
                          color=text_color, fontsize=7, zorder=11)

            if probe_warn_lines:
                ax3d.text2D(0.01, 0.01, "\n".join(probe_warn_lines), transform=ax3d.transAxes,
                            fontsize=9, color='#ef5350', fontweight='bold', va='bottom', ha='left',
                            bbox=dict(boxstyle='round,pad=0.4', facecolor='#1a0000', edgecolor='#ef5350', alpha=0.88), zorder=20)

            rot_tag   = f' [rot={screen_rot}°]' if screen_rot != 0 else ''
            probe_tag = '  ⚠ PROBE' if not probe_ok else ''

            # v08: multi-diameter holes summarize each segment's own
            # layers/points instead of a single shared "NL × NP" count,
            # and the zigzag tag notes it's configured per segment.
            # v09: isolate_active takes the plain single-segment label
            # path (layers/points already point at the isolated segment's
            # own settings) plus an explicit "isolated" tag so it's clear
            # the rest of the hole is hidden, not just this segment shown.
            isolate_tag = ''
            if isolate_active:
                isolate_tag = f'  🔎 Segment {app.selected_segment_idx + 1}/{len(hole.segments)} isolated'

            if multi_seg_display:
                seg_summary = " + ".join(
                    f"{cfg.layers}L×{cfg.points_per_layer}P" for cfg in hole.segments)
                layer_info  = f"{len(hole.segments)} segments [{seg_summary}]"
                zigzag_tag  = ' ↕Zigzag(per-segment)' if zigzag_any else ''
            else:
                layer_info  = f"{layers}L × {points}P = {layers*points} pts"
                zigzag_tag  = f' ↕Zigzag({step_deg}°/layer)' if use_zigzag else ''

            title_str  = (f"Customization — Hole {hole.display_id}  |  R={hole.radius:.1f} mm  Depth={hole.depth:.2f} mm  |  "
                          f"{layer_info}" + (' [STEP]' if has_step_hole else ' [Mesh]') + rot_tag + zigzag_tag + probe_tag + isolate_tag)
            ax3d.view_init(elev=-130, azim=67.5)

            hole_z_mid = (z_start + star_z) / 2.0
            half_zoom  = max(hole.radius * 1.6, abs(star_z - z_start)) * 0.55
            half_zoom  = max(half_zoom, half * 0.05)

            ax3d.set_xlim([hole.x - half_zoom, hole.x + half_zoom])
            ax3d.set_ylim([hole.y - half_zoom, hole.y + half_zoom])
            ax3d.set_zlim([hole_z_mid - half_zoom, hole_z_mid + half_zoom])

        else:
            title_str = "Customization — Select a hole to show probing path"
            ax3d.view_init(elev=-130, azim=67.5)
            ax3d.set_xlim([cx - half, cx + half])
            ax3d.set_ylim([cy - half, cy + half])
            ax3d.set_zlim([cz - half, cz + half])

        ax3d.set_title(title_str, color='#ef5350' if not probe_ok else 'white', fontsize=11, pad=10)
        for spine in [ax3d.xaxis, ax3d.yaxis, ax3d.zaxis]:
            spine.set_pane_color((0.10, 0.10, 0.10, 1.0))
            spine.line.set_color('gray')
        ax3d.tick_params(colors='white', labelsize=7)
        ax3d.set_xlabel("X (mm)", color='white', fontsize=9, labelpad=2)
        ax3d.set_ylabel("Y (mm)", color='white', fontsize=9, labelpad=2)
        ax3d.set_zlabel("Z (mm)", color='white', fontsize=9, labelpad=2)
        if has_hole:
            ax3d.legend(facecolor='#1e1e1e', edgecolor='gray', labelcolor='white', loc='upper right', fontsize=7)
        ax3d.invert_xaxis()
        app.canvas.draw()

    # ------------------------------------------------------------------
    # External API for Hover Effect (Called from UI Sidebar)
    # ------------------------------------------------------------------
    def highlight_hole(self, global_idx):
        """รับค่าจาก Sidebar เพื่อเปลี่ยนสี / Opacity ของตัวเลข 3D แบบเรียลไทม์"""
        if not hasattr(self, '_text_objects') or not self._text_objects: return
        need_redraw = False
        
        for idx, obj in self._text_objects.items():
            txt = obj['text']
            if idx == global_idx:
                if txt.get_alpha() != 1.0 or txt.get_color() != 'yellow':
                    txt.set_alpha(1.0)
                    txt.set_color('yellow')
                    txt.set_fontsize(10)
                    txt.set_fontweight('bold')
                    txt.set_zorder(1000)
                    need_redraw = True
            else:
                if txt.get_alpha() != obj['base_alpha'] or txt.get_color() != obj['base_color']:
                    txt.set_alpha(obj['base_alpha'])
                    txt.set_color(obj['base_color'])
                    txt.set_fontsize(7)
                    txt.set_fontweight('normal')
                    txt.set_zorder(obj['base_zorder'])
                    need_redraw = True
                    
        if need_redraw:
            self.app.canvas.draw_idle()

    def clear_hole_highlight(self):
        """เคลียร์ไฮไลต์ คืนค่ากลับสู่สถานะเดิม (Opacity จางสำหรับ Unselected)"""
        if not hasattr(self, '_text_objects') or not self._text_objects: return
        need_redraw = False
        
        for idx, obj in self._text_objects.items():
            txt = obj['text']
            if txt.get_alpha() != obj['base_alpha'] or txt.get_color() != obj['base_color']:
                txt.set_alpha(obj['base_alpha'])
                txt.set_color(obj['base_color'])
                txt.set_fontsize(7)
                txt.set_fontweight('normal')
                txt.set_zorder(obj['base_zorder'])
                need_redraw = True
                
        if need_redraw:
            self.app.canvas.draw_idle()