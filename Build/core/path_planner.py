# core/path_planner.py
# VERSION: 02
# CHANGE LOG (v01 -> v02):
#   FEATURE: multi-diameter ("counterbore-style") hole support.
#     Problem: get_probe_path_layers() built n_layers evenly spaced
#     between the hole's OVERALL open_3d/deep_3d and read radius via
#     hole.radius_at(t) — a straight-line interpolation between the two
#     outermost radii. For a hole with a real step in diameter (not a
#     taper), this smeared the step into a fake ramp, so layers landed
#     off the true wall right around the step boundary.
#     Fix: new get_probe_path_layers_multi() walks hole.segments (see
#     models.py v02 / step_extractor.py v24 — each segment is one
#     contiguous piece with its own open_3d/deep_3d/radius_open/
#     radius_deep) and, for EACH segment independently, generates that
#     segment's own layers using that segment's own
#     layers/points_per_layer/zigzag_inspection/zigzag_degree config
#     (models.HoleSegmentSetting — set per-segment by the user in the
#     sidebar "folder" UI). Radius is only ever interpolated WITHIN a
#     segment, never across a step boundary. zigzag angle offset resets
#     to 0° at the start of every segment (each segment's zigzag is
#     independent, per user's own scoping choice).
#     The original get_probe_path_layers() is UNCHANGED and still used
#     as-is for ordinary single-segment holes (HoleFeature.segments
#     empty) — this is purely additive.
import numpy as np


class PathPlanner:
    """Compute layer-by-layer probe paths for hole inspection."""

    def get_probe_path_layers(self, hole, n_layers: int, projector, view_name: str,
                               screen_rot: int = 0,
                               zigzag_inspection: bool = False,
                               zigzag_degree: float = 45.0) -> list:
        """
        Return a list of layer dicts for drawing the probe path.

        Parameters
        ----------
        hole              : StepHole (or any object with open_3d / deep_3d / radius_at)
        n_layers          : number of inspection layers
        projector         : Projector instance
        view_name         : current view name ('Top', 'Front', …)
        screen_rot        : current on-screen rotation (degrees) — must match
                            the value used when the view was rendered so that
                            projected layer positions align with the canvas
        zigzag_inspection : rotate probe angle per layer
        zigzag_degree     : cumulative rotation per layer (degrees)

        Zigzag mode
        -----------
        Layer 0 → offset = 0°
        Layer N → offset = N × zigzag_degree

        NOTE: this treats the hole as ONE continuous radius taper from
        open_3d to deep_3d (hole.radius_at). Correct for ordinary holes
        and true cones/tapers. For a hole with a real step in diameter,
        use get_probe_path_layers_multi() instead (see v02 changelog).
        """
        t_vals = np.linspace(0.0, 1.0, n_layers + 2)[1:-1]
        o = np.array(hole.open_3d)
        d = np.array(hole.deep_3d)

        layers = []
        for layer_idx, t in enumerate(t_vals):
            pt              = o + t * (d - o)
            dx, dy, depth   = projector.project_point_to_view(
                *pt, view_name, screen_rot)
            r_layer         = hole.radius_at(t)
            angle_offset    = (np.radians(layer_idx * zigzag_degree)
                               if zigzag_inspection else 0.0)

            layers.append({
                'z_display':    depth,
                'x_display':    dx,
                'y_display':    dy,
                'radius':       r_layer,
                'angle_offset': angle_offset,
                'layer_idx':    layer_idx,
            })
        return layers

    # ------------------------------------------------------------------
    def get_probe_path_layers_multi(self, hole, segment_settings: list,
                                     projector, view_name: str,
                                     screen_rot: int = 0) -> list:
        """
        Segment-aware version of get_probe_path_layers() for multi-diameter
        ("counterbore-style") holes.

        Parameters
        ----------
        hole              : StepHole whose .segments is a list of
                            core.models.HoleSegment (raw geometry, sorted
                            open-end first — see step_extractor.py v24)
        segment_settings  : list of core.models.HoleSegmentSetting, SAME
                            length and order as hole.segments — carries
                            each segment's own layers/points_per_layer/
                            zigzag_inspection/zigzag_degree
        projector, view_name, screen_rot : same as get_probe_path_layers()

        Returns
        -------
        Flat list of layer dicts (open end -> deep end, continuous), each
        with the same keys as get_probe_path_layers() PLUS:
          - 'seg_idx'          : which segment this layer belongs to
          - 'seg_local_idx'    : layer index WITHIN that segment (zigzag
                                  angle offset is computed from this, so
                                  every segment's zigzag restarts at 0°)
          - 'points_per_layer' : that segment's own point count, so the
                                  caller doesn't need a second lookup
        Radius is only ever interpolated between a segment's own
        radius_open/radius_deep — never across a step boundary into the
        next segment.
        """
        if len(segment_settings) != len(hole.segments):
            raise ValueError(
                f"segment_settings length ({len(segment_settings)}) must match "
                f"hole.segments length ({len(hole.segments)})")

        layers = []
        global_idx = 0

        for seg_idx, (seg, cfg) in enumerate(zip(hole.segments, segment_settings)):
            o = np.array(seg.open_3d)
            d = np.array(seg.deep_3d)
            t_vals = np.linspace(0.0, 1.0, cfg.layers + 2)[1:-1]

            for seg_local_idx, t in enumerate(t_vals):
                pt            = o + t * (d - o)
                dx, dy, depth = projector.project_point_to_view(
                    *pt, view_name, screen_rot)
                r_layer       = seg.radius_at(t)
                angle_offset  = (np.radians(seg_local_idx * cfg.zigzag_degree)
                                 if cfg.zigzag_inspection else 0.0)

                layers.append({
                    'z_display':        depth,
                    'x_display':        dx,
                    'y_display':        dy,
                    'radius':           r_layer,
                    'angle_offset':     angle_offset,
                    'layer_idx':        global_idx,
                    'seg_idx':          seg_idx,
                    'seg_local_idx':    seg_local_idx,
                    'points_per_layer': cfg.points_per_layer,
                })
                global_idx += 1

        return layers