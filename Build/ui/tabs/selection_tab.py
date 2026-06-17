# ui/tabs/selection_tab.py
import numpy as np
from core.models import HoleFeature

class SelectionTab:
    def __init__(self, app):
        self.app = app
        self._pinned_annotations = []
        self._pin_markers = []
        # เก็บข้อมูลดิบของ pin (x, y, depth) แยกจาก matplotlib artist
        # เพื่อให้ reset_position() สามารถ restore pin กลับมาได้หลัง ax.clear()
        self._pinned_pin_data = []
        self.MAX_PINS = 10

    def setup_events(self):
        self.app.canvas.mpl_connect('scroll_event', self.on_scroll)
        self.app.canvas.mpl_connect('button_press_event', self.on_press)
        self.app.canvas.mpl_connect('button_release_event', self.on_release)
        self.app.canvas.mpl_connect('motion_notify_event', self.on_motion)

    # ------------------------------------------------------------------
    # Pin Management
    # ------------------------------------------------------------------
    def _draw_single_pin(self, px, py, depth):
        """วาด pin ใหม่ 1 จุดลงบน ax ปัจจุบัน และเก็บ artist ไว้"""
        marker = self.app.ax.plot(
            px, py,
            marker='o', color='#ff4444', markersize=6,
            markeredgecolor='white', markeredgewidth=0.8,
            zorder=18)[0]

        ann = self.app.ax.annotate(
            f"▶ {depth:.2f} mm",
            xy=(px, py),
            xytext=(12, 12),
            textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.35", fc="#1e1e1e", ec="#ff4444", alpha=0.95),
            color="#ff9999", fontsize=9, fontweight='bold',
            zorder=19)

        self._pinned_annotations.append(ann)
        self._pin_markers.append(marker)

    def _restore_pins(self, saved_pins):
        """
        วาด pin ทั้งหมดจาก saved_pins กลับบน ax ใหม่หลัง redraw
        เรียกจาก main_window.reset_position() หลัง show_view() เสร็จ
        """
        # ล้าง artist list เก่า (ถูก clear ไปแล้วตอน ax.clear())
        self._pinned_annotations = []
        self._pin_markers = []
        self._pinned_pin_data = []

        for px, py, depth in saved_pins:
            self._draw_single_pin(px, py, depth)
            self._pinned_pin_data.append((px, py, depth))

        if saved_pins:
            self.app.canvas.draw_idle()

    # ------------------------------------------------------------------
    # คำนวณความลึก ณ ตำแหน่ง (mx, my)
    # ------------------------------------------------------------------
    def _get_depth_at_step(self, mx, my):
        app = self.app
        geo = app.geo

        surface_depth = self._get_depth_surface(mx, my)
        if surface_depth is None:
            return None

        step_holes = getattr(geo.extractor, '_step_holes_cache', [])
        if not step_holes:
            return surface_depth

        view_name = app.current_view
        projector = geo.projector
        total_depth = projector.get_view_params(view_name)['total_depth']
        OPEN_THRESHOLD = max(total_depth * 0.03, 1.5)
        FLOOR_TOLERANCE = max(total_depth * 0.04, 1.0)

        best_floor_depth = None
        best_dist  = float('inf')

        for sh in step_holes:
            ox, oy, od = projector.project_point_to_view(*sh.open_3d, view_name)
            dx, dy, dd = projector.project_point_to_view(*sh.deep_3d, view_name)

            if od <= dd:
                open_x, open_y, open_d = ox, oy, od
                deep_d = dd
            else:
                open_x, open_y, open_d = dx, dy, dd
                deep_d = od

            if open_d > OPEN_THRESHOLD:
                continue

            r = sh.radius_open
            dist_2d = np.hypot(mx - open_x, my - open_y)

            if dist_2d > r * 1.3:
                continue

            hole_floor_depth = deep_d - open_d
            if dist_2d < best_dist:
                best_dist = dist_2d
                best_floor_depth = hole_floor_depth

        if best_floor_depth is None:
            return surface_depth

        if abs(surface_depth - best_floor_depth) <= FLOOR_TOLERANCE:
            return max(0.0, best_floor_depth)

        return surface_depth

    def _get_depth_surface(self, mx, my):
        app = self.app
        if not hasattr(app, 'current_x') or app.current_x is None: return None
        if not hasattr(app, 'current_triangles') or app.current_triangles is None: return None
        if not hasattr(app, 'current_face_data') or app.current_face_data is None: return None

        x, y    = app.current_x, app.current_y
        tris    = app.current_triangles
        fdata   = app.current_face_data

        x0, y0 = x[tris[:, 0]], y[tris[:, 0]]
        x1, y1 = x[tris[:, 1]], y[tris[:, 1]]
        x2, y2 = x[tris[:, 2]], y[tris[:, 2]]

        denom      = (x0 - x2) * (y1 - y2) - (x1 - x2) * (y0 - y2)
        valid      = np.abs(denom) > 1e-10
        denom_safe = np.where(valid, denom, 1.0)

        dX, dY = mx - x2, my - y2
        l0 = ((dX) * (y1 - y2) - (x1 - x2) * (dY)) / denom_safe
        l1 = ((x0 - x2) * (dY) - (dX) * (y0 - y2)) / denom_safe
        l2 = 1.0 - l0 - l1

        inside = valid & (l0 >= -1e-6) & (l1 >= -1e-6) & (l2 >= -1e-6)
        if not np.any(inside): return None

        ti = np.where(inside)[0][0]
        depth_here = fdata[ti]
        return max(0.0, float(depth_here))

    def _get_depth_at(self, mx, my):
        """Entry point: เลือก STEP หรือ STL อัตโนมัติ"""
        app = self.app
        has_step = (hasattr(app.geo, 'step_data') and app.geo.step_data is not None)
        if has_step:
            return self._get_depth_at_step(mx, my)
        else:
            return self._get_depth_surface(mx, my)

    # ------------------------------------------------------------------
    def detect_holes_in_view(self, x, y, z, view_name):
        if len(z) == 0: return []

        if view_name in ['Front', 'Right']:
            surface_z    = np.max(z)
            bottom_z     = np.min(z)
            valid_indices = np.where((z < surface_z - 1.0) & (z > bottom_z + 1.0))[0]
            is_positive_view = True
        else:
            surface_z    = np.min(z)
            bottom_z     = np.max(z)
            valid_indices = np.where((z > surface_z + 1.0) & (z < bottom_z - 1.0))[0]
            is_positive_view = False

        if len(valid_indices) == 0: return []

        holes = []
        cluster_radius = 15.0
        remaining = set(valid_indices)

        while remaining:
            idx   = remaining.pop()
            cluster = [idx]
            queue   = [idx]

            while queue:
                current        = queue.pop(0)
                curr_x, curr_y = x[current], y[current]
                if not remaining: break

                rem_arr   = np.array(list(remaining))
                dists     = np.hypot(x[rem_arr] - curr_x, y[rem_arr] - curr_y)
                neighbors = rem_arr[dists < cluster_radius]
                for n in neighbors:
                    remaining.remove(n)
                    cluster.append(n)
                    queue.append(n)

            if len(cluster) > 5:
                cluster_x  = x[cluster]
                cluster_y  = y[cluster]
                cluster_z  = z[cluster]
                center_x   = float(np.mean(cluster_x))
                center_y   = float(np.mean(cluster_y))
                distances  = np.hypot(cluster_x - center_x, cluster_y - center_y)
                radius     = float(np.percentile(distances, 95))
                if radius < 1.0: radius = 2.0

                NEAR_CENTER_RATIO = 0.3
                near_center_mask  = distances < (radius * NEAR_CENTER_RATIO)
                if near_center_mask.sum() < 1:
                    near_center_mask = np.ones(len(cluster_z), dtype=bool)

                if is_positive_view:
                    surf_z    = surface_z
                    bot_z     = float(np.min(cluster_z[near_center_mask]))
                    max_depth = float(surf_z - bot_z)
                    hole_top_z = float(np.max(cluster_z))
                else:
                    surf_z    = surface_z
                    bot_z     = float(np.max(cluster_z[near_center_mask]))
                    max_depth = float(bot_z - surf_z)
                    hole_top_z = float(np.min(cluster_z))

                hid = len(holes) + 1
                hf  = HoleFeature(hid, center_x, center_y, surf_z, bot_z, max_depth, radius)
                hf.hole_top_z = hole_top_z
                holes.append(hf)

        holes.sort(key=lambda h: (-round(h.y / 5.0), h.x))
        for i, h in enumerate(holes):
            h.id = i + 1
        return holes

    def update_plot(self, x, y, z_vert, face_data, triangles, title, holes=None):
        app = self.app
        if app.current_tab != "Selection": return

        # ล้าง artist list (ax.clear() ด้านล่างทำให้ artist เดิม invalid แล้ว)
        # ข้อมูลดิบ (_pinned_pin_data) ยังคงอยู่ใน SelectionTab ตามปกติ
        # reset_position() จะ save/restore ข้อมูลดิบนั้นเอง
        self._pinned_annotations = []
        self._pin_markers = []
        # หมายเหตุ: ไม่ล้าง _pinned_pin_data ที่นี่ เพราะ reset_position()
        # ต้องอ่านก่อน call show_view() → update_plot() และ restore ทีหลัง

        app.ax.clear()
        if hasattr(app, 'cax') and app.cax is not None:
            app.cax.clear()
            app.cax.set_visible(True)
        app.ax.set_axis_on()

        app.current_x, app.current_y, app.current_z = x, y, z_vert
        app.current_triangles = triangles
        app.current_face_data = face_data

        vmin, vmax = np.min(face_data), np.max(face_data)
        if vmin == vmax: vmax = vmin + 0.1

        tpc = app.ax.tripcolor(x, y, triangles, facecolors=face_data,
                               cmap=app.cmap, edgecolors='none', vmin=vmin, vmax=vmax)

        if holes:
            hole_x = [h.x for h in holes]
            hole_y = [h.y for h in holes]
            app.current_holes_count = len(holes)
            initial_colors = ['white'] * app.current_holes_count

            if app.selected_hole_idx is not None and 0 <= app.selected_hole_idx < app.current_holes_count:
                initial_colors[app.selected_hole_idx] = 'yellow'

            app.scatter_holes = app.ax.scatter(
                hole_x, hole_y, facecolors=initial_colors,
                edgecolors="#3694ED", marker='o', s=150,
                linewidths=2, zorder=5, clip_on=True)
            for i, h in enumerate(holes):
                app.ax.text(h.x, h.y, f"{h.id}", color='black', fontsize=8,
                            weight='bold', ha='center', va='center', zorder=6, clip_on=True)
        else:
            app.scatter_holes = None
            app.current_holes_count = 0

        lock_text = " [LOCKED]" if app.holes_detected else ""
        rot_text  = f" (Rotated {app.screen_rotation}°)" if app.screen_rotation > 0 else ""
        app.ax.set_title(title + rot_text + lock_text, fontsize=16, color="white")

        app.ax.grid(True, linestyle='--', alpha=0.3, color='#444444')
        app.ax.set_xlabel("X-Axis (mm)", fontsize=12, fontweight='bold', color="white")
        app.ax.set_ylabel("Y-Axis (mm)", fontsize=12, fontweight='bold', color="white")

        if app.max_physical_dim is not None and len(app.current_x) > 0:
            cx = (np.min(app.current_x) + np.max(app.current_x)) / 2.0
            cy = (np.min(app.current_y) + np.max(app.current_y)) / 2.0
            half_span = (app.max_physical_dim / 2.0) * 1.15
            app.ax.set_xlim([cx - half_span, cx + half_span])
            app.ax.set_ylim([cy - half_span, cy + half_span])

        app.ax.set_aspect('equal')

        if hasattr(app, 'cax') and app.cax is not None:
            cbar = app.fig.colorbar(tpc, cax=app.cax)
            cbar.set_label("Depth / Z-Axis (mm)", fontsize=12, color="white")
            cbar.ax.yaxis.set_tick_params(color='white', labelcolor='white')

        app.hover_text = app.ax.annotate(
            "", xy=(0, 0), xytext=(14, 14),
            textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.4", fc="#1e1e1e", ec="#3694ED", alpha=0.92),
            color="white", fontsize=10, visible=False, zorder=20)

        app.ax.text(0.01, 0.01,
                    f"Click = Pin depth (max {self.MAX_PINS})  |  Right-click = Remove last pin",
                    transform=app.ax.transAxes,
                    fontsize=8, color='#666666', va='bottom', ha='left', zorder=15)

        # หมายเหตุ: ไม่ draw pins ที่นี่ — reset_position() จะเรียก _restore_pins()
        # ทีหลัง และ normal flow (click ใหม่) ก็ไม่ต้องการ restore อะไร

        app.canvas.draw()

    # ------------------------------------------------------------------
    def on_press(self, event):
        if event.inaxes != self.app.ax: return
        if self.app.current_tab != "Selection": return
        if event.xdata is None or event.ydata is None: return

        if event.button == 3:
            if self._pinned_annotations:
                self._pinned_annotations.pop().remove()
                self._pin_markers.pop().remove()
                if self._pinned_pin_data:
                    self._pinned_pin_data.pop()
                self.app.canvas.draw_idle()
            return

        if event.button == 1:
            if len(self._pinned_annotations) >= self.MAX_PINS:
                return

            depth = self._get_depth_at(event.xdata, event.ydata)
            if depth is None: return

            # วาด pin และบันทึกข้อมูลดิบพร้อมกัน
            self._draw_single_pin(event.xdata, event.ydata, depth)
            self._pinned_pin_data.append((event.xdata, event.ydata, depth))
            self.app.canvas.draw_idle()

    def on_release(self, event):
        pass

    def on_motion(self, event):
        if not hasattr(self.app, 'hover_text'): return

        if event.inaxes != self.app.ax or self.app.current_tab != "Selection":
            self.app.hover_text.set_visible(False)
            self.app.canvas.draw_idle()
            return

        if event.xdata is None or event.ydata is None:
            self.app.hover_text.set_visible(False)
            self.app.canvas.draw_idle()
            return

        depth = self._get_depth_at(event.xdata, event.ydata)

        if depth is not None:
            self.app.hover_text.set_text(f"Depth: {depth:.2f} mm")
            self.app.hover_text.xy = (event.xdata, event.ydata)
            self.app.hover_text.set_visible(True)
        else:
            self.app.hover_text.set_visible(False)

        self.app.canvas.draw_idle()

    def on_scroll(self, event):
        if event.inaxes != self.app.ax: return
        if self.app.current_tab == "Path Mapper": return

        base_scale   = 1.2
        scale_factor = 1 / base_scale if event.button == 'up' else base_scale
        xdata, ydata = event.xdata, event.ydata
        xlim, ylim   = self.app.ax.get_xlim(), self.app.ax.get_ylim()
        new_width    = (xlim[1] - xlim[0]) * scale_factor
        new_height   = (ylim[1] - ylim[0]) * scale_factor
        relx = (xlim[1] - xdata) / (xlim[1] - xlim[0])
        rely = (ylim[1] - ydata) / (ylim[1] - ylim[0])
        self.app.ax.set_xlim([xdata - new_width  * (1 - relx), xdata + new_width  * relx])
        self.app.ax.set_ylim([ydata - new_height * (1 - rely), ydata + new_height * rely])
        self.app.canvas.draw()
