# ui/main_window.py
import customtkinter as ctk
import os
import numpy as np
import tkinter.messagebox as _mb
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.colors import LinearSegmentedColormap
import matplotlib.pyplot as plt
from core.models import HoleFeature
from ui.tabs.selection_tab import SelectionTab
from ui.tabs.customization_tab import CustomizationTab
from ui.tabs.path_mapper_tab import PathMapperTab

class UIManager:
    def __init__(self, geometry_engine):
        self.geo = geometry_engine
        
        # --- ตัวแปรสถานะ ---
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
        
        # --- โหลดคลาสสำหรับแต่ละ Tab ---
        self.selection_tab = SelectionTab(self)
        self.customization_tab = CustomizationTab(self)
        self.path_mapper_tab = PathMapperTab(self)
        
        # --- สร้างหน้าต่างหลัก ---
        self.root = ctk.CTk()
        self.root.title("3D Laser Scanner Simulator")
        self.root.geometry("1400x800") 
        
        # --- Layout ซ้าย / ขวา / กลาง ---
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

        # --- Setup Matplotlib Canvas 2D (ตั้งค่าแค่ครั้งเดียว) ---
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

        # 📌 สร้างกล่องข้อความความลึก (Hover Text)
        self.hover_text = self.ax.annotate(
            "", xy=(0, 0), xytext=(15, 15),
            textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.3", fc="red", ec="gray", alpha=1),
            visible=False
        )

        # --- เรียก Setup ส่วนประกอบต่างๆ ลงหน้าจอ ---
        self._setup_left_sidebar()
        self._setup_right_sidebar()
        self.selection_tab.setup_events() 
        
        if self.geo.mesh is not None:
            self.show_view('Top')

    # ---------------------------------------------------------
    # UI Sidebar Setup
    # ---------------------------------------------------------
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

        self.holes_list_frame = ctk.CTkScrollableFrame(self.sidebar_right, fg_color="transparent")
        self.holes_list_frame.pack(fill="both", expand=True, padx=10, pady=5)

    def _set_view_controls_locked(self, is_locked):
        """
        is_locked=True  → holes ถูก generate แล้ว:
            - Rotate / View buttons → disabled (ป้องกันเปลี่ยนมุมมอง)
            - Reset Position        → ENABLED  (ยังใช้ได้ใน Selection)
            - Generate Holes        → disabled
            - Clear & Unlock        → enabled
        is_locked=False → ยังไม่ generate หรือ clear แล้ว:
            - ทุกปุ่มกลับสู่สถานะปกติ
        """
        rotate_state = "disabled" if is_locked else "normal"
        self.btn_rotate.configure(state=rotate_state)
        for btn in self.view_buttons.values():
            btn.configure(state=rotate_state)

        # Reset Position: ใช้ได้เสมอใน Selection (ทั้ง locked และ unlocked)
        # จะถูก disable เฉพาะตอนอยู่ใน Customization tab (จัดการใน on_nav_change)
        self.btn_reset.configure(state="normal")

        self.btn_detect.configure(state="disabled" if is_locked else "normal")
        self.btn_clear.configure(state="normal" if is_locked else "disabled")

    # ---------------------------------------------------------
    # Core Functions
    # ---------------------------------------------------------
    def on_nav_change(self, selected_tab):
        # เปลี่ยนหน้า (Selection / Customization / Path Mapper) → ล้าง pin ทั้งหมด
        self.selection_tab.clear_pins()

        self.current_tab = selected_tab
        self.sidebar_right.pack(side="right", fill="y", before=self.center_frame)

        # Reset Position: ใช้ได้เฉพาะใน Selection tab เท่านั้น
        if selected_tab == "Customization":
            self.btn_reset.configure(state="disabled")
        else:
            # Selection หรือ Path Mapper — enable ถ้ามี mesh
            self.btn_reset.configure(state="normal" if self.geo.mesh is not None else "disabled")
        
        if selected_tab == "Selection":
            self.fig.clf()
            self.ax = self.fig.add_subplot(111, facecolor='#1e1e1e')
            self.fig.subplots_adjust(bottom=0.1, right=0.85, left=0.1, top=0.9)
            self.cax = self.fig.add_axes([0.88, 0.15, 0.03, 0.7])
            self.selection_tab.setup_events()
            self.show_view(self.current_view)
            
        elif selected_tab == "Customization":
            self.customization_tab.draw_cross_section()
            
        elif selected_tab == "Path Mapper":
            self.path_mapper_tab.draw_path_mapper()

    def show(self):
        self.root.mainloop()

    def open_file_dialog(self):
        filepath = ctk.filedialog.askopenfilename(
            title="Select 3D CAD Model", 
            filetypes=[("STEP Files", "*.stp *.step"), ("All Files", "*.*")]
        )
        if filepath:
            # โหลดไฟล์ใหม่ → ล้าง pin ทั้งหมด (พิกัดเดิมไม่มีความหมายกับโมเดลใหม่)
            self.selection_tab.clear_pins()

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

    def show_view(self, view_name):
        if self.geo.mesh is None: return

        # เปลี่ยนมุมมอง (Top -> Bottom, Front -> Left, ฯลฯ) → ล้าง pin ทั้งหมด
        # เช็คก่อนเปลี่ยน self.current_view เพื่อแยกแยะ "เปลี่ยนมุมมองจริง" ออกจาก
        # การเรียก show_view(self.current_view) ซ้ำมุมมองเดิม ซึ่งใช้ใน
        # on_generate_holes() / on_clear_holes() / reset_position() ที่ต้องการ
        # คง pin เดิมไว้ (caller เหล่านั้นจะ save/restore pin ของตัวเองอยู่แล้ว)
        if view_name != self.current_view:
            self.selection_tab.clear_pins()

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
                self.current_holes = self.selection_tab.detect_holes_in_view(
                    x[visible_vert_idx], y[visible_vert_idx],
                    z_v[visible_vert_idx], view_name)

            if len(self.current_holes) == 0:
                _mb.showinfo("No Holes", f"ไม่พบรูในมุมมอง {view_name}")
        else:
            self.current_holes = []
            
        title = f"{view_name} View"
        self.selection_tab.update_plot(x, y, z_v, z_f, tri, title, holes=self.current_holes)
        self.update_treeview(self.current_holes)

    def on_generate_holes(self):
        if self.geo.mesh is None: return
        self.holes_detected = True
        self._set_view_controls_locked(True) 
        if self.current_tab == "Selection":
            # บันทึก pin เดิมไว้ก่อน redraw แล้ว restore กลับหลัง show_view()
            # (Generate Holes ไม่ควรทำให้ pin ที่ติดไว้หายไป)
            saved_pins = list(self.selection_tab._pinned_pin_data)
            self.show_view(self.current_view)
            self.selection_tab._restore_pins(saved_pins)
        
    def on_clear_holes(self):
        self.holes_detected = False
        self.current_holes = []
        self.selected_hole_idx = None
        self._set_view_controls_locked(False)

        # บันทึก pin เดิมไว้ก่อน redraw แล้ว restore กลับหลัง on_nav_change()
        # (Clear Holes ควรล้างแค่ข้อมูลรู ไม่ใช่ pin ที่ผู้ใช้ติดไว้)
        saved_pins = list(self.selection_tab._pinned_pin_data)
        self.nav_selector.set("Selection")
        self.on_nav_change("Selection")
        self.selection_tab._restore_pins(saved_pins)

    def rotate_screen(self):
        if self.geo.mesh is None: return
        # Rotate มุมมอง → ล้าง pin ทั้งหมด (พิกัด 2D เดิมใช้ไม่ได้กับมุมที่หมุนใหม่)
        self.selection_tab.clear_pins()
        self.screen_rotation = (self.screen_rotation + 90) % 360
        self.show_view(self.current_view)

    def reset_position(self):
        """
        Reset กลับมุมมองเดิม — Pin ที่ pin ไว้จะยังคงอยู่ โดยบันทึกข้อมูล
        pin ก่อน redraw แล้ว restore กลับหลัง update_plot เสร็จ
        """
        if self.geo.mesh is None: return
        if self.current_tab != "Selection": return

        # --- บันทึก pin data ก่อน redraw ---
        saved_pins = list(self.selection_tab._pinned_pin_data)

        # --- Redraw (ax.clear ใน update_plot จะลบ artist ทั้งหมด) ---
        self.show_view(self.current_view)

        # --- Restore pins หลัง redraw ---
        self.selection_tab._restore_pins(saved_pins)

    # ---------------------------------------------------------
    # Hole Settings UI (Sidebar ขวา)
    # ---------------------------------------------------------
    def update_treeview(self, holes):
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
            self.customization_tab.draw_cross_section()
        elif self.current_tab == "Path Mapper":
            self.path_mapper_tab.draw_path_mapper()

    def on_config_change_for_hole(self, idx):
        if idx >= len(self.current_holes):
            return
        hole = self.current_holes[idx]
        widgets = self.hole_widgets[idx]
        hole.layers = int(widgets['opt_layers'].get())
        hole.points_per_layer = int(widgets['opt_points'].get())
        if self.current_tab == "Path Mapper":
            self.path_mapper_tab.draw_path_mapper()
        elif self.current_tab == "Customization":
            self.customization_tab.draw_cross_section()
