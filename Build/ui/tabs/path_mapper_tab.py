# ==============================================================================
# ui/tabs/path_mapper_tab.py — แท็บ "Path Mapper"
# ==============================================================================
# หน้าที่: วาดหน้าจอ placeholder ของแท็บ Path Mapper (ฟีเจอร์นี้ยังไม่พัฒนา)
# แสดงไอคอน 🚧 + หัวข้อ + รายการฟีเจอร์ที่จะทำในอนาคต
#
# ตัวแปรที่ปรับจูนได้:
#   future_items  = รายการข้อความฟีเจอร์ที่จะขึ้นแสดงใต้หัวข้อ (แก้ไข/เพิ่มได้)
# ==============================================================================
# ui/tabs/path_mapper_tab.py
# VERSION: 02
# CHANGE LOG (v01 -> v02):
#   FEATURE: "no hole selected" state no longer shows a plain placeholder.
#   Now draws a full 2D overview matching Selection tab's look (mesh
#   tripcolor background + hole markers/display_id, reusing app.current_x/
#   current_y/current_triangles/current_face_data already stored by
#   main_window.show_view()) PLUS a red dashed line connecting every
#   selected-for-inspection hole in display_id order — a preview of the
#   travel path between holes. This is a SEQUENTIAL preview (display_id
#   order, same top-to-bottom/left-to-right order already used in the
#   sidebar), NOT the nearest-neighbor optimized order Phase 2's G-code
#   generator will compute — noted in the footer text so it isn't
#   mistaken for the final travel path.
#   Falls back to the original short placeholder message only if no
#   view has been rendered yet (app.current_x is None) or zero holes are
#   currently selected for inspection.
#   No changes to the per-hole preview branch (_draw_hole_path) from v01.
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Circle

_LAYER_COLORS = [
    '#00bcd4', '#ff4d6d', '#7c4dff', '#69f0ae', '#ff9100', '#40c4ff',
    '#f06292', '#aeea00', '#ea80fc', '#ff6e40', '#18ffff', '#b9f6ca',
]


def _layer_color(idx: int) -> str:
    return _LAYER_COLORS[idx % len(_LAYER_COLORS)]


class PathMapperTab:
    def __init__(self, app):
        self.app = app

    # ------------------------------------------------------------------
    def draw_path_mapper(self):
        app = self.app
        app.fig.clf()
        app.ax = app.fig.add_subplot(111, facecolor='#1e1e1e')
        app.fig.subplots_adjust(left=0.08, right=0.97, bottom=0.08, top=0.90)

        if app.geo.mesh is None:
            self._draw_placeholder("Please upload a model and generate holes first.")
            return

        has_hole = (app.selected_hole_idx is not None and len(app.current_holes) > 0
                    and app.selected_hole_idx < len(app.current_holes))

        if not has_hole:
            self._draw_overview()
            return

        hole = app.current_holes[app.selected_hole_idx]
        sh   = getattr(hole, '_step_hole', None)
        has_step = (sh is not None and hasattr(app.geo, 'step_data') and app.geo.step_data is not None)

        if not has_step:
            self._draw_placeholder(
                f"Hole {getattr(hole, 'display_id', '?')}: Path Mapper preview currently supports "
                f"STEP-extracted holes only (mesh-only detection not yet supported).")
            return

        self._draw_hole_path(hole, sh)

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
        """v02: no hole selected -> full 2D overview (Selection-tab style
        mesh background) + red dashed travel-order line through every
        selected-for-inspection hole, in display_id order."""
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

        x, y, tris, fdata = app.current_x, app.current_y, app.current_triangles, app.current_face_data

        vmin, vmax = np.min(fdata), np.max(fdata)
        if vmin == vmax:
            vmax = vmin + 0.1

        ax.set_axis_on()
        ax.tripcolor(x, y, tris, facecolors=fdata, cmap=app.cmap,
                    edgecolors='none', vmin=vmin, vmax=vmax, alpha=0.55, zorder=1)

        # sort by display_id (int for selected holes — see
        # main_window._renumber_holes_by_category)
        ordered = sorted(selected_holes, key=lambda h: int(h.display_id))

        hx = [h.x for h in ordered]
        hy = [h.y for h in ordered]

        # red dashed travel-path preview
        ax.plot(hx, hy, color='#e53935', linestyle='--', linewidth=1.6,
               alpha=0.85, zorder=4, marker=None)

        ax.scatter(hx, hy, facecolors='white', edgecolors='#3694ED',
                  marker='o', s=140, linewidths=2, zorder=5)
        for h in ordered:
            ax.text(h.x, h.y, f"{h.display_id}", color='black', fontsize=8,
                   weight='bold', ha='center', va='center', zorder=6)

        # mark start point distinctly
        if ordered:
            ax.scatter([ordered[0].x], [ordered[0].y], facecolors='#66bb6a',
                      edgecolors='white', marker='o', s=170, linewidths=2, zorder=7)

        ax.set_title(f"Path Mapper — Overview ({len(ordered)} holes selected)",
                    fontsize=15, color="white")
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
               "Sequential preview (display_id order) — not the optimized "
               "route. Green = start. G-code export (Phase 2) will use "
               "nearest-neighbor ordering on raw 3D coordinates.",
               transform=ax.transAxes, fontsize=8, color='#888888',
               va='bottom', ha='left', zorder=15)

        app.canvas.draw()

    # ------------------------------------------------------------------
    def _draw_hole_path(self, hole, sh):
        app  = self.app
        ax   = app.ax
        view = app.current_view
        rot  = app.screen_rotation

        is_multi_seg = bool(getattr(hole, 'segments', None))

        if is_multi_seg:
            step_layers = app.geo.get_probe_path_layers_multi(
                sh, hole.segments, view, screen_rot=rot)
        else:
            step_layers = app.geo.get_probe_path_layers(
                sh, hole.layers, view, screen_rot=rot,
                zigzag_inspection=getattr(hole, 'zigzag_inspection', False),
                zigzag_degree=getattr(hole, 'zigzag_degree', 45.0))

        layer_centers = {}
        for lyr in step_layers:
            lidx = lyr.get('layer_idx', 0)
            layer_centers[lidx] = lyr

        all_x = [hole.x]
        all_y = [hole.y]

        ax.scatter([hole.x], [hole.y], s=90, marker='+', color='#3694ED',
                  linewidths=2, zorder=6)
        ax.text(hole.x, hole.y, f" {hole.display_id}", color='white',
               fontsize=9, fontweight='bold', va='center', zorder=7)

        for lidx in sorted(layer_centers.keys()):
            lyr    = layer_centers[lidx]
            cx     = lyr['x_display']
            cy     = lyr['y_display']
            r      = lyr['radius']
            offset = lyr.get('angle_offset', 0.0)
            pts_n  = lyr.get('points_per_layer', hole.points_per_layer)
            color  = _layer_color(lidx)

            ring = Circle((cx, cy), r, fill=False, edgecolor=color,
                          linewidth=1.4, alpha=0.85, zorder=4)
            ax.add_patch(ring)
            ax.scatter([cx], [cy], s=14, color=color, zorder=5)

            angles = np.linspace(0, 2 * np.pi, pts_n, endpoint=False) + offset
            px = cx + r * np.cos(angles)
            py = cy + r * np.sin(angles)
            ax.scatter(px, py, s=36, color=color, edgecolors='white',
                      linewidths=0.6, zorder=6)

            if offset != 0.0:
                sx = cx + r * np.cos(offset)
                sy = cy + r * np.sin(offset)
                ax.plot([cx, sx], [cy, sy], color=color, linewidth=1.8,
                       alpha=0.9, zorder=5)

            all_x.extend(px.tolist() + [cx])
            all_y.extend(py.tolist() + [cy])

        pad = max(1.0, (max(all_x) - min(all_x)) * 0.2, (max(all_y) - min(all_y)) * 0.2)
        ax.set_xlim(min(all_x) - pad, max(all_x) + pad)
        ax.set_ylim(min(all_y) - pad, max(all_y) + pad)
        ax.set_aspect('equal')
        ax.grid(True, linestyle='--', alpha=0.3, color='#444444')
        ax.set_xlabel("X-Axis (mm)", fontsize=11, color="white")
        ax.set_ylabel("Y-Axis (mm)", fontsize=11, color="white")

        if is_multi_seg:
            seg_summary = " + ".join(
                f"{cfg.layers}L×{cfg.points_per_layer}P" for cfg in hole.segments)
            plan_info = f"{len(hole.segments)} segments [{seg_summary}]"
        else:
            zz = f" ↕{hole.zigzag_degree}°/layer" if getattr(hole, 'zigzag_inspection', False) else ""
            plan_info = f"{hole.layers}L × {hole.points_per_layer}P = {hole.layers * hole.points_per_layer} pts{zz}"

        title = (f"Path Mapper — Hole {hole.display_id}  |  "
                 f"R={hole.radius:.1f} mm  Depth={hole.depth:.2f} mm  |  {plan_info}")
        ax.set_title(title, fontsize=13, color="white")

        ax.text(0.01, 0.01,
               "Preview only — view-projected, not machine coordinates. "
               "G-code export (Phase 2) uses raw 3D geometry.",
               transform=ax.transAxes, fontsize=8, color='#666666',
               va='bottom', ha='left', zorder=15)

        app.canvas.draw()