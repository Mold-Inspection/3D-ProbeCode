import numpy as np
from core.models import HoleFeature

class SelectionTab:
    def __init__(self, app):
        self.app = app
        self._pinned_annotations = []
        self._pin_markers = []
        self.MAX_PINS = 10

    def setup_events(self):
        self.app.canvas.mpl_connect('scroll_event', self.on_scroll)
        self.app.canvas.mpl_connect('button_press_event', self.on_press)
        self.app.canvas.mpl_connect('button_release_event', self.on_release)
        self.app.canvas.mpl_connect('motion_notify_event', self.on_motion)

    # ------------------------------------------------------------------
    # คำนวณความลึก ณ ตำแหน่ง (mx, my)
    #
    # Strategy (ลำดับความสำคัญ — รอบ 3):
    #   1. อ่านความลึกจริงจากพื้นผิว mesh ก่อนเสมอ (ตรงกับสีบนจอ 100%)
    #   2. STEP mode เท่านั้น: ถ้าค่าจากผิวใกล้เคียงพื้นก้นรู (floor) ของ
    #      STEP hole ที่ใกล้ที่สุด ให้ snap เป็นค่า floor แม่นยำจาก B-Rep
    #      แทน (กรณีนี้คือกำลังชี้อยู่บนพื้นก้นรูจริง ๆ)
    #   3. ถ้าไม่เข้าเงื่อนไข floor หรือไม่มี STEP hole เลย → ใช้ค่าจากผิว
    #      mesh ตรง ๆ (รวมถึงตอนชี้บนขอบ/ผนังรูที่กำลังไล่เฉดสีตามความชัน)
    #
    # หมายเหตุประวัติการแก้ไข:
    #   v1: คืนค่าคงที่ hole.depth ทันทีที่อยู่ในรัศมีรู (ผิดตอนชี้บนขอบ/ผนัง)
    #   v2: ลด tolerance รัศมีลง (ยังพังถ้า silhouette ใหญ่กว่ารัศมีจริง)
    #   v3 (ปัจจุบัน): เลิกใช้รัศมีตัดสิน floor/wall เปลี่ยนไปเทียบค่าจริงจาก
    #       พื้นผิว mesh กับค่า floor จาก B-Rep โดยตรง — แม่นยำไม่ว่า silhouette
    #       จะมีรูปร่างซับซ้อนแค่ไหน
    # ------------------------------------------------------------------
    def _get_depth_at_step(self, mx, my):
        """คำนวณความลึก ณ จุดที่ชี้ สำหรับไฟล์ STEP

        หมายเหตุการแก้ไข (รอบ 3 — เลิกใช้ radius fudge-factor ตัดสิน floor/wall):
        วิธีเดิมเช็คว่า "อยู่ในรัศมีรู (บวก tolerance)" แล้วถือว่าคือพื้นก้นรู
        เป็นปัญหาเพราะรัศมีที่ใช้ตัดสิน (radius_open ของรูใน B-Rep) ไม่ได้
        ตรงกับ "ขนาดจริงของพื้นที่ราบก้นรูบนจอ" เสมอไป (เช่น fillet, มุมโค้ง,
        หรือมุมมองที่ทำให้ silhouette ใหญ่กว่ารัศมีจริง) ทำให้จุดที่อยู่บน
        ขอบ/ผนังรู (ซึ่งควรไล่เฉดสีตามความชัน) ถูกตัดสินผิดว่าเป็นพื้นก้นรู
        แล้วคืนค่าคงที่ทับไป

        แนวทางใหม่: อ่านความลึกจริงจากพื้นผิว mesh ณ จุดนั้นก่อนเสมอ (ค่า
        เดียวกับสีที่วาดบนจอ) แล้วเทียบกับความลึกพื้นก้นรูของ STEP hole ที่
        ใกล้ที่สุด — ถ้าค่าจากพื้นผิวเองก็ใกล้เคียงพื้นก้นรูอยู่แล้ว (เผื่อ
        ความหยาบของ tessellation) ค่อย snap เป็นค่า floor ที่แม่นยำ 100%
        จาก B-Rep แทนค่าประมาณจาก mesh ส่วนจุดที่อยู่บนขอบ/ผนัง (ค่าจากผิว
        ไม่ใกล้ floor) จะใช้ค่าจากผิวจริงตามที่ควรเป็น
        """
        app = self.app
        geo = app.geo

        # 1) อ่านความลึกจริงจากพื้นผิว mesh ก่อนเสมอ — ค่านี้ตรงกับสีบนจอ 100%
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

            # ยังต้องอยู่ในรัศมีปากรู (กว้างพอสมควร เพราะแค่ใช้คัดเลือก "รูที่
            # เกี่ยวข้อง" ไม่ใช่ตัดสิน floor/wall อีกต่อไป)
            if dist_2d > r * 1.3:
                continue

            hole_floor_depth = deep_d - open_d
            if dist_2d < best_dist:
                best_dist = dist_2d
                best_floor_depth = hole_floor_depth

        if best_floor_depth is None:
            return surface_depth

        # 2) Snap เป็นค่า floor แม่นยำจาก B-Rep เฉพาะตอนค่าจากพื้นผิว mesh เอง
        #    ก็ใกล้เคียงค่า floor อยู่แล้ว (แสดงว่าจุดนี้อยู่บนพื้นก้นรูจริง)
        if abs(surface_depth - best_floor_depth) <= FLOOR_TOLERANCE:
            return max(0.0, best_floor_depth)

        # ไม่ใกล้พอ → จุดนี้อยู่บนขอบ/ผนังรูหรือพื้นผิวทั่วไป ใช้ค่าจากผิวจริง
        return surface_depth

    def _get_depth_surface(self, mx, my):
        """อ่านความลึก ณ จุด (mx, my) — คืนค่าที่ "ตรงกับสีที่วาดจริงบนจอ"

        สำคัญ: `ax.tripcolor(x, y, triangles, facecolors=face_data)` วาดสีแบบ
        FLAT ต่อ "หน้าสามเหลี่ยม" (1 ค่าต่อ 1 triangle จาก face_data ทั้งรูป
        ไม่ได้ไล่เฉดสีในแนวภายในสามเหลี่ยม) ดังนั้นค่าตัวเลขที่ hover/pin ต้อง
        ใช้ "ค่าเดียวกัน" กับ face_data ของ triangle ที่ cursor อยู่ใน ไม่ใช่
        การ interpolate ข้าม vertex (ซึ่งเป็นคนละค่ากับสีที่เห็นจริง และทำให้
        ตัวเลขกับสีไม่ตรงกัน เช่น ชี้บนพื้นที่สีเหลือง/ขาว แต่ตัวเลขกลับขึ้น
        ค่าระดับสีแดงลึกสุด)
        """
        app = self.app
        if not hasattr(app, 'current_x') or app.current_x is None: return None
        if not hasattr(app, 'current_triangles') or app.current_triangles is None: return None
        if not hasattr(app, 'current_face_data') or app.current_face_data is None: return None

        x, y    = app.current_x, app.current_y
        tris    = app.current_triangles
        fdata   = app.current_face_data   # ค่าเดียวกับที่ส่งให้ tripcolor(facecolors=...)

        x0, y0 = x[tris[:, 0]], y[tris[:, 0]]
        x1, y1 = x[tris[:, 1]], y[tris[:, 1]]
        x2, y2 = x[tris[:, 2]], y[tris[:, 2]]

        # หมายเหตุการแก้ไข (รอบ 4 — root cause จริง):
        # denom ตัวนี้คือ "ตัวหารบารีเซนทริก" มาตรฐาน (canonical):
        #   denom = (x0-x2)*(y1-y2) - (x1-x2)*(y0-y2)
        # โค้ดเดิมตั้งแต่ไฟล์แรกที่ได้รับมา ใช้ตัวแปรชื่อ det ที่มีค่าเป็น
        # "ค่าลบ" ของ denom มาตรฐานนี้ (det = -denom) แต่ตัวเศษ (l0, l1) ยัง
        # เขียนตามสัญญะของ denom มาตรฐาน ทำให้ผลลัพธ์ l0, l1 ติดเครื่องหมาย
        # ลบสลับกัน ส่งผลให้เงื่อนไข "inside triangle" (l0,l1,l2 >= 0) เพี้ยน
        # และจุดส่วนใหญ่ไม่ถูกจับว่าอยู่ใน triangle ไหนเลย หรือจับผิด triangle
        # — นี่คือสาเหตุจริงของค่าความลึกที่ผิดทุกภาพที่ผ่านมา ไม่ใช่แค่เรื่อง
        # threshold/fudge-factor ตามที่แก้ไปก่อนหน้า
        denom      = (x0 - x2) * (y1 - y2) - (x1 - x2) * (y0 - y2)
        valid      = np.abs(denom) > 1e-10
        denom_safe = np.where(valid, denom, 1.0)

        dX, dY = mx - x2, my - y2
        l0 = ((dX) * (y1 - y2) - (x1 - x2) * (dY)) / denom_safe
        l1 = ((x0 - x2) * (dY) - (dX) * (y0 - y2)) / denom_safe
        l2 = 1.0 - l0 - l1

        inside = valid & (l0 >= -1e-6) & (l1 >= -1e-6) & (l2 >= -1e-6)
        if not np.any(inside): return None

        # ใช้ triangle แรกที่ cursor อยู่ใน แล้วอ่านค่าความลึกของ "หน้านั้น
        # ทั้งหน้า" ตรง ๆ — เป็นค่าเดียวกับที่ ax.tripcolor(facecolors=fdata)
        # ใช้วาดสีจริงบนจอ จึงตรงกับสีที่เห็นเสมอ (ไม่ใช้ argmin/argmax แบบ
        # เลือกตามค่าความลึก เพราะนั่นจะ bias ไปทาง shallow/deep โดยไม่มีเหตุผล
        # เกี่ยวกับว่าจุดไหนคือผิวที่มองเห็นจริง — เมื่อ inside มีได้มากกว่า 1
        # แทบทุกครั้งคือ floating point ติดกันที่ขอบ triangle ไม่ใช่การซ้อนทับ
        # ของผิวหน้า/หลังจริง)
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

        self._pinned_annotations = []
        self._pin_markers = []

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
                self.app.canvas.draw_idle()
            return

        if event.button == 1:
            if len(self._pinned_annotations) >= self.MAX_PINS:
                return

            depth = self._get_depth_at(event.xdata, event.ydata)
            if depth is None: return

            marker = self.app.ax.plot(
                event.xdata, event.ydata,
                marker='o', color='#ff4444', markersize=6,
                markeredgecolor='white', markeredgewidth=0.8,
                zorder=18)[0]

            ann = self.app.ax.annotate(
                f"▶ {depth:.2f} mm",
                xy=(event.xdata, event.ydata),
                xytext=(12, 12),
                textcoords="offset points",
                bbox=dict(boxstyle="round,pad=0.35", fc="#1e1e1e", ec="#ff4444", alpha=0.95),
                color="#ff9999", fontsize=9, fontweight='bold',
                zorder=19)

            self._pinned_annotations.append(ann)
            self._pin_markers.append(marker)
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
