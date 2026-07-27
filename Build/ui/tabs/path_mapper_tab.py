# ==============================================================================
# ui/tabs/path_mapper_tab.py — แท็บ "Path Mapper"
# ==============================================================================
# หน้าที่: วาดหน้าจอ placeholder ของแท็บ Path Mapper (ฟีเจอร์นี้ยังไม่พัฒนา)
# แสดงไอคอน 🚧 + หัวข้อ + รายการฟีเจอร์ที่จะทำในอนาคต
#
# ตัวแปรที่ปรับจูนได้:
#   future_items  = รายการข้อความฟีเจอร์ที่จะขึ้นแสดงใต้หัวข้อ (แก้ไข/เพิ่มได้)
# ==============================================================================
# ==============================================================================
# ui/tabs/path_mapper_tab.py — แท็บ "Path Mapper"
# ==============================================================================
# หน้าที่: วาด overview 2D (mesh background + hole markers) พร้อมเส้นทางเดิน
# เครื่องแบบ preview — ลำดับเดินเครื่องต้องตรงกับที่ G-code จริงจะวิ่ง
#
# ตัวแปรที่ปรับจูนได้:
#   _START_COLOR / _BASE_FACE / _BASE_EDGE / _HILITE_FACE / _HILITE_EDGE / _SKIP_COLOR
#     = สี marker ในแต่ละสถานะ (จุดเริ่ม / ปกติ / ไฮไลต์ / ข้าม-ไม่มี STEP)
# ==============================================================================
# VERSION: 03
# CHANGE LOG (v02 -> v03):
#   FEATURE: Overview travel line now walks holes in the SAME order the
#   real G-code will visit them (greedy nearest-neighbor over raw 3D
#   open_3d coordinates), via the new shared core/hole_ordering.py
#   module — no longer the plain display_id sequential order. Holes
#   without STEP geometry (mesh-only, can't be G-code exported either)
#   are excluded from the travel line and shown as small gray "no STEP
#   data" ✕ markers instead, mirroring gcode_export_panel.py's skip
#   warning.
#   FEATURE: highlight_hole()/clear_hole_highlight() added — clicking or
#   hovering a hole in the right sidebar while on this tab now just
#   recolors that hole's marker on the SAME overview (no page/view
#   switch), called from ui/main_window.py's on_hole_select() and the
#   existing hover bindings.
#   REMOVED (explicit decision): per-hole zoomed detail view
#   (_draw_hole_path and the has_hole/has_step routing in
#   draw_path_mapper()) — overview + highlight fully replaces it. This
#   tab now only ever shows: "no model" placeholder, "no view rendered
#   yet" placeholder, "nothing selected" placeholder, or the overview.
import numpy as np
import matplotlib.pyplot as plt

from core.hole_ordering import order_holes_nearest_neighbor, split_step_ready

_START_COLOR = '#66bb6a'
_BASE_FACE   = 'white'
_BASE_EDGE   = '#3694ED'
_HILITE_FACE = '#ffee58'
_HILITE_EDGE = '#ffee58'
_SKIP_COLOR  = '#888888'


class PathMapperTab:
    def __init__(self, app):
        self.app = app
        self._overview_scatter   = None
        self._overview_index_map = {}   # {global_idx (into app.current_holes): local scatter index}
        self._overview_base_face = []
        self._overview_base_edge = []
        self._highlighted_gidx   = None

    # ------------------------------------------------------------------
    def draw_path_mapper(self):
        app = self.app
        app.fig.clf()
        app.ax = app.fig.add_subplot(111, facecolor='#1e1e1e')
        app.fig.subplots_adjust(left=0.08, right=0.97, bottom=0.08, top=0.90)

        self._overview_scatter   = None
        self._overview_index_map = {}
        self._overview_base_face = []
        self._overview_base_edge = []
        self._highlighted_gidx   = None

        if app.geo.mesh is None:
            self._draw_placeholder("Please upload a model and generate holes first.")
            return

        self._draw_overview()

    # ------------------------------------------------------------------
    def _draw_placeholder(self, message: str):
        app = self.app
        app.ax.set_xlim(0, 1)
        app.ax.set_ylim(0, 1)
        app.ax.set_axis_off()

        app.ax.add_patch(plt.Rectangle((0.05, 0.1), 0.9, 0.8,
                          linewidth=1.5, edgecolor='#1f538d',
                          facecolor='#0d1117', zorder=1))

        app.ax.text(0.5, 0.58, '📍', fontsize=42, ha='center', va='center',
                    transform=app.ax.transAxes, zorder=2)
        app.ax.text(0.5, 0.46, message, fontsize=12, color='#aaaaaa',
                    ha='center', va='center', wrap=True,
                    transform=app.ax.transAxes, zorder=2)

        app.canvas.draw()

    # ------------------------------------------------------------------
    def _draw_overview(self):
        """เส้นทางเดินเครื่อง preview — เดินตามลำดับเดียวกับ G-code จริง
        (nearest-neighbor บนพิกัด 3D ดิบ ผ่าน core/hole_ordering.py)"""
        app = self.app
        ax  = app.ax

        has_view_data = (getattr(app, 'current_x', None) is not None and
                          getattr(app, 'current_triangles', None) is not None and
                          getattr(app, 'current_face_data', None) is not None)

        if not has_view_data:
            self._draw_placeholder("Select a view (Selection tab) to preview the overall probe route here.")
            return

        selected_holes = [h for h in app.current_holes
                          if getattr(h, 'selected_for_inspection', False)
                          and h.x is not None and h.y is not None]

        if not selected_holes:
            self._draw_placeholder("No holes are currently selected for inspection.")
            return

        # global index lookup (into app.current_holes) — ใช้จับคู่ตอน highlight_hole()
        gidx_of = {id(h): gi for gi, h in enumerate(app.current_holes)}

        ready, skipped = split_step_ready(selected_holes)
        ordered = order_holes_nearest_neighbor(ready)

        x, y, tris, fdata = app.current_x, app.current_y, app.current_triangles, app.current_face_data

        vmin, vmax = np.min(fdata), np.max(fdata)
        if vmin == vmax:
            vmax = vmin + 0.1

        ax.set_axis_on()
        ax.tripcolor(x, y, tris, facecolors=fdata, cmap=app.cmap,
                    edgecolors='none', vmin=vmin, vmax=vmax, alpha=0.55, zorder=1)

        if skipped:
            sx = [h.x for h in skipped]
            sy = [h.y for h in skipped]
            ax.scatter(sx, sy, facecolors='#333333', edgecolors=_SKIP_COLOR,
                      marker='x', s=90, linewidths=2, zorder=3)
            for h in skipped:
                ax.text(h.x, h.y - 4, f"{h.display_id} (no STEP)", color=_SKIP_COLOR,
                       fontsize=7, ha='center', va='top', zorder=3)

        if ordered:
            hx = [h.x for h in ordered]
            hy = [h.y for h in ordered]

            # red dashed = actual G-code travel path
            ax.plot(hx, hy, color='#e53935', linestyle='--', linewidth=1.6,
                   alpha=0.85, zorder=4, marker=None)

            face_colors = [_START_COLOR if i == 0 else _BASE_FACE for i in range(len(ordered))]
            edge_colors = [_BASE_EDGE] * len(ordered)

            scatter = ax.scatter(hx, hy, facecolors=face_colors, edgecolors=edge_colors,
                      marker='o', s=140, linewidths=2, zorder=5)
            for h in ordered:
                ax.text(h.x, h.y, f"{h.display_id}", color='black', fontsize=8,
                       weight='bold', ha='center', va='center', zorder=6)

            self._overview_scatter   = scatter
            self._overview_base_face = list(face_colors)
            self._overview_base_edge = list(edge_colors)
            self._overview_index_map = {gidx_of[id(h)]: i for i, h in enumerate(ordered)}

        skip_tag = f", {len(skipped)} skipped (no STEP)" if skipped else ""
        ax.set_title(f"Path Mapper — Overview ({len(ordered)} holes, G-code visit order{skip_tag})",
                    fontsize=14, color="white")
        ax.grid(True, linestyle='--', alpha=0.3, color='#444444')
        ax.set_xlabel("X-Axis (mm)", fontsize=11, color="white")
        ax.set_ylabel("Y-Axis (mm)", fontsize=11, color="white")

        if getattr(app, 'max_physical_dim', None) is not None and len(x) > 0:
            cx        = (np.min(x) + np.max(x)) / 2.0
            cy        = (np.min(y) + np.max(y)) / 2.0
            half_span = (app.max_physical_dim / 2.0) * 1.15
            ax.set_xlim([cx - half_span, cx + half_span])
            ax.set_ylim([cy - half_span, cy + half_span])
        ax.set_aspect('equal')

        ax.text(0.01, 0.01,
               "Red dashed = actual G-code travel order (nearest-neighbor). "
               "Green = start point. Gray ✕ = no STEP data, skipped from G-code export.",
               transform=ax.transAxes, fontsize=8, color='#888888',
               va='bottom', ha='left', zorder=15)

        app.canvas.draw()

    # ------------------------------------------------------------------
    def highlight_hole(self, global_idx):
        """เรียกจาก ui/main_window.py ตอน click หรือ hover รูใน sidebar
        ขณะอยู่แท็บ Path Mapper — ไฮไลต์ marker บน overview เดิม ไม่สลับหน้า"""
        if self._overview_scatter is None:
            return
        local_idx = self._overview_index_map.get(global_idx)
        if local_idx is None:
            return   # รูนี้ไม่ได้อยู่บน overview (ไม่ถูกเลือก / ไม่มี STEP data)

        self._highlighted_gidx = global_idx
        face = list(self._overview_base_face)
        edge = list(self._overview_base_edge)
        face[local_idx] = _HILITE_FACE
        edge[local_idx] = _HILITE_EDGE
        self._overview_scatter.set_facecolors(face)
        self._overview_scatter.set_edgecolors(edge)
        self.app.canvas.draw_idle()

    def clear_hole_highlight(self):
        if self._overview_scatter is None or self._highlighted_gidx is None:
            return
        self._highlighted_gidx = None
        self._overview_scatter.set_facecolors(self._overview_base_face)
        self._overview_scatter.set_edgecolors(self._overview_base_edge)
        self.app.canvas.draw_idle()