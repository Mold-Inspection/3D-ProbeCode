import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.colors import LinearSegmentedColormap
import customtkinter as ctk
from tkinter import ttk 
import numpy as np
import os

ctk.set_appearance_mode("Dark")  
ctk.set_default_color_theme("blue")  

class HoleFeature:
    def __init__(self, hid, x, y, surface_z, bottom_z, depth):
        self.id = hid
        self.x = x
        self.y = y
        self.surface_z = surface_z
        self.bottom_z = bottom_z
        self.depth = depth

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
        
        self.root = ctk.CTk()
        self.root.title("3D Laser Scanner Simulator")
        self.root.geometry("1400x800") 
        
        style = ttk.Style(self.root)
        style.theme_use("default")
        style.configure("Treeview", 
                        background="#2b2b2b",
                        foreground="white",
                        rowheight=30,
                        fieldbackground="#2b2b2b",
                        borderwidth=0,
                        font=('Arial', 10))
        style.map('Treeview', background=[('selected', '#1f538d')])
        style.configure("Treeview.Heading",
                        background="#1f1f1f",
                        foreground="white",
                        relief="flat")
        style.map("Treeview.Heading", background=[('active', '#333333')])

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

        self.tree_frame = ctk.CTkFrame(self.sidebar_right, fg_color="transparent")
        self.tree_frame.pack(fill="both", expand=True, padx=20, pady=20)

        columns = ("id", "type")
        self.tree = ttk.Treeview(self.tree_frame, columns=columns, show="tree", selectmode="browse")
        
        self.tree.column("#0", width=300, minwidth=200, stretch=ctk.YES) 
        self.tree.column("id", width=0, stretch=ctk.NO) 
        self.tree.column("type", width=0, stretch=ctk.NO)

        scrollbar = ttk.Scrollbar(self.tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.tree.bind("<Button-1>", self.on_tree_click)

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
                
                if is_positive_view:
                    surf_z = surface_z
                    bot_z = float(np.min(cluster_z))
                    max_depth = float(surf_z - bot_z)
                else:
                    surf_z = surface_z
                    bot_z = float(np.max(cluster_z))
                    max_depth = float(bot_z - surf_z)
                
                hid = len(holes) + 1
                holes.append(HoleFeature(hid, center_x, center_y, surf_z, bot_z, max_depth))
        
        holes.sort(key=lambda h: (-round(h.y / 5.0), h.x))
        for i, h in enumerate(holes):
            h.id = i + 1
            
        return holes

    def update_treeview(self, holes):
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        if not holes and self.holes_detected:
            self.tree.insert("", "end", text="   -- No holes detected --")
            return
        elif not self.holes_detected:
            self.tree.insert("", "end", text="   -- Press Generate Holes --")
            return
            
        for i, hole in enumerate(holes):
            node_text = f" 🎯 Hole {hole.id} [X: {hole.x:.2f}, Y: {hole.y:.2f}] Depth: {hole.depth:.2f} mm"
            self.tree.insert("", "end", text=node_text, values=(f"H{i}", "Parent"), open=True)

    def on_tree_select(self, event):
        selected_items = self.tree.selection()
        if not self.scatter_holes and self.current_tab == "Selection": return

        colors = ['white'] * self.current_holes_count
        self.selected_hole_idx = None
        
        if selected_items:
            item = selected_items[0]
            values = self.tree.item(item, "values")
            if values and str(values[0]).startswith("H"):
                try:
                    idx = int(values[0][1:])
                    if 0 <= idx < self.current_holes_count:
                        colors[idx] = 'yellow' 
                        self.selected_hole_idx = idx
                except ValueError: pass

        if self.current_tab == "Selection" and self.scatter_holes:
            self.scatter_holes.set_facecolors(colors)
            self.canvas.draw_idle()
        elif self.current_tab == "Customization":
            self.draw_cross_section()
    
    def on_tree_click(self, event):
        item = self.tree.identify_row(event.y)
        if item and item in self.tree.selection():
            self.tree.selection_remove(item)
            self.on_tree_select(None)
            return "break"

    def draw_cross_section(self):
        self.ax.clear()
        self.cax.clear()
        self.cax.set_visible(False) 
        
        if self.selected_hole_idx is None or not self.current_holes:
            self.ax.set_title("Please select a hole from the right panel to analyze.", color="white", fontsize=16)
            self.ax.set_axis_off()
            self.canvas.draw()
            return
            
        self.ax.set_axis_on()
        hole = self.current_holes[self.selected_hole_idx]
        
        # [MODIFIED] กลับมาดึงข้อมูลเฉพาะบริเวณรอบๆ รู เพื่อให้ซูมเข้าใกล้ๆ
        tolerance_y = 1.5
        tolerance_x = max(hole.depth * 2.0, 20.0) 
        
        mask = (np.abs(self.current_y - hole.y) < tolerance_y) & (np.abs(self.current_x - hole.x) < tolerance_x)
        profile_x = self.current_x[mask]
        profile_z = self.current_z[mask]
        
        sorted_indices = np.argsort(profile_x)
        profile_x = profile_x[sorted_indices]
        profile_z = profile_z[sorted_indices]
        
        nominal_surface_z = hole.surface_z
        depth_for_ref = hole.depth if hole.depth > 1.0 else 5.0 
        taper_reference_plane_z = nominal_surface_z - depth_for_ref / 2.0 
        bottom_z = hole.bottom_z
        
        z_wall_mask = (profile_z < (nominal_surface_z - 1.0)) & (profile_z > (bottom_z + 1.0))
        wall_x = profile_x[z_wall_mask]
        wall_z = profile_z[z_wall_mask]
        
        left_wall_mask = wall_x < hole.x
        right_wall_mask = wall_x > hole.x
        left_wall_x, left_wall_z = wall_x[left_wall_mask], wall_z[left_wall_mask]
        right_wall_x, right_wall_z = wall_x[right_wall_mask], wall_z[right_wall_mask]
        
        taper_angle_left, taper_angle_right = 0.0, 0.0
        line_left_x, line_right_x = [], []
        
        if len(left_wall_x) > 5:
            m_l, c_l = np.polyfit(left_wall_z, left_wall_x, 1)
            alpha_l_rad = np.arctan(m_l)
            taper_angle_left = np.abs(np.degrees(alpha_l_rad))
            z_fit = np.array([bottom_z, nominal_surface_z])
            line_left_x = m_l * z_fit + c_l
            
        if len(right_wall_x) > 5:
            m_r, c_r = np.polyfit(right_wall_z, right_wall_x, 1)
            alpha_r_rad = np.arctan(m_r)
            taper_angle_right = np.abs(np.degrees(alpha_r_rad))
            z_fit = np.array([bottom_z, nominal_surface_z])
            line_right_x = m_r * z_fit + c_r
            
        total_taper_angle = taper_angle_left + taper_angle_right
        
        if len(line_left_x) > 0 and len(line_right_x) > 0:
            left_gauge_x = m_l * taper_reference_plane_z + c_l
            right_gauge_x = m_r * taper_reference_plane_z + c_r
            gauge_distance = np.abs(right_gauge_x - left_gauge_x)
        else:
            gauge_distance = 0.0
            left_gauge_x, right_gauge_x = hole.x, hole.x 

        # วาดเส้นโปรไฟล์และจุดสัมผัส
        if len(profile_x) > 0:
            self.ax.plot(profile_x, profile_z, color='#00e5ff', linewidth=2.5, marker='o', markersize=3, label="Measured Surface Profile")
        
        self.ax.axhline(y=nominal_surface_z, color='gray', linestyle='--', label='Nominal Reference Surface')
        self.ax.axhline(y=taper_reference_plane_z, color='orange', linestyle=':', label='Taper Reference Plane (Gauge)')
        
        z_fit_draw = np.array([bottom_z, nominal_surface_z])
        if len(line_left_x) > 0:
            self.ax.plot(m_l * z_fit_draw + c_l, z_fit_draw, color='red', linestyle='-', linewidth=2, label=f'Left Taper Line ({taper_angle_left:.1f}°)')
        if len(line_right_x) > 0:
            self.ax.plot(m_r * z_fit_draw + c_r, z_fit_draw, color='red', linestyle='-', linewidth=2, label=f'Right Taper Line ({taper_angle_right:.1f}°)')
            
        if len(line_left_x) > 0 and len(line_right_x) > 0:
            self.ax.scatter([left_gauge_x, right_gauge_x], [taper_reference_plane_z, taper_reference_plane_z], color='yellow', marker='o', s=100, zorder=10, label='Gauge Points')
        
        self.ax.axvline(x=hole.x, color='white', linestyle='-.', alpha=0.5)

        # การแสดงผลข้อความ
        label_x = hole.x - (tolerance_x * 0.8)
        if len(profile_x) > 0:
            self.ax.annotate('', xy=(label_x + 5, nominal_surface_z), xytext=(label_x, nominal_surface_z), arrowprops=dict(arrowstyle='<->', color='white', linewidth=1))
            self.ax.text(label_x - 1, nominal_surface_z, 'Reference Surface', color='white', fontsize=10, ha='right', va='center')
            
            self.ax.annotate('', xy=(label_x + 5, taper_reference_plane_z), xytext=(label_x, taper_reference_plane_z), arrowprops=dict(arrowstyle='<->', color='orange', linewidth=1))
            self.ax.text(label_x - 1, taper_reference_plane_z, 'Reference Plane', color='orange', fontsize=10, ha='right', va='center')
            
            self.ax.annotate('', xy=(label_x + 5, bottom_z), xytext=(label_x, bottom_z), arrowprops=dict(arrowstyle='<->', color='gray', linewidth=1))
            self.ax.text(label_x - 1, bottom_z, 'Hole Bottom', color='gray', fontsize=10, ha='right', va='center')

        if total_taper_angle > 0:
            text_pos_x, text_pos_z = hole.x, bottom_z + 3.0
            self.ax.text(text_pos_x, text_pos_z, f'Total Taper Angle\n2α = {total_taper_angle:.1f}°', color='red', fontsize=12, fontweight='bold', ha='center', va='center', bbox=dict(facecolor='#1e1e1e', alpha=0.8, edgecolor='red', boxstyle='round'))
        
        if gauge_distance > 0:
            self.ax.annotate('', xy=(left_gauge_x, taper_reference_plane_z - 1.0), xytext=(right_gauge_x, taper_reference_plane_z - 1.0), arrowprops=dict(arrowstyle='<->', color='yellow', linewidth=1.5))
            text_pos_x, text_pos_z = hole.x, taper_reference_plane_z - 2.5
            self.ax.text(text_pos_x, text_pos_z, f'Gauge Distance\n= {gauge_distance:.2f} mm', color='yellow', fontsize=11, fontweight='bold', ha='center', va='center')
            
        if len(left_wall_x) > 0 and len(left_wall_z) > 0:
            self.ax.text(min(left_wall_x) - 1, left_wall_z[0], 'Tapered Hole', color='red', fontsize=12, rotation=90, va='center')
        
        if len(profile_x) > 0:
            self.ax.text(hole.x + (tolerance_x * 0.5), nominal_surface_z + 2, 'Nominal Section', color='white', fontsize=12, ha='left')

        self.ax.set_title(f"Detailed Analysis: Cross-Section of Hole {hole.id}", color='white', fontsize=16)
        self.ax.set_xlabel("X-Axis (mm)", color='white', fontsize=13)
        self.ax.set_ylabel("Z-Axis / Depth (mm)", color='white', fontsize=13)
        self.ax.tick_params(colors='white')
        
        # [MODIFIED] ตั้งค่าขอบเขต (Limits) ให้ซูมรอบๆ รู
        if len(profile_x) > 0:
            cx = hole.x
            half_span = tolerance_x
            self.ax.set_xlim([cx - half_span, cx + half_span])
            
        z_margin = max(depth_for_ref / 2.0, 3.0) 
        self.ax.set_ylim([bottom_z - z_margin, nominal_surface_z + z_margin])
        
        # [NEW] สั่งล็อคอัตราส่วน 1:1 ให้ภาพสมจริง ไม่ถูกบีบอัด
        self.ax.set_aspect('equal')
        
        self.ax.grid(True, linestyle=':', alpha=0.5, color='gray')
        self.ax.legend(facecolor='#1e1e1e', edgecolor='gray', labelcolor='white', loc='upper right')
        
        self.canvas.draw()

    def on_nav_change(self, selected_tab):
        self.current_tab = selected_tab
        
        if selected_tab == "Selection":
            self.sidebar_right.pack(side="right", fill="y", before=self.center_frame)
            self.cax.set_visible(True)
            self.show_view(self.current_view)
            
        elif selected_tab == "Customization":
            self.sidebar_right.pack(side="right", fill="y", before=self.center_frame)
            self.draw_cross_section()
            
        else:
            self.sidebar_right.pack_forget()
            self.ax.clear()
            self.cax.clear()
            self.cax.set_visible(False)
            self.ax.set_title("Path Mapper & G-Code - Coming Soon", color="white", fontsize=16)
            self.ax.set_axis_off()
            self.canvas.draw()
            
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
        
        if self.current_tab == "Customization":
            self.nav_selector.set("Selection")
            self.on_nav_change("Selection")
        else:
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
        if self.current_tab != "Selection": return
        
        if event.button == 1:
            self.drag_state['is_dragging'] = True
            self.drag_state['x'], self.drag_state['y'] = event.x, event.y
            self.drag_state['xlim'], self.drag_state['ylim'] = self.ax.get_xlim(), self.ax.get_ylim()

    def on_release(self, event):
        if event.button == 1: self.drag_state['is_dragging'] = False

    def on_motion(self, event):
        if event.inaxes != self.ax: return
        
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
        if self.current_tab != "Selection": return
        
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