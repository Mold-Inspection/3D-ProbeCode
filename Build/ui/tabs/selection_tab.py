# ==============================================================================
# ui/tabs/selection_tab.py — แท็บ "Selection" (มุมมอง 2D + เลือก/ปักหมุดรู)
# ==============================================================================
# หน้าที่หลักของไฟล์นี้:
#   - วาดกราฟ 2D (tripcolor) แสดงความลึกของชิ้นงานตามมุมมองที่เลือก
#   - จัดการ event เมาส์: scroll (ซูม), click (ปักหมุดวัดความลึก), hover (แสดง tooltip)
#   - ตรวจจับรู (clustering) จากพื้นผิว mesh กรณีไม่มีข้อมูล STEP
#   - คำนวณความลึก ณ ตำแหน่งเมาส์ ทั้งจากพื้นผิว mesh และจาก step-hole cache
#
# ตัวแปรสำคัญที่ปรับจูนได้ (อยู่กระจายในฟังก์ชันต่าง ๆ ด้านล่าง มีคอมเมนต์กำกับจุด):
#   MAX_PINS            = จำนวนหมุดวัดความลึกสูงสุดที่ปักบนกราฟได้พร้อมกัน
#   cluster_radius       = รัศมีรวมกลุ่มจุด (mm) สำหรับตรวจจับว่าเป็นรูเดียวกัน
#   min cluster size (>5)= จำนวนจุดขั้นต่ำในกลุ่มก่อนจะนับว่าเป็น "รู"
#   NEAR_CENTER_RATIO     = สัดส่วนรัศมีที่ถือว่า "ใกล้ศูนย์กลางรู" (ใช้หาก้นรู)
#   OPEN_THRESHOLD/FLOOR_TOLERANCE = ค่าความคลาดเคลื่อนตรวจสอบปาก/ก้นรูจาก STEP
#   base_scale            = อัตราการซูมเข้า/ออกต่อการเลื่อนสกรอลล์ 1 ครั้ง
# ==============================================================================
import numpy as np

from ui import theme


class SelectionTab:
    def __init__(self, app):
        self.app = app
        self._pinned_annotations = []
        self._pin_markers        = []
        self._pinned_pin_data    = []   # [(x, y, depth), …]
        self.MAX_PINS = 10   # จำนวนหมุดวัดความลึกสูงสุดที่ปักบนกราฟได้พร้อมกัน — ปรับได้

        self._unselected_marker_artists = []

        # --- Performance (ดู "Overlay / blitting" ด้านล่าง) ---
        self._event_cids = []     # id ของ handler ที่ผูกกับ canvas อยู่ตอนนี้
        self._overlay    = []     # artist ที่เปลี่ยนบ่อย (hover, วงรู, เลขรู) — วาดทับแบบ blit
        self._bg         = None   # ภาพพื้นหลัง (mesh + แกน) ที่ cache ไว้หลัง draw เต็มครั้งล่าสุด
        self._bg_stale   = True   # True = มี draw เต็มรออยู่ ห้าม blit ทับภาพเก่า
        self._tri_cache  = None   # ค่าคงที่ต่อสามเหลี่ยมสำหรับ _get_depth_surface()
        self._hole_proj_cache = None   # ตำแหน่งปากรูบนจอของ STEP holes ในมุมมองปัจจุบัน

    def setup_events(self):
        # FIX: เดิม mpl_connect ซ้ำทุกครั้งที่กลับมาแท็บ Selection โดยไม่เคยถอดของเก่า
        # → handler สะสม (สลับแท็บ 10 ครั้ง = on_motion ทำงาน 11 รอบต่อการขยับเมาส์ 1 ครั้ง)
        # ตอนนี้ถอดชุดเก่าก่อนผูกชุดใหม่เสมอ
        cv = self.app.canvas
        for cid in self._event_cids:
            cv.mpl_disconnect(cid)
        self._event_cids = [
            cv.mpl_connect('scroll_event',         self.on_scroll),
            cv.mpl_connect('button_press_event',   self.on_press),
            cv.mpl_connect('button_release_event', self.on_release),
            cv.mpl_connect('motion_notify_event',  self.on_motion),
            cv.mpl_connect('draw_event',           self._on_full_draw),
        ]

    # ------------------------------------------------------------------
    # Overlay / blitting
    # ------------------------------------------------------------------
    # การ draw เต็ม 1 ครั้งต้อง render สามเหลี่ยมของ mesh ใหม่ทั้งหมด (~0.2 วินาที
    # ที่ 10k faces, มากกว่านั้นกับชิ้นงานใหญ่) เดิมทุกการขยับเมาส์ / hover แถวรู /
    # เลือกรู เรียก draw เต็มทั้งหมด ทำให้ค่า Depth ตามเมาส์กระตุก
    # ตอนนี้ของที่เปลี่ยนบ่อย (hover_text, วงรู, เลขรู, marker รูที่ไม่ได้เลือก) เป็น
    # artist แบบ animated: draw เต็มจะข้ามไป แล้วเราวาดทับบนภาพพื้นหลังที่ cache
    # ไว้ (blit) ซึ่งใช้เวลาไม่กี่มิลลิวินาที
    def _on_full_draw(self, _event=None):
        if self.app.current_tab != "Selection":
            self._bg = None
            return
        cv = self.app.canvas
        self._bg = cv.copy_from_bbox(cv.figure.bbox)
        self._bg_stale = False
        self._draw_overlay()

    def _draw_overlay(self):
        fig = self.app.fig
        self._overlay = [a for a in self._overlay if a.axes is not None]
        for artist in sorted(self._overlay, key=lambda a: a.get_zorder()):
            fig.draw_artist(artist)

    def refresh_overlay(self):
        """วาดเฉพาะ overlay ใหม่ (เร็ว) — ถ้ายังไม่มีภาพพื้นหลังที่ใช้ได้ ให้ draw เต็มแทน"""
        cv = self.app.canvas
        if self._bg is None or self._bg_stale or self.app.current_tab != "Selection":
            cv.draw_idle()
            return
        cv.restore_region(self._bg)
        self._draw_overlay()
        cv.blit(cv.figure.bbox)

    def request_full_draw(self):
        """ของที่ไม่ใช่ overlay เปลี่ยน (ซูม, ปัก/ถอนหมุด) — ต้อง draw เต็ม"""
        self._bg_stale = True
        self.app.canvas.draw_idle()

    # ------------------------------------------------------------------
    # Pin Management
    # ------------------------------------------------------------------
    def clear_pins(self):
        for ann in self._pinned_annotations:
            try: ann.remove()
            except Exception: pass
        for marker in self._pin_markers:
            try: marker.remove()
            except Exception: pass
        self._pinned_annotations = []
        self._pin_markers        = []
        self._pinned_pin_data    = []

    def _draw_single_pin(self, px, py, depth):
        marker = self.app.ax.plot(
            px, py,
            marker='o', color='#ff4444', markersize=6,
            markeredgecolor='white', markeredgewidth=0.8,
            zorder=18)[0]

        ann = self.app.ax.annotate(
            f"▶ {depth:.2f} mm",
            xy=(px, py), xytext=(12, 12),
            textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.35", fc=theme.c(theme.BG_PANEL),
                      ec="#ff4444", alpha=0.95),
            color="#ff9999", fontsize=9, fontweight='bold',
            zorder=19)

        self._pinned_annotations.append(ann)
        self._pin_markers.append(marker)

    def _restore_pins(self, saved_pins):
        self._pinned_annotations = []
        self._pin_markers        = []
        self._pinned_pin_data    = []

        for px, py, depth in saved_pins:
            self._draw_single_pin(px, py, depth)
            self._pinned_pin_data.append((px, py, depth))

        if saved_pins:
            self.request_full_draw()

    def highlight_hole(self, global_idx):
        app = self.app
        if app.current_tab != "Selection" or not app.scatter_holes:
            return
        local_idx = getattr(app, '_visible_hole_map', {}).get(global_idx)
        if local_idx is None:
            return

        colors = ['white'] * app.current_holes_count
        if app.selected_hole_idx is not None:
            sel_local = getattr(app, '_visible_hole_map', {}).get(app.selected_hole_idx)
            if sel_local is not None:
                colors[sel_local] = 'yellow'
        colors[local_idx] = 'yellow'
        app.scatter_holes.set_facecolors(colors)
        self.refresh_overlay()

    def clear_hole_highlight(self):
        app = self.app
        if app.current_tab != "Selection" or not app.scatter_holes:
            return

        colors = ['white'] * app.current_holes_count
        if app.selected_hole_idx is not None:
            sel_local = getattr(app, '_visible_hole_map', {}).get(app.selected_hole_idx)
            if sel_local is not None:
                colors[sel_local] = 'yellow'
        app.scatter_holes.set_facecolors(colors)
        self.refresh_overlay()

    def show_unselected_marker(self, hole):
        app = self.app
        self.clear_unselected_marker()
        if app.current_tab != "Selection":
            return
        if getattr(hole, 'position_unknown', False) or hole.x is None or hole.y is None:
            return

        marker = app.ax.scatter(
            [hole.x], [hole.y],
            s=230, marker='o',
            facecolors='white', edgecolors='#e53935', linewidths=2.6,
            zorder=25, clip_on=True, animated=True)
        label = app.ax.text(
            hole.x, hole.y, "U",
            color='#e53935', fontsize=12, fontweight='bold',
            ha='center', va='center', zorder=26, clip_on=True, animated=True)

        self._unselected_marker_artists = [marker, label]
        self._overlay += [marker, label]
        self.refresh_overlay()

    def clear_unselected_marker(self):
        if not self._unselected_marker_artists:
            return   # ไม่มีอะไรต้องลบ — ไม่ต้องวาดใหม่
        for artist in self._unselected_marker_artists:
            try:
                artist.remove()
            except Exception:
                pass
        self._unselected_marker_artists = []
        self.refresh_overlay()

    # ------------------------------------------------------------------
    # Depth calculation
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

        view_name  = app.current_view
        screen_rot = app.screen_rotation
        projector  = geo.projector
        total_depth = projector.get_view_params(
            view_name, screen_rot)['total_depth']

        # ค่าคลาดเคลื่อนที่ยอมรับได้เมื่อเทียบตำแหน่งเมาส์กับปาก/ก้นรูจาก STEP (mm)
        # — ปรับสัดส่วน (0.03 / 0.04) หรือค่าต่ำสุด (1.5 / 1.0) ได้ตามความละเอียดโมเดล
        OPEN_THRESHOLD = max(total_depth * 0.03, 1.5)
        FLOOR_TOLERANCE = max(total_depth * 0.04, 1.0)

        best_floor_depth = None
        best_dist        = float('inf')

        # ตำแหน่งปากรูบนจอไม่ขึ้นกับตำแหน่งเมาส์ — คำนวณครั้งเดียวต่อมุมมอง
        # (update_plot() ล้าง cache นี้) แทนการ project ทุกรูใหม่ทุกครั้งที่เมาส์ขยับ
        cache_key = (view_name, screen_rot, id(step_holes), len(step_holes))
        if self._hole_proj_cache is None or self._hole_proj_cache[0] != cache_key:
            projected = []
            for sh in step_holes:
                ox, oy, od = projector.project_point_to_view(
                    *sh.open_3d, view_name, screen_rot)
                dx, dy, dd = projector.project_point_to_view(
                    *sh.deep_3d, view_name, screen_rot)
                # ช่องสี่เหลี่ยมใช้รัศมีวงกลมที่ครอบมุม ไม่ใช่ครึ่งด้านแคบ
                r_hit = (sh.outer_radius if getattr(sh, 'shape', 'circle') == 'rect'
                         else sh.radius_open)
                if od <= dd:
                    projected.append((ox, oy, od, dd, r_hit))
                else:
                    projected.append((dx, dy, dd, od, r_hit))
            self._hole_proj_cache = (cache_key, projected)

        for open_x, open_y, open_d, deep_d, r in self._hole_proj_cache[1]:
            if open_d > OPEN_THRESHOLD:
                continue

            dist_2d  = np.hypot(mx - open_x, my - open_y)

            # ระยะห่างสูงสุด (เท่าของรัศมีปากรู) ที่ยังนับว่าเมาส์ชี้อยู่ในรูนี้ — ปรับได้
            if dist_2d > r * 1.3:
                continue

            hole_floor_depth = deep_d - open_d
            if dist_2d < best_dist:
                best_dist        = dist_2d
                best_floor_depth = hole_floor_depth

        if best_floor_depth is None:
            return surface_depth

        if abs(surface_depth - best_floor_depth) <= FLOOR_TOLERANCE:
            return max(0.0, best_floor_depth)

        return surface_depth

    def _get_depth_surface(self, mx, my):
        app = self.app
        if not hasattr(app, 'current_x')         or app.current_x is None:          return None
        if not hasattr(app, 'current_triangles') or app.current_triangles is None:  return None
        if not hasattr(app, 'current_face_data') or app.current_face_data is None:  return None

        fdata = app.current_face_data

        # ค่าที่ขึ้นกับสามเหลี่ยมอย่างเดียว (ไม่ขึ้นกับตำแหน่งเมาส์) คำนวณครั้งเดียวต่อ
        # มุมมอง แล้วใช้ซ้ำทุกการขยับเมาส์ — update_plot() ล้าง cache นี้เมื่อ mesh เปลี่ยน
        c = self._tri_cache
        if c is None:
            x, y = app.current_x, app.current_y
            tris = app.current_triangles
            x0, y0 = x[tris[:, 0]], y[tris[:, 0]]
            x1, y1 = x[tris[:, 1]], y[tris[:, 1]]
            x2, y2 = x[tris[:, 2]], y[tris[:, 2]]
            denom  = (x0 - x2) * (y1 - y2) - (x1 - x2) * (y0 - y2)
            valid  = np.abs(denom) > 1e-10
            inv    = 1.0 / np.where(valid, denom, 1.0)
            c = self._tri_cache = {
                'x2': x2, 'y2': y2, 'valid': valid,
                'a': (y1 - y2) * inv, 'b': (x1 - x2) * inv,
                'c': (x0 - x2) * inv, 'd': (y0 - y2) * inv,
                'xmin': np.minimum(np.minimum(x0, x1), x2), 'xmax': np.maximum(np.maximum(x0, x1), x2),
                'ymin': np.minimum(np.minimum(y0, y1), y2), 'ymax': np.maximum(np.maximum(y0, y1), y2),
            }

        # คัดเฉพาะสามเหลี่ยมที่กรอบครอบคลุมจุดนี้ก่อน (เหลือไม่กี่สิบจากทั้ง mesh)
        cand = np.nonzero((c['xmin'] <= mx) & (mx <= c['xmax']) &
                          (c['ymin'] <= my) & (my <= c['ymax']) & c['valid'])[0]
        if cand.size == 0:
            return None
        dX, dY = mx - c['x2'][cand], my - c['y2'][cand]
        l0 = dX * c['a'][cand] - c['b'][cand] * dY
        l1 = c['c'][cand] * dY - dX * c['d'][cand]
        l2 = 1.0 - l0 - l1

        inside = (l0 >= -1e-6) & (l1 >= -1e-6) & (l2 >= -1e-6)
        if not np.any(inside):
            return None

        ti         = cand[np.nonzero(inside)[0][0]]   # สามเหลี่ยมแรกตามลำดับเดิม (เหมือนก่อนแก้)
        depth_here = fdata[ti]
        return max(0.0, float(depth_here))

    def _get_depth_at(self, mx, my):
        app      = self.app
        has_step = (hasattr(app.geo, 'step_data') and app.geo.step_data is not None)
        if has_step:
            return self._get_depth_at_step(mx, my)
        else:
            return self._get_depth_surface(mx, my)

    # ------------------------------------------------------------------
    def detect_holes_in_view(self, x, y, z, view_name):
        """ตรวจจับรูจากพื้นผิว mesh ด้วยการรวมกลุ่มจุด (clustering) — ใช้เฉพาะ
        กรณีไม่มีข้อมูล STEP (ไฟล์ STL/mesh ล้วน)"""
        if len(z) == 0:
            return []

        # ระยะขอบเขต (mm) ที่ตัดพื้นผิวบนสุด/ล่างสุดออก ก่อนเริ่มหารู — ปรับได้
        Z_EDGE_MARGIN = 1.0

        if view_name in ['Front', 'Right']:
            surface_z        = np.max(z)
            bottom_z         = np.min(z)
            valid_indices    = np.where((z < surface_z - Z_EDGE_MARGIN) & (z > bottom_z + Z_EDGE_MARGIN))[0]
            is_positive_view = True
        else:
            surface_z        = np.min(z)
            bottom_z         = np.max(z)
            valid_indices    = np.where((z > surface_z + Z_EDGE_MARGIN) & (z < bottom_z - Z_EDGE_MARGIN))[0]
            is_positive_view = False

        if len(valid_indices) == 0:
            return []

        holes          = []
        cluster_radius = 15.0   # รัศมีรวมกลุ่มจุด (mm) ที่ถือว่าอยู่ในรูเดียวกัน — ปรับได้
        remaining      = set(valid_indices)

        while remaining:
            idx     = remaining.pop()
            cluster = [idx]
            queue   = [idx]

            while queue:
                current        = queue.pop(0)
                curr_x, curr_y = x[current], y[current]
                if not remaining:
                    break

                rem_arr   = np.array(list(remaining))
                dists     = np.hypot(x[rem_arr] - curr_x, y[rem_arr] - curr_y)
                neighbors = rem_arr[dists < cluster_radius]
                for n in neighbors:
                    remaining.remove(n)
                    cluster.append(n)
                    queue.append(n)

            # จำนวนจุดขั้นต่ำในกลุ่มก่อนนับว่าเป็น "รู" (กันจุดรบกวน/noise) — ปรับได้
            MIN_CLUSTER_SIZE = 5
            if len(cluster) > MIN_CLUSTER_SIZE:
                cluster_x  = x[cluster]
                cluster_y  = y[cluster]
                cluster_z  = z[cluster]
                center_x   = float(np.mean(cluster_x))
                center_y   = float(np.mean(cluster_y))
                distances  = np.hypot(cluster_x - center_x, cluster_y - center_y)
                radius     = float(np.percentile(distances, 95))
                if radius < 1.0:
                    radius = 2.0   # รัศมีขั้นต่ำสำรอง (mm) กรณีคำนวณได้เล็กผิดปกติ — ปรับได้

                # สัดส่วนรัศมีที่ถือว่า "ใกล้ศูนย์กลางรู" ใช้หาความลึกก้นรู — ปรับได้
                NEAR_CENTER_RATIO = 0.3
                near_center_mask  = distances < (radius * NEAR_CENTER_RATIO)
                if near_center_mask.sum() < 1:
                    near_center_mask = np.ones(len(cluster_z), dtype=bool)

                if is_positive_view:
                    surf_z     = surface_z
                    bot_z      = float(np.min(cluster_z[near_center_mask]))
                    max_depth  = float(surf_z - bot_z)
                    hole_top_z = float(np.max(cluster_z))
                else:
                    surf_z     = surface_z
                    bot_z      = float(np.max(cluster_z[near_center_mask]))
                    max_depth  = float(bot_z - surf_z)
                    hole_top_z = float(np.min(cluster_z))

                hid = len(holes) + 1
                hf  = HoleFeature(hid, center_x, center_y, surf_z, bot_z, max_depth, radius)
                hf.hole_top_z = hole_top_z
                holes.append(hf)

        holes.sort(key=lambda h: (-round(h.y / 5.0), h.x))
        for i, h in enumerate(holes):
            h.id = i + 1
        return holes

    # ------------------------------------------------------------------
    def update_plot(self, x, y, z_vert, face_data, triangles, title, holes=None):
        app = self.app
        if app.current_tab != "Selection":
            return

        self._pinned_annotations = []
        self._pin_markers        = []
        self._unselected_marker_artists = []
        self._overlay   = []
        self._tri_cache = None
        self._hole_proj_cache = None
        self._bg_stale  = True

        app.ax.clear()
        if hasattr(app, 'cax') and app.cax is not None:
            app.cax.clear()
            app.cax.set_visible(True)
        app.ax.set_axis_on()

        app.current_x         = x
        app.current_y         = y
        app.current_z         = z_vert
        app.current_triangles = triangles
        app.current_face_data = face_data

        vmin, vmax = np.min(face_data), np.max(face_data)
        if vmin == vmax:
            vmax = vmin + 0.1

        tpc = app.ax.tripcolor(x, y, triangles, facecolors=face_data,
                               cmap=app.cmap, edgecolors='none',
                               vmin=vmin, vmax=vmax)

        if holes:
            hole_x = [h.x for h in holes]
            hole_y = [h.y for h in holes]
            app.current_holes_count = len(holes)
            initial_colors = ['white'] * app.current_holes_count
            if app.selected_hole_idx is not None:
                local_idx = getattr(app, '_visible_hole_map', {}).get(app.selected_hole_idx)
                if local_idx is not None and 0 <= local_idx < app.current_holes_count:
                    initial_colors[local_idx] = 'yellow'

            app.scatter_holes = app.ax.scatter(
                hole_x, hole_y, facecolors=initial_colors,
                edgecolors="#3694ED", marker='o', s=150,
                linewidths=2, zorder=5, clip_on=True, animated=True)
            self._overlay.append(app.scatter_holes)
            self._draw_hole_outlines(holes)
            for i, h in enumerate(holes):
                self._overlay.append(app.ax.text(
                    h.x, h.y, f"{h.display_id}",
                    color='black', fontsize=8,
                    weight='bold', ha='center', va='center',
                    zorder=6, clip_on=True, animated=True))
        else:
            app.scatter_holes       = None
            app.current_holes_count = 0

        lock_text = " [LOCKED]" if getattr(app, 'holes_detected', False) else ""
        rot_text  = f" (Rotated {app.screen_rotation}°)" if getattr(app, 'screen_rotation', 0) > 0 else ""
        app.ax.set_title(title + rot_text + lock_text, fontsize=16, color=theme.c(theme.TEXT))

        app.ax.grid(True, linestyle='--', alpha=0.3, color=theme.c(theme.PLOT_GRID))
        app.ax.set_xlabel("X-Axis (mm)", fontsize=12, fontweight='bold', color=theme.c(theme.TEXT))
        app.ax.set_ylabel("Y-Axis (mm)", fontsize=12, fontweight='bold', color=theme.c(theme.TEXT))

        if getattr(app, 'max_physical_dim', None) is not None and len(app.current_x) > 0:
            cx        = (np.min(app.current_x) + np.max(app.current_x)) / 2.0
            cy        = (np.min(app.current_y) + np.max(app.current_y)) / 2.0
            half_span = (app.max_physical_dim / 2.0) * 1.15   # margin รอบชิ้นงานเมื่อ fit หน้าจอ (15%) — ปรับได้
            app.ax.set_xlim([cx - half_span, cx + half_span])
            app.ax.set_ylim([cy - half_span, cy + half_span])

        app.ax.set_aspect('equal')

        if hasattr(app, 'cax') and app.cax is not None:
            cbar = app.fig.colorbar(tpc, cax=app.cax)
            cbar.set_label("Depth / Z-Axis (mm)", fontsize=12, color=theme.c(theme.TEXT))
            cbar.ax.yaxis.set_tick_params(color=theme.c(theme.TEXT_MUTED), labelcolor=theme.c(theme.TEXT_MUTED))

        app.hover_text = app.ax.annotate(
            "", xy=(0, 0), xytext=(14, 14),
            textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.4", fc=theme.c(theme.BG_PANEL),
                      ec="#3694ED", alpha=0.92),
            color=theme.c(theme.TEXT), fontsize=10, visible=False, zorder=20, animated=True)
        self._overlay.append(app.hover_text)

        app.ax.text(
            0.01, 0.01,
            f"Click = Pin depth (max {self.MAX_PINS})  |  Right-click = Remove last pin",
            transform=app.ax.transAxes,
            fontsize=8, color=theme.c(theme.TEXT_MUTED), va='bottom', ha='left', zorder=15)

        app.canvas.draw()

    def _draw_hole_outlines(self, holes):
        """วาดขอบจริงของทุกรูบนมุมมอง 2D — รูกลม (วงกลมทุกขนาดของรู counterbore)
        และช่องสี่เหลี่ยม/slot — เป็นส่วนของพื้นหลัง (ไม่ animated) จึงไม่ต้อง
        วาดใหม่ตอน hover"""
        app = self.app
        projector = app.geo.projector
        for h in holes:
            sh = getattr(h, '_step_hole', None)
            if sh is None:
                # รูจาก mesh (ไม่มี STEP) — มีแค่จุดศูนย์กลาง/รัศมีบนจอ วาดวงกลมตรง ๆ
                if getattr(h, 'radius', None):
                    ang = np.linspace(0.0, 2 * np.pi, 49)
                    app.ax.plot(h.x + h.radius * np.cos(ang), h.y + h.radius * np.sin(ang),
                                color="#3694ED", linewidth=1.6, zorder=4, clip_on=True)
                continue
            for outline in sh.outlines_3d():
                xy = [projector.project_point_to_view(*p, app.current_view, app.screen_rotation)[:2]
                      for p in outline]
                ox, oy = zip(*xy)
                app.ax.plot(ox, oy, color="#3694ED", linewidth=1.6, zorder=4, clip_on=True)

    # ------------------------------------------------------------------
    def on_press(self, event):
        if event.inaxes != self.app.ax:               return
        if self.app.current_tab != "Selection":       return
        if event.xdata is None or event.ydata is None: return

        if event.button == 3:
            if self._pinned_annotations:
                self._pinned_annotations.pop().remove()
                self._pin_markers.pop().remove()
                if self._pinned_pin_data:
                    self._pinned_pin_data.pop()
                self.request_full_draw()
            return

        if event.button == 1:
            if len(self._pinned_annotations) >= self.MAX_PINS:
                return
            depth = self._get_depth_at(event.xdata, event.ydata)
            if depth is None:
                return
            self._draw_single_pin(event.xdata, event.ydata, depth)
            self._pinned_pin_data.append((event.xdata, event.ydata, depth))
            self.request_full_draw()

    def on_release(self, event):
        pass

    def on_motion(self, event):
        app = self.app
        # FIX: เดิมสั่ง draw เต็มทุกครั้งที่เมาส์ขยับ แม้อยู่แท็บอื่น (เช่นกราฟ 3D ของ
        # Customization ถูกวาดใหม่ทั้งภาพทุกการขยับเมาส์) — แท็บอื่นไม่ต้องทำอะไรเลย
        if app.current_tab != "Selection":
            return
        hover = getattr(app, 'hover_text', None)
        if hover is None:
            return

        depth = None
        if event.inaxes == app.ax and event.xdata is not None and event.ydata is not None:
            depth = self._get_depth_at(event.xdata, event.ydata)

        if depth is None:
            if hover.get_visible():        # วาดใหม่เฉพาะตอนที่ต้องซ่อนจริง ๆ
                hover.set_visible(False)
                self.refresh_overlay()
            return

        hover.set_text(f"Depth: {depth:.2f} mm")
        hover.xy = (event.xdata, event.ydata)
        hover.set_visible(True)
        self.refresh_overlay()

    def on_scroll(self, event):
        if event.inaxes != self.app.ax:              return
        if self.app.current_tab == "Path Mapper":    return

        base_scale   = 1.2   # อัตราซูมเข้า/ออกต่อการเลื่อนสกรอลล์ 1 ครั้ง (ยิ่งมาก ยิ่งซูมไว) — ปรับได้
        scale_factor = 1 / base_scale if event.button == 'up' else base_scale
        xdata, ydata = event.xdata, event.ydata
        xlim, ylim   = self.app.ax.get_xlim(), self.app.ax.get_ylim()
        new_width    = (xlim[1] - xlim[0]) * scale_factor
        new_height   = (ylim[1] - ylim[0]) * scale_factor
        relx = (xlim[1] - xdata) / (xlim[1] - xlim[0])
        rely = (ylim[1] - ydata) / (ylim[1] - ylim[0])
        self.app.ax.set_xlim([xdata - new_width  * (1 - relx), xdata + new_width  * relx])
        self.app.ax.set_ylim([ydata - new_height * (1 - rely), ydata + new_height * rely])
        # draw_idle (ไม่ใช่ draw): หมุนล้อเมาส์เร็ว ๆ หลายคลิกจะรวมเป็นการวาดครั้งเดียว
        self.request_full_draw()
