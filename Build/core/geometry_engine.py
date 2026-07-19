# core/geometry_engine.py
# VERSION: 03
# CHANGE LOG (v02 -> v03):
#   FIX: forward the already-loaded mesh into extractor.extract() so it
#   can confirm/correct multi-diameter hole segment order against the
#   real mesh surface instead of trusting the B-Rep axis sign alone (see
#   step_extractor.py v25 / _orient_segments_by_mesh()). self.mesh is
#   already centered by the same mesh_centroid every extracted point
#   uses (both come from cad_loader.py's single centering step), so no
#   extra transform is needed — just pass the reference through.
# CHANGE LOG (v01 -> v02):
#   FEATURE: multi-diameter ("counterbore-style") hole support.
#     Added get_probe_path_layers_multi() — thin facade wrapper mirroring
#     the existing get_probe_path_layers(), forwarding to
#     PathPlanner.get_probe_path_layers_multi() (see path_planner.py v02).
#     UI code (customization_tab.py) decides which of the two to call
#     based on whether the hole has 2+ segments; this file makes no such
#     decision itself, same separation of concerns as the existing single
#     get_probe_path_layers().
import numpy as np

from core.cad_loader import CADLoader
from core.projector import Projector
from core.step_extractor import StepExtractor
from core.path_planner import PathPlanner


class MoldGeometry:
    """Facade Manager — coordinates all sub-modules."""

    def __init__(self, filepath=None):
        self.loader    = CADLoader()
        self.projector = Projector()
        self.extractor = StepExtractor()
        self.planner   = PathPlanner()

        self.mesh             = None
        self.step_data        = None
        self._mesh_centroid   = np.zeros(3)

        if filepath:
            self.load_file(filepath)

    def load_file(self, filepath):
        self.mesh, self.step_data, self._mesh_centroid = self.loader.load(filepath)
        self.projector.update_mesh(self.mesh)
        if self.step_data:
            self.extractor.extract(self.step_data, self._mesh_centroid)

    def get_physical_dimensions(self):
        return self.mesh.extents if self.mesh is not None else (0, 0, 0)

    # ------------------------------------------------------------------
    # View routing — screen_rot forwarded so projector cache stays consistent
    # ------------------------------------------------------------------
    def get_top_view(self,    rot=0): return self.projector.get_view('Top',    rot)
    def get_bottom_view(self, rot=0): return self.projector.get_view('Bottom', rot)
    def get_front_view(self,  rot=0): return self.projector.get_view('Front',  rot)
    def get_back_view(self,   rot=0): return self.projector.get_view('Back',   rot)
    def get_left_view(self,   rot=0): return self.projector.get_view('Left',   rot)
    def get_right_view(self,  rot=0): return self.projector.get_view('Right',  rot)

    def get_step_holes_in_view(self, view_name: str, screen_rot: int = 0):
        """screen_rot must be passed so hole display positions match the canvas."""
        return self.extractor.get_step_holes_in_view(self.projector, view_name, screen_rot, mesh=self.mesh)

    def get_probe_path_layers(self, hole, n_layers: int, view_name: str,
                               screen_rot: int = 0,
                               zigzag_inspection: bool = False,
                               zigzag_degree: float = 45.0):
        return self.planner.get_probe_path_layers(
            hole, n_layers, self.projector, view_name,
            screen_rot=screen_rot,
            zigzag_inspection=zigzag_inspection,
            zigzag_degree=zigzag_degree)

    def get_probe_path_layers_multi(self, hole, segment_settings: list,
                                     view_name: str, screen_rot: int = 0):
        """
        Segment-aware path for multi-diameter holes. `hole` is a StepHole
        with .segments (raw geometry); `segment_settings` is the matching
        list of HoleSegmentSetting (per-segment layers/points/zigzag
        config) — see path_planner.py v02 for details.
        """
        return self.planner.get_probe_path_layers_multi(
            hole, segment_settings, self.projector, view_name,
            screen_rot=screen_rot)