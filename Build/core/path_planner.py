# core/path_planner.py
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
