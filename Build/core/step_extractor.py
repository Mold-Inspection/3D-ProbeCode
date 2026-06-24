# core/step_extractor.py
import numpy as np
import math
import copy
from core.models import StepHole


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

                # ----------------------------------------------------------
                # Bug Fix A: Accept ALL CIRCLE edges, not only closed ones.
                #
                # The original code required e.IsClosed() == True, which
                # only matched full 360° circles.  Many real STEP files
                # (including counterbored / countersunk holes) represent the
                # cylinder ends as open arcs whose IsClosed() returns False.
                # We now collect every CIRCLE-type edge regardless of whether
                # it is reported as closed, because the arc centre still gives
                # us the correct hole axis endpoint.
                # ----------------------------------------------------------
                circle_edges = [e for e in face.Edges()
                                if e.geomType() == 'CIRCLE']

                if len(circle_edges) < 2:
                    continue

                circle_data = []
                for edge in circle_edges:
                    c  = edge.Center()
                    ex = float(c.x) - cx_off
                    ey = float(c.y) - cy_off
                    ez = float(c.z) - cz_off
                    r  = edge.Length() / (2 * math.pi)
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
                circle_data.sort(key=lambda d: ax * d[0] + ay * d[1] + az * d[2])

                end_a, end_b = tuple(circle_data[0][:3]), tuple(circle_data[-1][:3])
                r_a,   r_b   = circle_data[0][3], circle_data[-1][3]

                # ----------------------------------------------------------
                # Bug Fix B: Remove the hard-coded Z-axis filter.
                #
                # The original code had:
                #     if abs(az) < 0.70: continue
                # This discarded every hole whose axis was not close to
                # vertical (Z-direction).  Parts like flat clamping plates
                # have holes that drill along Y (axis = (0,1,0)), giving
                # az = 0, so ALL holes were silently dropped at extract time.
                #
                # The correct place to decide whether a hole is visible is
                # get_step_holes_in_view(), which projects the hole into the
                # current view and checks the open-end depth.  Removing this
                # filter here lets every geometrically valid cylinder through
                # to that per-view visibility check.
                # ----------------------------------------------------------

                face_depth = float(np.linalg.norm(np.array(end_b) - np.array(end_a)))
                if face_depth < 0.1:
                    continue

                mid = (np.array(end_a) + np.array(end_b)) / 2.0
                key = (round(mid[0], 1), round(mid[1], 1), round(mid[2], 1),
                       round(max(r_a, r_b), 2))

                if key in seen:
                    idx = seen[key]
                    if face_depth > holes[idx].depth:
                        holes[idx] = StepHole(end_a, end_b, r_a, r_b, (ax, ay, az))
                    continue

                seen[key] = len(holes)
                holes.append(StepHole(end_a, end_b, r_a, r_b, (ax, ay, az)))

            except Exception:
                continue

        self._step_holes_cache = holes
        print(f"[geo] STEP holes extracted: {len(holes)}")
        return holes

    # ------------------------------------------------------------------
    def get_step_holes_in_view(self, projector, view_name: str,
                                screen_rot: int = 0):
        """
        Return the subset of cached STEP holes visible from *view_name*.

        ``screen_rot`` must match the current on-screen rotation so that
        display_x / display_y are consistent with what the canvas shows.
        """
        if not self._step_holes_cache:
            return []

        p                = projector.get_view_params(view_name, screen_rot)
        part_total_depth = p['total_depth']

        # ------------------------------------------------------------------
        # Bug Fix C: OPEN_THRESHOLD was too tight (0.03 multiplier + 1.5 mm
        # floor), causing holes to be rejected even when they genuinely open
        # near the surface.
        #
        # Example: a 22.2 mm-thick plate with holes that open 1.548 mm from
        # the front face:
        #   OLD  →  max(22.2 * 0.03, 1.5) = 1.50  →  1.548 > 1.50  FAIL
        #   NEW  →  max(22.2 * 0.08, 2.0) = 2.00  →  1.548 ≤ 2.00  PASS ✅
        #
        # The 0.08 multiplier still rejects holes that are clearly not at
        # the surface (anything deeper than ~8 % of the part thickness), so
        # false positives on deeply buried holes remain suppressed.
        # ------------------------------------------------------------------
        OPEN_THRESHOLD = max(part_total_depth * 0.08, 2.0)
        MIN_DEPTH      = max(part_total_depth * 0.05, 0.5)

        result = []
        for h in self._step_holes_cache:
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
            if open_depth > OPEN_THRESHOLD or actual_depth < MIN_DEPTH:
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
