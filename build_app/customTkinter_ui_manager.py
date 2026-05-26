import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.colors import LinearSegmentedColormap
import customtkinter as ctk
import numpy as np
import os

ctk.set_appearance_mode("Dark")  
ctk.set_default_color_theme("blue")  

# [MODIFIED] เพิ่มการเก็บค่า Layers และ Points ต่อ Layer ลงใน Object
class HoleFeature:
    def __init__(self, hid, x, y, surface_z, bottom_z, depth, radius):
        self.id = hid
        self.x = x
        self.y = y
        self.surface_z = surface_z
        self.bottom_z = bottom_z
        self.depth = depth
        self.radius = radius 
        self.layers = 3              # ค่า Default ขั้นต่ำ 3 ชั้น
        self.points_per_layer = 4    # ค่า Default ขั้นต่ำ 4 จุด

class UIManager:
    def __init__(self, geometry_engine):
        self.geo = geometry_engine
        self.marked_points = [] 
        self.current_view = 'Top'
        self.screen_rotation = 0 
        self.scatter_holes = None
        self.current_holes_count = 0
        self.current_holes = [] 
        self.holes_detected = False  
        
        self.current_tab = "Selection"
        self.selected_hole_idx = None
        self.max_physical_dim = None 
        
        self.view_buttons = {}
        self.hole_widgets = {}
        
        self.root = ctk.CTk()
        self.root.title("3D Laser Scanner Simulator")
        self.root.geometry("1400x800") 
        
        self.sidebar_left = ctk.CTkFrame(self.root, width=250, corner_radius=0)
        self.sidebar_left.pack(side="left", fill="y")
        
        self.sidebar_right = ctk.CTkFrame(self.root, width=350, corner_radius=0, fg_color="#181818")
        self.sidebar_right.pack_propagate(False) 
        self.sidebar_right.pack(side="right", fill="y")
        
        self.center_frame = ctk.CTkFrame(self.root, corner_radius=0, fg_color="#242424")
        self.center_frame.pack(side="left", fill="both", expand=True)

        self.top_bar = ctk.CTkFrame(self.center_frame, fg_color="transparent", height=50)
        self.top_bar.pack(side="top", fill="x", padx=20, pady=(10, 0))
        
        self.nav_selector = ctk.CTkSegmentedButton(
            self.top_bar, 
            values=["Selection", "Customization", "Path Mapper"],
            command=self.on_nav_change,
            height=35,
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.nav_selector.set("Selection")
        self.nav_selector.pack(side="top", pady=5) 

        plt.style.use('dark_background')
        colors = ["white", "red"]
        self.cmap = LinearSegmentedColormap.from_list("depth_color", colors)

        self.fig = Figure(figsize=(10, 8), facecolor='#242424')
        self.fig.tight_layout(pad=3.0)
        self.ax = self.fig.add_subplot(111, facecolor='#1e1e1e')
        self.fig.subplots_adjust(bottom=0.1, right=0.85, left=0.1, top=0.9)
        self.cax = self.fig.add_axes([0.88, 0.15, 0.03, 0.7]) 
        
        self.drag_state = {'is_dragging': False, 'x': 0, 'y': 0, 'xlim': None, 'ylim': None}

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.center_frame)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.pack(fill=ctk.BOTH, expand=True, padx=10, pady=10)

        self.hover_text = self.ax.annotate(
            "", xy=(0, 0), xytext=(15, 15),
            textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.3", fc="red", ec="gray", alpha=1),
            visible=False
        )

        self._setup_left_sidebar()
        self._setup_right_sidebar()
        self._setup_events()
        
        if self.geo.mesh is not None:
            self.show_view('Top')

    def _setup_left_sidebar(self):
        ctk.CTkLabel(self.sidebar_left, text="3D CNC Control", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(20, 10))
        
        self.btn_upload = ctk.CTkButton(self.sidebar_left, text="Upload STEP or STP", fg_color="#2e7d32", hover_color="#4caf50", command=self.open_file_dialog)
        self.btn_upload.pack(pady=10, padx=20, fill="x")
        
        self.info_frame = ctk.CTkFrame(self.sidebar_left, fg_color="#1e1e1e", corner_radius=5)
        self.info_frame.pack(pady=(0, 15), padx=20, fill="x")
        
        self.lbl_width = ctk.CTkLabel(self.info_frame, text="Width (X): -- mm", text_color="gray", font=ctk.CTkFont(size=12))
        self.lbl_width.pack(pady=(5, 0), padx=10, anchor="w")
        
        self.lbl_length = ctk.CTkLabel(self.info_frame, text="Length (Y): -- mm", text_color="gray", font=ctk.CTkFont(size=12))
        self.lbl_length.pack(pady=0, padx=10, anchor="w")
        
        self.lbl_thick = ctk.CTkLabel(self.info_frame, text="Thickness (Z): -- mm", text_color="gray", font=ctk.CTkFont(size=12))
        self.lbl_thick.pack(pady=(0, 5), padx=10, anchor="w")

        self.btn_detect = ctk.CTkButton(self.sidebar_left, text="🔍 Generate Holes", fg_color="#f57c00", hover_color="#ef6c00", command=self.on_generate_holes)
        self.btn_detect.pack(pady=(10, 5), padx=20, fill="x")

        self.btn_clear = ctk.CTkButton(self.sidebar_left, text="❌ Clear & Unlock", fg_color="#c62828", hover_color="#b71c1c", command=self.on_clear_holes, state="disabled")
        self.btn_clear.pack(pady=(0, 10), padx=20, fill="x")

        ctk.CTkLabel(self.sidebar_left, text="--- View Controls ---", text_color="gray").pack(pady=(20, 5))
        
        self.btn_rotate = ctk.CTkButton(self.sidebar_left, text="⟳ Rotate 90°", fg_color="#0277bd", hover_color="#039be5", command=self.rotate_screen)
        self.btn_rotate.pack(pady=10, padx=20, fill="x")

        self.btn_reset = ctk.CTkButton(self.sidebar_left, text="⌂ Reset Position", fg_color="#d84315", hover_color="#bf360c", command=self.reset_position)
        self.btn_reset.pack(pady=(0, 10), padx=20, fill="x")

        view_frame = ctk.CTkFrame(self.sidebar_left, fg_color="transparent")
        view_frame.pack(pady=10, padx=20, fill="x")
        
        views = [('Top', 0, 0), ('Bottom', 0, 1), 
                 ('Front', 1, 0), ('Back', 1, 1), 
                 ('Left', 2, 0), ('Right', 2, 1)]
                 
        for name, row, col in views:
            btn = ctk.CTkButton(view_frame, text=name, width=85, fg_color="#424242", hover_color="#616161",
                                command=lambda v=name: self.show_view(v))
            btn.grid(row=row, column=col, padx=5, pady=5)
            self.view_buttons[name] = btn

    def _setup_right_sidebar(self):
        self.right_header = ctk.CTkLabel(self.sidebar_right, text="Detected Holes", font=ctk.CTkFont(size=16, weight="bold"))
        self.right_header.pack(pady=(20, 10), padx=20, anchor="w")

        # [MODIFIED] เปลี่ยนจาก ttk.Treeview เป็น CTkScrollableFrame
        # เพื่อรองรับ inline settings (Z-Layers / Points per Layer) ต่อรูได้โดยตรง
        self.holes_list_frame = ctk.CTkScrollableFrame(self.sidebar_right, fg_color="transparent")
        self.holes_list_frame.pack(fill="both", expand=True, padx=10, pady=5)

    def _set_view_controls_locked(self, is_locked):
        target_state = "disabled" if is_locked else "normal"
        self.btn_rotate.configure(state=target_state)
        self.btn_reset.configure(state=target_state)
        for btn in self.view_buttons.values():
            btn.configure(state=target_state)
        self.btn_detect.configure(state="disabled" if is_locked else "normal")
        self.btn_clear.configure(state="normal" if is_locked else "disabled")

    def _detect_holes_in_view(self, x, y, z, view_name):
        if len(z) == 0: return []
        
        if view_name in ['Top', 'Front', 'Right']:
            surface_z = np.max(z)
            bottom_z = np.min(z)
            valid_indices = np.where((z < surface_z - 1.0) & (z > bottom_z + 1.0))[0]
            is_positive_view = True
        else:
            surface_z = np.min(z)
            bottom_z = np.max(z)
            valid_indices = np.where((z > surface_z + 1.0) & (z < bottom_z - 1.0))[0]
            is_positive_view = False
            
        if len(valid_indices) == 0: return []

        holes = []
        cluster_radius = 15.0  
        remaining = set(valid_indices)

        while remaining:
            idx = remaining.pop()
            cluster = [idx]
            queue = [idx]
            
            while queue:
                current = queue.pop(0)
                curr_x, curr_y = x[current], y[current]
                if not remaining: break
                
                rem_arr = np.array(list(remaining))
                dists = np.hypot(x[rem_arr] - curr_x, y[rem_arr] - curr_y)
                
                neighbors = rem_arr[dists < cluster_radius]
                for n in neighbors:
                    remaining.remove(n)
                    cluster.append(n)
                    queue.append(n)
            
            if len(cluster) > 5:
                cluster_x = x[cluster]
                cluster_y = y[cluster]
                cluster_z = z[cluster]
                
                center_x = float(np.mean(cluster_x))
                center_y = float(np.mean(cluster_y))
                
                distances = np.hypot(cluster_x - center_x, cluster_y - center_y)
                radius = float(np.percentile(distances, 95))
                if radius < 1.0: radius = 2.0 
                
                if is_positive_view:
                    surf_z = surface_z
                    bot_z = float(np.min(cluster_z))
                    max_depth = float(surf_z - bot_z)
                else:
                    surf_z = surface_z
                    bot_z = float(np.max(cluster_z))
                    max_depth = float(bot_z - surf_z)
                
                hid = len(holes) + 1
                holes.append(HoleFeature(hid, center_x, center_y, surf_z, bot_z, max_depth, radius))
        
        holes.sort(key=lambda h: (-round(h.y / 5.0), h.x))
        for i, h in enumerate(holes):
            h.id = i + 1
            
        return holes

    def update_treeview(self, holes):
        # [MODIFIED] ล้าง widget ทั้งหมดใน CTkScrollableFrame แทน Treeview rows
        for widget in self.holes_list_frame.winfo_children():
            widget.destroy()
        self.hole_widgets = {}

        if not holes and self.holes_detected:
            ctk.CTkLabel(self.holes_list_frame, text="-- No holes detected --", text_color="gray").pack(pady=20)
            return
        elif not self.holes_detected:
            ctk.CTkLabel(self.holes_list_frame, text="-- Press Generate Holes --", text_color="gray").pack(pady=20)
            return

        for i, hole in enumerate(holes):
            container = ctk.CTkFrame(self.holes_list_frame, fg_color="transparent")
            container.pack(fill="x", pady=2)

            btn_text = f"🎯 Hole {hole.id} [X: {hole.x:.1f}, Y: {hole.y:.1f}] D: {hole.depth:.1f}"
            btn = ctk.CTkButton(container, text=btn_text, anchor="w",
                                fg_color="#1f1f1f", hover_color="#2c2c2c", corner_radius=4,
                                command=lambda idx=i: self.on_hole_select(idx))
            btn.pack(fill="x")

            # [NEW] settings_frame inline ต่อรู — ซ่อนไว้จนกว่าจะ expand
            settings_frame = ctk.CTkFrame(container, fg_color="#2b2b2b", corner_radius=4)

            layer_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
            layer_frame.pack(fill="x", padx=15, pady=(10, 5))
            ctk.CTkLabel(layer_frame, text="Z-Layers:").pack(side="left")
            opt_layers = ctk.CTkOptionMenu(layer_frame, values=["3", "4", "5", "6", "8", "10"],
                                           command=lambda val, idx=i: self.on_config_change_for_hole(idx),
                                           width=60, height=25)
            opt_layers.set(str(hole.layers))
            opt_layers.pack(side="right")

            points_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
            points_frame.pack(fill="x", padx=15, pady=(0, 10))
            ctk.CTkLabel(points_frame, text="Points/Layer:").pack(side="left")
            opt_points = ctk.CTkOptionMenu(points_frame, values=["4", "6", "8", "12", "16"],
                                           command=lambda val, idx=i: self.on_config_change_for_hole(idx),
                                           width=60, height=25)
            opt_points.set(str(hole.points_per_layer))
            opt_points.pack(side="right")

            self.hole_widgets[i] = {
                'container': container,
                'btn': btn,
                'settings_frame': settings_frame,
                'opt_layers': opt_layers,
                'opt_points': opt_points,
                'is_expanded': False
            }

    def on_hole_select(self, idx):
        # [MODIFIED] แทน on_tree_select — toggle expand/collapse settings_frame inline
        for i, widgets in self.hole_widgets.items():
            widgets['btn'].configure(fg_color="#1f1f1f")
            if widgets['is_expanded'] and i != idx:
                widgets['settings_frame'].pack_forget()
                widgets['is_expanded'] = False

        sel = self.hole_widgets[idx]
        sel['btn'].configure(fg_color="#1f538d")
        if not sel['is_expanded']:
            sel['settings_frame'].pack(fill="x", pady=(0, 2))
            sel['is_expanded'] = True

        self.selected_hole_idx = idx

        if self.current_tab == "Selection" and self.scatter_holes:
            colors = ['white'] * self.current_holes_count
            colors[idx] = 'yellow'
            self.scatter_holes.set_facecolors(colors)
            self.canvas.draw_idle()
        elif self.current_tab == "Customization":
            self.draw_cross_section()
        elif self.current_tab == "Path Mapper":
            self.draw_path_mapper()

    def on_config_change_for_hole(self, idx):
        # [NEW] อัปเดต layers/points ต่อรูจาก inline dropdown
        if idx >= len(self.current_holes):
            return
        hole = self.current_holes[idx]
        widgets = self.hole_widgets[idx]
        hole.layers = int(widgets['opt_layers'].get())
        hole.points_per_layer = int(widgets['opt_points'].get())
        if self.current_tab == "Path Mapper":
            self.draw_path_mapper()
        elif self.current_tab == "Customization":
            self.draw_cross_section()

    # [KEPT] on_config_change เดิม — ยังใช้กับ Customization/Path Mapper ผ่าน selected_hole_idx
    def on_config_change(self, value):
        if self.selected_hole_idx is not None:
            hole = self.current_holes[self.selected_hole_idx]
            hole.layers = int(self.var_layers.get()) if hasattr(self, 'var_layers') else hole.layers
            hole.points_per_layer = int(self.var_points.get()) if hasattr(self, 'var_points') else hole.points_per_layer
            if self.current_tab == "Path Mapper":
                self.draw_path_mapper()

    def on_tree_click(self, event):
        return "break"

    def draw_cross_section(self):
        # [MODIFIED] Customization mode: แสดงเฉพาะ 3D Path Map แบบเต็มหน้าจอ
        # ลบ 2D cross-section ออก, ลบ safe Z-path (clearance) ออก,
        # เพิ่มแสดงพื้นผิว (surface disk) ที่จุดลึกที่สุดของรู
        self.fig.clf()

        # ซ่อน colorbar axis (ไม่ใช้ใน Customization)
        if hasattr(self, 'cax'):
            self.cax = None

        if self.selected_hole_idx is None or not self.current_holes:
            self.ax = self.fig.add_subplot(111, facecolor='#1e1e1e')
            self.ax.set_title("Please select a hole from the right panel to analyze.", color="white", fontsize=16)
            self.ax.set_axis_off()
            self.canvas.draw()
            return

        hole = self.current_holes[self.selected_hole_idx]

        # ══════════════════════════════════════════
        # 3D Path Map เต็มหน้าจอ (ไม่มี 2D cross-section)
        # ══════════════════════════════════════════
        self.fig.subplots_adjust(left=0.0, right=1.0, top=1.0, bottom=0.0)
        ax_path = self.fig.add_subplot(111, projection='3d', facecolor='#1e1e1e')
        self.ax = ax_path

        layers = hole.layers
        points = hole.points_per_layer

        # [FIX] z_levels:
        #   - เริ่มจาก surface_z ลงมา (layer แรกอยู่ใต้ปาก ไม่เกินขอบบน)
        #   - layer สุดท้ายหยุดก่อนถึง bottom จริง ด้วย margin = 10% ของความลึก (อย่างน้อย 1 mm)
        z_margin_top    = max(hole.depth * 0.05, 0.5)   # ระยะห่างจากปากรูลงมา
        z_margin_bottom = max(hole.depth * 0.10, 1.0)   # ระยะห่างจาก bottom ขึ้นมา (layer สุดท้าย)
        z_levels = np.linspace(hole.surface_z - z_margin_top,
                               hole.bottom_z  + z_margin_bottom,
                               layers)

        # วาด Wireframe กระบอก (ผนังรู)
        z_cyl = np.linspace(hole.bottom_z, hole.surface_z, 15)
        theta = np.linspace(0, 2*np.pi, 20)
        theta_grid, z_grid = np.meshgrid(theta, z_cyl)
        ax_path.plot_wireframe(hole.x + hole.radius * np.cos(theta_grid),
                               hole.y + hole.radius * np.sin(theta_grid),
                               z_grid, color='#0277bd', alpha=0.25)

        # [NEW] วาดพื้นผิวที่จุดลึกที่สุด (bottom surface disk) เพื่อยืนยันทิศทางของรู
        theta_fill = np.linspace(0, 2*np.pi, 60)
        r_fill = np.linspace(0, hole.radius, 8)
        theta_disk, r_disk = np.meshgrid(theta_fill, r_fill)
        disk_x = hole.x + r_disk * np.cos(theta_disk)
        disk_y = hole.y + r_disk * np.sin(theta_disk)
        disk_z = np.full_like(disk_x, hole.bottom_z)
        ax_path.plot_surface(disk_x, disk_y, disk_z, color='#00e5ff', alpha=0.35, linewidth=0)
        # วาดวงกลมขอบ bottom เพื่อให้เห็นชัด
        ax_path.plot(hole.x + hole.radius * np.cos(theta_fill),
                     hole.y + hole.radius * np.sin(theta_fill),
                     np.full_like(theta_fill, hole.bottom_z),
                     color='#00e5ff', linewidth=1.5, alpha=0.7)
        # label บน bottom surface
        ax_path.text(hole.x, hole.y, hole.bottom_z,
                     f"Bottom Z={hole.bottom_z:.2f}", color='#00e5ff',
                     fontsize=7, ha='center', va='top', zorder=10)

        # ══════════════════════════════════════════
        # สร้าง Tool Path
        # - จุดสัมผัสผนังอยู่ที่ขอบ (radius พอดี) ไม่เลยออกนอกชิ้นงาน
        # - เดินจากกึ่งกลาง → ขอบโดยตรง ไม่มี overshoot
        # - หลังครบทุก layer เพิ่มจุดกึ่งกลางที่ bottom_z เพื่อวัดความลึกสูงสุด
        # ══════════════════════════════════════════
        path_x, path_y, path_z = [hole.x], [hole.y], [hole.surface_z]
        touch_x, touch_y, touch_z = [], [], []

        for z in z_levels:
            # ลงมาที่ระดับชั้น
            path_x.append(hole.x); path_y.append(hole.y); path_z.append(z)
            for ang in np.linspace(0, 2*np.pi, points, endpoint=False):
                # เดินตรงออกไปแตะขอบ (radius พอดี = ขอบชิ้นงาน)
                px = hole.x + hole.radius * np.cos(ang)
                py = hole.y + hole.radius * np.sin(ang)
                touch_x.append(px); touch_y.append(py); touch_z.append(z)
                path_x.append(px);  path_y.append(py);  path_z.append(z)
                # ถอยกลับกึ่งกลางก่อนไปจุดถัดไป
                path_x.append(hole.x); path_y.append(hole.y); path_z.append(z)

        # [NEW] จุดกึ่งกลางที่ bottom_z — วัดความลึกสูงสุด
        path_x.append(hole.x); path_y.append(hole.y); path_z.append(hole.bottom_z)
        touch_x.append(hole.x); touch_y.append(hole.y); touch_z.append(hole.bottom_z)
        # ถอยกลับขึ้น surface
        path_x.append(hole.x); path_y.append(hole.y); path_z.append(hole.surface_z)

        ax_path.plot(path_x, path_y, path_z, color='yellow', linestyle='--', linewidth=1.2,
                     label='Tool Path', alpha=0.8)
        # จุดสัมผัสผนัง
        wall_touch_x = touch_x[:-1]; wall_touch_y = touch_y[:-1]; wall_touch_z = touch_z[:-1]
        ax_path.scatter(wall_touch_x, wall_touch_y, wall_touch_z, color='red', s=25,
                        depthshade=False, label='Wall Contact Points')
        # จุดกึ่งกลาง bottom — แยกสีให้เห็นชัด
        ax_path.scatter([touch_x[-1]], [touch_y[-1]], [touch_z[-1]], color='#ffea00', s=80,
                        marker='*', depthshade=False, label='Bottom Depth Point', zorder=10)

        # [FIX] ปรับ scale แกน X, Y, Z ให้สมดุลกัน — ป้องกัน Z ยาวบิดเบี้ยว
        max_r = hole.radius * 1.6
        z_range = hole.surface_z - hole.bottom_z
        xy_range = max_r * 2

        # บังคับให้ทุกแกนมีสัดส่วนเท่ากันด้วยการสร้าง bounding cube
        mid_x, mid_y = hole.x, hole.y
        mid_z = (hole.bottom_z + hole.surface_z) / 2.0
        max_range = max(xy_range, z_range) / 2.0

        ax_path.set_xlim([mid_x - max_range, mid_x + max_range])
        ax_path.set_ylim([mid_y - max_range, mid_y + max_range])
        ax_path.set_zlim([mid_z - max_range, mid_z + max_range])

        # ตกแต่ง 3D plot
        ax_path.set_title(f"3D Probing Path — Hole {hole.id}  |  {layers}L × {points}P + 1 bottom = {layers*points + 1} pts  |  Depth: {hole.depth:.2f} mm",
                          color='white', fontsize=12, pad=12)
        for spine in [ax_path.xaxis, ax_path.yaxis, ax_path.zaxis]:
            spine.set_pane_color((0, 0, 0, 0))
            spine.line.set_color("gray")
        ax_path.tick_params(colors='white', labelsize=7)
        ax_path.set_xlabel("X (mm)", color='white', fontsize=9, labelpad=2)
        ax_path.set_ylabel("Y (mm)", color='white', fontsize=9, labelpad=2)
        ax_path.set_zlabel("Z (mm)", color='white', fontsize=9, labelpad=2)
        ax_path.legend(facecolor='#1e1e1e', edgecolor='gray', labelcolor='white',
                       loc='upper right', fontsize=7)

        self.canvas.draw()

    # [PLACEHOLDER] Path Mapper — สำรองไว้สำหรับพัฒนาในอนาคต
    # จะใช้รับ Log File จาก OpenBuilds และแสดงผลเปรียบเทียบพิกัดจริง vs CAD
    def draw_path_mapper(self):
        self.fig.clf()
        self.ax = self.fig.add_subplot(111, facecolor='#1a1a2e')
        self.fig.subplots_adjust(left=0, right=1, bottom=0, top=1)

        self.ax.set_xlim(0, 1)
        self.ax.set_ylim(0, 1)
        self.ax.set_axis_off()

        # กล่องกรอบหลัก
        self.ax.add_patch(plt.Rectangle((0.05, 0.1), 0.9, 0.8,
                          linewidth=1.5, edgecolor='#1f538d',
                          facecolor='#0d1117', zorder=1))

        # ไอคอนและข้อความ
        self.ax.text(0.5, 0.72, '🚧', fontsize=42, ha='center', va='center',
                     transform=self.ax.transAxes, zorder=2)

        self.ax.text(0.5, 0.58, 'Path Mapper', fontsize=22, fontweight='bold',
                     color='white', ha='center', va='center',
                     transform=self.ax.transAxes, zorder=2)

        self.ax.text(0.5, 0.48, 'Under Development', fontsize=13,
                     color='#1f538d', ha='center', va='center',
                     transform=self.ax.transAxes, zorder=2)

        # เส้นแบ่ง
        self.ax.plot([0.15, 0.85], [0.43, 0.43], color='#1f538d',
                     linewidth=0.8, alpha=0.6, transform=self.ax.transAxes)

        # รายการฟีเจอร์ที่จะทำในอนาคต
        future_items = [
            "📂  Import G38.2 Log File from OpenBuilds",
            "📐  Apply Probe Radius Compensation",
            "⭕  Least Squares Circle Fitting per Layer",
            "📊  Deviation Report vs CAD Reference",
        ]
        for i, item in enumerate(future_items):
            self.ax.text(0.5, 0.36 - i * 0.065, item, fontsize=10,
                         color='#aaaaaa', ha='center', va='center',
                         transform=self.ax.transAxes, zorder=2)

        self.canvas.draw()

    def on_nav_change(self, selected_tab):
        self.current_tab = selected_tab

        if selected_tab == "Selection":
            self.sidebar_right.pack(side="right", fill="y", before=self.center_frame)
            # เสมอ rebuild 2D subplot ให้สะอาด ไม่ว่าจะมาจาก Customization (3D axis) หรือที่ไหน
            self.fig.clf()
            self.ax = self.fig.add_subplot(111, facecolor='#1e1e1e')
            self.fig.subplots_adjust(bottom=0.1, right=0.85, left=0.1, top=0.9)
            self.cax = self.fig.add_axes([0.88, 0.15, 0.03, 0.7])
            self._setup_events()
            self.show_view(self.current_view)

        elif selected_tab == "Customization":
            self.sidebar_right.pack(side="right", fill="y", before=self.center_frame)
            self.draw_cross_section()

        elif selected_tab == "Path Mapper":
            self.sidebar_right.pack(side="right", fill="y", before=self.center_frame)
            self.draw_path_mapper()
            
    def on_generate_holes(self):
        if self.geo.mesh is None: return
        self.holes_detected = True
        self._set_view_controls_locked(True) 
        if self.current_tab == "Selection":
            self.show_view(self.current_view)
        
    def on_clear_holes(self):
        self.holes_detected = False
        self.current_holes = []
        self.selected_hole_idx = None
        self._set_view_controls_locked(False)

        # rebuild 2D subplot ให้ถูกต้องก่อน nav ไป Selection
        self.fig.clf()
        self.ax = self.fig.add_subplot(111, facecolor='#1e1e1e')
        self.fig.subplots_adjust(bottom=0.1, right=0.85, left=0.1, top=0.9)
        self.cax = self.fig.add_axes([0.88, 0.15, 0.03, 0.7])
        self._setup_events()

        self.nav_selector.set("Selection")
        self.current_tab = "Selection"
        self.show_view(self.current_view)

    def rotate_screen(self):
        if self.geo.mesh is None: return
        self.screen_rotation = (self.screen_rotation + 90) % 360
        self.show_view(self.current_view)

    def reset_position(self):
        if self.geo.mesh is not None:
            self.show_view(self.current_view)

    def open_file_dialog(self):
        filepath = ctk.filedialog.askopenfilename(
            title="Select 3D CAD Model", 
            filetypes=[("STEP Files", "*.stp *.step"), ("All Files", "*.*")]
        )
        if filepath:
            filename = os.path.basename(filepath)
            self.geo.load_file(filepath)
            self.screen_rotation = 0
            self.holes_detected = False 
            self.current_holes = []
            self.selected_hole_idx = None
            self._set_view_controls_locked(False) 
            
            self.nav_selector.set("Selection")
            self.on_nav_change("Selection")
            
            if self.geo.mesh is not None:
                extents = self.geo.get_physical_dimensions() 
                self.max_physical_dim = max(extents) 
                
                self.lbl_width.configure(text=f"Width (X): {extents[0]:.2f} mm", text_color="white")
                self.lbl_length.configure(text=f"Length (Y): {extents[1]:.2f} mm", text_color="white")
                self.lbl_thick.configure(text=f"Thickness (Z): {extents[2]:.2f} mm", text_color="white")
            self.show_view('Top')

    def update_plot(self, x, y, z_vert, face_data, triangles, title, holes=None):
        if self.current_tab != "Selection": return 
        
        self.ax.clear()
        if hasattr(self, 'cax'):
            self.cax.clear()
            self.cax.set_visible(True)
        self.ax.set_axis_on()
        
        self.current_x, self.current_y, self.current_z = x, y, z_vert
        self.current_triangles = triangles
        
        vmin, vmax = np.min(face_data), np.max(face_data)
        if vmin == vmax: vmax = vmin + 0.1 
            
        tpc = self.ax.tripcolor(x, y, triangles, facecolors=face_data, cmap=self.cmap, edgecolors='none', vmin=vmin, vmax=vmax)
        
        if holes:
            hole_x = [h.x for h in holes] 
            hole_y = [h.y for h in holes]
            
            self.current_holes_count = len(holes)
            initial_colors = ['white'] * self.current_holes_count
            
            if self.selected_hole_idx is not None and 0 <= self.selected_hole_idx < self.current_holes_count:
                initial_colors[self.selected_hole_idx] = 'yellow'
                
            self.scatter_holes = self.ax.scatter(hole_x, hole_y, facecolors=initial_colors, edgecolors="#3694ED", 
                                                 marker='o', s=150, linewidths=2, zorder=5, clip_on=True)
            
            for i, h in enumerate(holes):
                self.ax.text(h.x, h.y, f"{h.id}", color='black', fontsize=8, weight='bold', 
                             ha='center', va='center', zorder=6, clip_on=True)
        else:
            self.scatter_holes = None
            self.current_holes_count = 0

        lock_text = " [LOCKED]" if self.holes_detected else "" 
        rot_text = f" (Rotated {self.screen_rotation}°)" if self.screen_rotation > 0 else ""
        self.ax.set_title(title + rot_text + lock_text, fontsize=16, color="white")
        
        self.ax.grid(True, linestyle='--', alpha=0.3, color='#444444')
        self.ax.set_xlabel("X-Axis (mm)", fontsize=12, fontweight='bold', color="white")
        self.ax.set_ylabel("Y-Axis (mm)", fontsize=12, fontweight='bold', color="white")
        
        if self.max_physical_dim is not None and len(self.current_x) > 0:
            cx = (np.min(self.current_x) + np.max(self.current_x)) / 2.0
            cy = (np.min(self.current_y) + np.max(self.current_y)) / 2.0
            half_span = (self.max_physical_dim / 2.0) * 1.15  
            self.ax.set_xlim([cx - half_span, cx + half_span])
            self.ax.set_ylim([cy - half_span, cy + half_span])
            
        self.ax.set_aspect('equal')
        
        if hasattr(self, 'cax'):
            cbar = self.fig.colorbar(tpc, cax=self.cax)
            cbar.set_label("Depth / Z-Axis (mm)", fontsize=12, color="white")
            cbar.ax.yaxis.set_tick_params(color='white', labelcolor='white')
        
        self.hover_text = self.ax.annotate(
            "", xy=(0, 0), xytext=(15, 15), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.3", fc="red", ec="gray", alpha=1), visible=False
        )

        self.canvas.draw()
        
    def show_view(self, view_name):
        if self.geo.mesh is None: return
        self.current_view = view_name
        
        if view_name == 'Top':
            x, y, z_v, z_f, tri = self.geo.get_top_view(self.screen_rotation)
        elif view_name == 'Bottom':
            x, y, z_v, z_f, tri = self.geo.get_bottom_view(self.screen_rotation)
        elif view_name == 'Front':
            x, y, z_v, z_f, tri = self.geo.get_front_view(self.screen_rotation)
        elif view_name == 'Back':
            x, y, z_v, z_f, tri = self.geo.get_back_view(self.screen_rotation)
        elif view_name == 'Left':
            x, y, z_v, z_f, tri = self.geo.get_left_view(self.screen_rotation)
        elif view_name == 'Right':
            x, y, z_v, z_f, tri = self.geo.get_right_view(self.screen_rotation)

        if self.holes_detected:
            self.current_holes = self._detect_holes_in_view(x, y, z_v, view_name)
        else:
            self.current_holes = []
        
        title = f"{view_name} View"
        self.update_plot(x, y, z_v, z_f, tri, title, holes=self.current_holes)
        self.update_treeview(self.current_holes)

    def _setup_events(self):
        self.canvas.mpl_connect('scroll_event', self.on_scroll)
        self.canvas.mpl_connect('button_press_event', self.on_press)
        self.canvas.mpl_connect('button_release_event', self.on_release)
        self.canvas.mpl_connect('motion_notify_event', self.on_motion)

    def on_press(self, event):
        if event.inaxes != self.ax: return
        if self.current_tab == "Path Mapper": return # ข้ามการจัดการเมาส์ของ 2D ไปให้ 3D ทำงาน
        
        if event.button == 1:
            self.drag_state['is_dragging'] = True
            self.drag_state['x'], self.drag_state['y'] = event.x, event.y
            self.drag_state['xlim'], self.drag_state['ylim'] = self.ax.get_xlim(), self.ax.get_ylim()

    def on_release(self, event):
        if event.button == 1: self.drag_state['is_dragging'] = False

    def on_motion(self, event):
        if event.inaxes != self.ax: return
        if self.current_tab == "Path Mapper": return # ข้ามการจัดการเมาส์ของ 2D ไปให้ 3D ทำงาน
        
        if self.drag_state['is_dragging']: 
            dx_pixel, dy_pixel = event.x - self.drag_state['x'], event.y - self.drag_state['y']
            inv = self.ax.transData.inverted()
            p0 = inv.transform((0, 0))
            p1 = inv.transform((dx_pixel, dy_pixel))
            dx_data, dy_data = p1[0] - p0[0], p1[1] - p0[1]
            self.ax.set_xlim(self.drag_state['xlim'][0] - dx_data, self.drag_state['xlim'][1] - dx_data)
            self.ax.set_ylim(self.drag_state['ylim'][0] - dy_data, self.drag_state['ylim'][1] - dy_data)
            self.canvas.draw()
        else:
            if self.current_tab != "Selection": 
                self.hover_text.set_visible(False)
                return
                
            if not hasattr(self, 'current_x') or self.current_x is None: return
            dist = np.hypot(self.current_x - event.xdata, self.current_y - event.ydata)
            close_points = np.where(dist < 2.0)[0]
            
            if len(close_points) > 0:
                if self.current_view in ['Top', 'Front', 'Right']:
                    best_idx = close_points[np.argmin(self.current_z[close_points])]
                    surface_z = np.max(self.current_z)
                    depth = surface_z - self.current_z[best_idx]
                else:
                    best_idx = close_points[np.argmax(self.current_z[close_points])]
                    surface_z = np.min(self.current_z)
                    depth = self.current_z[best_idx] - surface_z
                
                self.hover_text.set_text(f"Depth: {depth:.2f} mm")
                self.hover_text.xy = (event.xdata, event.ydata)
                self.hover_text.set_visible(True)
            else:
                self.hover_text.set_visible(False)
            self.canvas.draw()

    def on_scroll(self, event):
        if event.inaxes != self.ax: return 
        if self.current_tab == "Path Mapper": return # ข้ามการจัดการซูมของ 2D ไปให้ 3D ทำงาน
        
        base_scale = 1.2 
        scale_factor = 1 / base_scale if event.button == 'up' else base_scale
        xdata, ydata = event.xdata, event.ydata
        xlim, ylim = self.ax.get_xlim(), self.ax.get_ylim()
        new_width = (xlim[1] - xlim[0]) * scale_factor
        new_height = (ylim[1] - ylim[0]) * scale_factor
        relx = (xlim[1] - xdata) / (xlim[1] - xlim[0])
        rely = (ylim[1] - ydata) / (ylim[1] - ylim[0])
        self.ax.set_xlim([xdata - new_width * (1 - relx), xdata + new_width * relx])
        self.ax.set_ylim([ydata - new_height * (1 - rely), ydata + new_height * rely])
        self.canvas.draw()
    
    def show(self):
        self.root.mainloop()