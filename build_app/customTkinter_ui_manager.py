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
        colors = ["white", "yellow", "orange", "red"]
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

        # geometry_engine.get_2d_projection คำนวณ z_depth = surface_z - z_raw
        # โดย surface_z = np.max(z_raw) เสมอ (camera side อยู่ที่ z มากที่สุด)
        # ดังนั้น z_depth=0 = ผิวที่กำลังมอง, z_depth ยิ่งมาก = ยิ่งลึก
        # → ใช้ logic เดียวกันทุก view: surface = min(z_depth), bottom = max(z_depth)

        if view_name in ['Front', 'Right']:
            # views เหล่านี้ยังคง convention เดิม (ทดสอบแล้วถูก)
            surface_z = np.max(z)
            bottom_z  = np.min(z)
            valid_indices = np.where((z < surface_z - 1.0) & (z > bottom_z + 1.0))[0]
            is_positive_view = True
        else:
            # Top, Bottom, Back, Left — ทุก view ใช้ z_depth จาก geometry_engine
            # z_depth น้อย = ผิวด้านกล้อง, z_depth มาก = ลึกลงไป
            surface_z = np.min(z)
            bottom_z  = np.max(z)
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
                
                # NEAR_CENTER_RATIO: สัดส่วนของ radius ที่ใช้กรอง cluster_z
                # ให้เหลือเฉพาะ vertex ใกล้ center_x/center_y เพื่อหา bot_z
                # ถ้าจะเปลี่ยนสัดส่วน แก้ค่านี้ที่เดียว (ใช้ร่วมกับ Customization)
                NEAR_CENTER_RATIO = 0.3
                near_center_mask = distances < (radius * NEAR_CENTER_RATIO)
                if near_center_mask.sum() < 1:
                    near_center_mask = np.ones(len(cluster_z), dtype=bool)  # fallback: ใช้ cluster_z ทั้งหมด

                if is_positive_view:
                    surf_z = surface_z
                    bot_z = float(np.min(cluster_z[near_center_mask]))
                    max_depth = float(surf_z - bot_z)
                    # Z สูงสุดของ cluster = ขอบปากรูจริง (อาจต่ำกว่า surface_z ของชิ้นงาน)
                    hole_top_z = float(np.max(cluster_z))
                else:
                    surf_z = surface_z
                    bot_z = float(np.max(cluster_z[near_center_mask]))
                    max_depth = float(bot_z - surf_z)
                    hole_top_z = float(np.min(cluster_z))
                
                hid = len(holes) + 1
                hf = HoleFeature(hid, center_x, center_y, surf_z, bot_z, max_depth, radius)
                hf.hole_top_z = hole_top_z   # ขอบปากรูจริงของ cluster นี้
                holes.append(hf)
        
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

            btn_text = f"🎯 Hole {hole.id} [X: {hole.x:.2f}, Y: {hole.y:.2f}] D: {hole.depth:.2f}"
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
        self.fig.clf()
        self.cax = None  # ไม่ใช้ colorbar ใน Customization

        # ── guard: ต้องมีข้อมูล mesh และรูที่เลือก ────────────────────────────
        has_mesh = self.geo.mesh is not None
        has_hole = self.selected_hole_idx is not None and len(self.current_holes) > 0

        if not has_mesh:
            self.ax = self.fig.add_subplot(111, facecolor='#1e1e1e')
            self.ax.set_title("Please upload a model and generate holes first.",
                              color="white", fontsize=15)
            self.ax.set_axis_off()
            self.canvas.draw()
            return

        # ── สร้าง 3D subplot เต็มหน้าจอ ──────────────────────────────────────
        self.fig.subplots_adjust(left=0.0, right=1.0, top=1.0, bottom=0.0)
        ax3d = self.fig.add_subplot(111, projection='3d', facecolor='#1e1e1e')
        self.ax = ax3d

        # ── หมุน mesh ให้ตรงกับ view ที่เลือกใน Selection ───────────────────────
        # ใช้ rotation matrix เดียวกับ geometry_engine.get_XXX_view()
        # ทำให้ z3 น้อย = ผิวที่กำลังมองอยู่เสมอ ไม่ว่าจะเลือก view ไหน
        _view_rotations = {
            'Top':    (180,  0,   0),   # [SWAPPED] แก้ให้ตรงกับ Selection
            'Bottom': (0,    0,   0),   # [SWAPPED]
            'Front':  (-90,  0,   0),
            'Back':   (90,   0, 180),
            'Left':   (-90,  0,  90),
            'Right':  (-90,  0, -90),
        }
        rx_deg, ry_deg, rz_deg = _view_rotations.get(self.current_view, (0, 0, 0))
        import trimesh as _trimesh
        from trimesh.transformations import euler_matrix as _euler
        _matrix = _euler(np.radians(rx_deg), np.radians(ry_deg), np.radians(rz_deg))
        _rotated = _trimesh.transformations.transform_points(
            self.geo.mesh.vertices, _matrix)

        faces = self.geo.mesh.faces

        x3   = _rotated[:, 0]
        y3   = _rotated[:, 1]
        z3   = _rotated[:, 2]
        tris = faces

        # center XY เหมือนกับที่ get_2d_projection ทำ (ใช้ centroid XY)
        x3 = x3 - (float(np.min(x3)) + float(np.max(x3))) / 2.0
        y3 = y3 - (float(np.min(y3)) + float(np.max(y3))) / 2.0

        n_tri   = len(tris)
        MAX_TRIS = 16000                          # [MODIFIED] เพิ่มจาก 4000 → 16000
        step    = max(1, n_tri // MAX_TRIS)
        sampled = tris[::step]

        # ── global Z offset: ผิวบนสุด = Z 0 ────────────────────────────────────
        SURF_Z_GLOBAL = float(np.min(z3))   # Z raw ของผิวบนสุดชิ้นงาน

        # รวม edge segments ทั้งหมดแล้ว plot ครั้งเดียว
        tx = x3[sampled]   # shape (N,3)
        ty = y3[sampled]
        tz = z3[sampled] - SURF_Z_GLOBAL    # offset Z
        nan_col = np.full((len(sampled), 1), np.nan)
        seg_x = np.hstack([tx[:, [0,1,2,0]], nan_col]).ravel()
        seg_y = np.hstack([ty[:, [0,1,2,0]], nan_col]).ravel()
        seg_z = np.hstack([tz[:, [0,1,2,0]], nan_col]).ravel()

        ax3d.plot(seg_x, seg_y, seg_z,
                  color="#1f538d", linewidth=0.8, alpha=0.6)

        # ── [NEW] pre-compute triangle sets ต่อรู สำหรับใช้ highlight ──────────
        tri_cx = x3[tris].mean(axis=1)
        tri_cy = y3[tris].mean(axis=1)
        tri_cz = z3[tris].mean(axis=1)   # ยังเป็น raw Z (ใช้เปรียบเทียบกับ hole coords)

        # ── bounding box (ใช้ Z offset แล้ว) ────────────────────────────────────
        xmin, xmax = float(np.min(x3)), float(np.max(x3))
        ymin, ymax = float(np.min(y3)), float(np.max(y3))
        zmin_d = 0.0                                    # ผิวบน = 0
        zmax_d = float(np.max(z3)) - SURF_Z_GLOBAL     # ก้นลึกสุด
        cx = (xmin + xmax) / 2.0
        cy = (ymin + ymax) / 2.0
        cz = (zmin_d + zmax_d) / 2.0
        half = max(xmax - xmin, ymax - ymin, zmax_d - zmin_d) / 2.0 * 1.1

        # ══════════════════════════════════════════════════════════════════════
        # 2. วาด ID label + highlight mesh จริงของทุกรู (ไม่มีวงแหวนสังเคราะห์)
        # ══════════════════════════════════════════════════════════════════════
        for i, h in enumerate(self.current_holes):
            r_z    = getattr(h, 'hole_top_z', h.surface_z)
            is_sel = (i == self.selected_hole_idx)

            # ID label — offset Z
            ax3d.text(h.x, h.y, (r_z - SURF_Z_GLOBAL) + half * 0.02,
                      str(h.id), color='white', fontsize=7,
                      ha='center', va='bottom')

            # หา triangles ของรูนี้จาก mesh จริง (ใช้ raw Z เปรียบเทียบ)
            dist_h   = np.hypot(tri_cx - h.x, tri_cy - h.y)
            surf_z_g = SURF_Z_GLOBAL
            z_lo_h   = min(h.bottom_z, r_z)
            z_hi_h   = max(h.bottom_z, r_z) + 0.5

            mask_wall = (
                (dist_h <= h.radius * 1.2) &
                (tri_cz >= z_lo_h - 0.3) &
                (tri_cz <= z_hi_h)
            )
            mask_rim = (
                (dist_h <= h.radius * 1.3) &
                (tri_cz >= surf_z_g - 0.5) &
                (tri_cz <  z_lo_h + 0.3)
            )
            hmask = mask_wall | mask_rim
            htris = tris[hmask]

            if len(htris) > 0:
                htx = x3[htris]; hty = y3[htris]
                htz = z3[htris] - SURF_Z_GLOBAL    # offset Z
                nan_h = np.full((len(htris), 1), np.nan)
                hxs = np.hstack([htx[:,[0,1,2,0]], nan_h]).ravel()
                hys = np.hstack([hty[:,[0,1,2,0]], nan_h]).ravel()
                hzs = np.hstack([htz[:,[0,1,2,0]], nan_h]).ravel()
                if is_sel:
                    ax3d.plot(hxs, hys, hzs, color="white", linewidth=1.6, alpha=0.95,
                              label='Selected Hole Mesh')
                else:
                    ax3d.plot(hxs, hys, hzs, color='#1f538d', linewidth=0.9, alpha=0.5)

        # ══════════════════════════════════════════════════════════════════════
        # 3. Probing path เฉพาะรูที่เลือก — อิง mesh จริงทั้งหมด
        # ══════════════════════════════════════════════════════════════════════
        if has_hole:
            hole   = self.current_holes[self.selected_hole_idx]
            layers = hole.layers
            points = hole.points_per_layer

            rim_z  = getattr(hole, 'hole_top_z', hole.surface_z)   # display Z (ตื้น)
            bot_z  = hole.bottom_z                                   # display Z (ลึก)

            # ── แปลง display Z กลับเป็น raw mesh Z ───────────────────────────
            # display Z = raw_z - SURF_Z_GLOBAL  →  raw_z = display_z + SURF_Z_GLOBAL
            # rim_z display น้อย = raw_z น้อย = ตื้น (Z น้อย = ผิวบนใน mesh)
            # bot_z display มาก = raw_z มาก = ลึก
            raw_rim_z = rim_z + SURF_Z_GLOBAL   # raw Z ของปากรู
            raw_bot_z = bot_z + SURF_Z_GLOBAL   # raw Z ของก้นรู

            # vertices ของรูนี้ — กรองใน raw mesh space
            dist_v = np.hypot(x3 - hole.x, y3 - hole.y)
            z_lo_v = min(raw_rim_z, raw_bot_z) - 2.0
            z_hi_v = max(raw_rim_z, raw_bot_z) + 2.0
            vmask  = (dist_v <= hole.radius * 1.6) & (z3 >= z_lo_v) & (z3 <= z_hi_v)
            vx = x3[vmask]; vy = y3[vmask]; vz = z3[vmask]

            has_step_hole = (hasattr(hole, '_step_hole') and hole._step_hole is not None
                             and hasattr(self.geo, 'step_data') and self.geo.step_data is not None)

            EDGE_HALF = 0.5

            def dz(z_raw):
                return z_raw - SURF_Z_GLOBAL

            if has_step_hole:
                sh = hole._step_hole
                z_start = sh.depth_top     # display depth ของปากรู
                star_z  = sh.depth_bot     # display depth ของก้นรู
                star_x  = hole.x
                star_y  = hole.y
                z_end   = star_z

                step_layers = self.geo.get_probe_path_layers(sh, layers, self.current_view)

                px_list, py_list, pz_list = [hole.x], [hole.y], [z_start]
                tx_list, ty_list, tz_list = [], [], []

                for lyr in step_layers:
                    z_disp = lyr['z_display']
                    r_at_z = lyr['radius'] * 0.92
                    # [FIX] center XY เปลี่ยนตาม layer (รูเอียง/taper)
                    cx_lyr = lyr['x_display']
                    cy_lyr = lyr['y_display']
                    px_list.append(cx_lyr); py_list.append(cy_lyr); pz_list.append(z_disp)
                    for ang in np.linspace(0, 2*np.pi, points, endpoint=False):
                        ppx = cx_lyr + r_at_z * np.cos(ang)
                        ppy = cy_lyr + r_at_z * np.sin(ang)
                        tx_list.append(ppx); ty_list.append(ppy); tz_list.append(z_disp)
                        px_list += [ppx, cx_lyr]
                        py_list += [ppy, cy_lyr]
                        pz_list += [z_disp, z_disp]

                is_blind = True

            else:
                # ── Mesh-based (fallback สำหรับ STL) ────────────────────────────
                rim_z    = getattr(hole, 'hole_top_z', hole.surface_z)
                bot_z    = hole.bottom_z
                raw_rim_z = rim_z + SURF_Z_GLOBAL
                raw_bot_z = bot_z + SURF_Z_GLOBAL

                dist_v = np.hypot(x3 - hole.x, y3 - hole.y)
                z_lo_v = min(raw_rim_z, raw_bot_z) - 2.0
                z_hi_v = max(raw_rim_z, raw_bot_z) + 2.0
                vmask  = (dist_v <= hole.radius * 1.6) & (z3 >= z_lo_v) & (z3 <= z_hi_v)
                vx = x3[vmask]; vy = y3[vmask]; vz = z3[vmask]

                depth_span = abs(rim_z - bot_z)
                vz_disp = vz - SURF_Z_GLOBAL

                if len(vz_disp) >= 6:
                    n_bins    = max(20, layers * 4)
                    z_bins    = np.linspace(float(np.min(vz_disp)), float(np.max(vz_disp)), n_bins + 1)
                    z_profile = []
                    r_profile = []
                    for bi in range(n_bins):
                        b_mask = (vz_disp >= z_bins[bi]) & (vz_disp < z_bins[bi+1])
                        if b_mask.sum() >= 2:
                            r_vals = np.hypot(vx[b_mask]-hole.x, vy[b_mask]-hole.y)
                            z_profile.append(float((z_bins[bi] + z_bins[bi+1]) / 2))
                            r_profile.append(float(np.percentile(r_vals, 72)))
                    z_profile = np.array(z_profile)
                    r_profile = np.array(r_profile)

                    def mesh_radius_at_z(target_z_disp):
                        if len(z_profile) < 2:
                            return hole.radius
                        return float(np.interp(target_z_disp, z_profile, r_profile,
                                               left=r_profile[0], right=r_profile[-1]))
                else:
                    def mesh_radius_at_z(target_z_disp):
                        return hole.radius

                NEAR_CENTER_RATIO = 0.3
                if len(vz) == 0:
                    TRUE_TOP_Z = raw_rim_z
                    TRUE_BOT_Z = raw_bot_z
                else:
                    TRUE_TOP_Z = float(np.min(vz))
                    dist_vmask = dist_v[vmask]
                    near_center_vmask = dist_vmask < (hole.radius * NEAR_CENTER_RATIO)
                    if near_center_vmask.sum() < 1:
                        near_center_vmask = np.ones(len(vz), dtype=bool)
                    TRUE_BOT_Z = float(np.max(vz[near_center_vmask]))

                z_start = dz(TRUE_TOP_Z)
                star_z  = min(z_start + hole.depth, dz(TRUE_BOT_Z))
                star_x  = hole.x
                star_y  = hole.y
                z_end   = star_z
                z_levels_path = np.linspace(z_start, z_end, layers)

                px_list, py_list, pz_list = [hole.x], [hole.y], [z_start]
                tx_list, ty_list, tz_list = [], [], []

                for z_disp in z_levels_path:
                    r_at_z = mesh_radius_at_z(z_disp) * 0.92
                    px_list.append(hole.x); py_list.append(hole.y); pz_list.append(z_disp)
                    for ang in np.linspace(0, 2*np.pi, points, endpoint=False):
                        ppx = hole.x + r_at_z * np.cos(ang)
                        ppy = hole.y + r_at_z * np.sin(ang)
                        tx_list.append(ppx); ty_list.append(ppy); tz_list.append(z_disp)
                        px_list += [ppx, hole.x]
                        py_list += [ppy, hole.y]
                        pz_list += [z_disp, z_disp]

                raw_global_bot    = float(np.max(z3))
                through_threshold = max((raw_global_bot - SURF_Z_GLOBAL) * 0.001, 0.1)
                is_blind = (raw_global_bot - TRUE_BOT_Z) > through_threshold

            px_list.append(star_x); py_list.append(star_y); pz_list.append(star_z)
            tx_list.append(star_x); ty_list.append(star_y); tz_list.append(star_z)
            px_list.append(hole.x); py_list.append(hole.y); pz_list.append(z_start)

            ax3d.plot(px_list, py_list, pz_list,
                      color='yellow', linestyle='--', linewidth=1.2,
                      label='Tool Path', alpha=0.85)

            wall_n = len(tx_list) - 1
            ax3d.scatter(tx_list[:wall_n], ty_list[:wall_n], tz_list[:wall_n],
                         color='red', s=22, depthshade=False,
                         label=f'Wall Contact ({layers}L×{points}P)')
            ax3d.scatter([tx_list[-1]], [ty_list[-1]], [tz_list[-1]],
                         color='#ffea00', s=90, marker='*',
                         depthshade=False, label='Bottom Depth Point', zorder=10)

            # แสดง Position ของ Star — [NEW] text สีแดงถ้ามาจาก STEP
            text_color = '#ff3333' if has_step_hole else '#ffea00'
            source_tag = ' [STEP]' if has_step_hole else ' [Mesh]'
            ax3d.text(star_x, star_y, star_z,
                      f" ★{source_tag} X={star_x:.2f}, Y={star_y:.2f}\n"
                      f"   Depth={hole.depth:.2f} mm",
                      color=text_color, fontsize=7, zorder=11)

            title_str = (f"Customization — Hole {hole.id}  |  "
                         f"R={hole.radius:.1f} mm  Depth={hole.depth:.2f} mm  |  "
                         f"{layers}L × {points}P = {layers*points} pts"
                         + (' [STEP]' if has_step_hole else ' [Mesh]'))

            ax3d.view_init(elev=-135, azim=30)

        else:
            title_str = "Customization — Select a hole to show probing path"
            ax3d.view_init(elev=-135, azim=30)   # มุมกล้องเดียวกับตอนเลือกรู

        # ══════════════════════════════════════════════════════════════════════
        # 4. ตั้งค่า axis + ตกแต่ง
        # ══════════════════════════════════════════════════════════════════════
        ax3d.set_xlim([cx - half, cx + half])
        ax3d.set_ylim([cy - half, cy + half])
        ax3d.set_zlim([cz - half, cz + half])

        ax3d.set_title(title_str, color='white', fontsize=11, pad=10)
        for spine in [ax3d.xaxis, ax3d.yaxis, ax3d.zaxis]:
            spine.set_pane_color((0.10, 0.10, 0.10, 1.0))
            spine.line.set_color('gray')
        ax3d.tick_params(colors='white', labelsize=7)
        ax3d.set_xlabel("X (mm)", color='white', fontsize=9, labelpad=2)
        ax3d.set_ylabel("Y (mm)", color='white', fontsize=9, labelpad=2)
        ax3d.set_zlabel("Z (mm)", color='white', fontsize=9, labelpad=2)
        if has_hole:
            ax3d.legend(facecolor='#1e1e1e', edgecolor='gray',
                        labelcolor='white', loc='upper right', fontsize=7)

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
            has_step = (hasattr(self.geo, 'step_data') and self.geo.step_data is not None)

            if has_step:
                step_holes = self.geo.get_step_holes_in_view(view_name)
                converted = []
                for i, sh in enumerate(step_holes):
                    hf = HoleFeature(
                        hid       = i + 1,
                        x         = sh.display_x,
                        y         = sh.display_y,
                        surface_z = sh.depth_top,
                        bottom_z  = sh.depth_bot,
                        depth     = sh.depth,
                        radius    = sh.radius,
                    )
                    hf.hole_top_z = sh.depth_top
                    hf._step_hole = sh
                    converted.append(hf)
                self.current_holes = converted
            else:
                visible_vert_idx = np.unique(tri.ravel())
                self.current_holes = self._detect_holes_in_view(
                    x[visible_vert_idx], y[visible_vert_idx],
                    z_v[visible_vert_idx], view_name)

            if len(self.current_holes) == 0:
                import tkinter.messagebox as _mb
                _mb.showinfo(
                    "ไม่พบรู",
                    f"ไม่พบรูหรือโพรงที่มองเห็นได้ในมุมมอง {view_name}\n"
                    "อาจเป็นเพราะรูอยู่ด้านตรงข้าม หรือโพรงไม่เปิดโล่งในด้านนี้\n\n"
                    "ลองเปลี่ยนมุมมองเป็นด้านที่รูเปิดโล่งแทน"
                )
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
                if self.current_view in ['Front', 'Right']:
                    best_idx = close_points[np.argmin(self.current_z[close_points])]
                    surface_z = np.max(self.current_z)
                    depth = surface_z - self.current_z[best_idx]
                else:
                    # Top, Bottom, Back, Left — z_depth จาก geometry_engine (น้อย = ผิว)
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