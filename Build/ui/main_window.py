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
from core.probe_profile import ProbeProfile
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

        # --- Feature: Probe Profile ---
        # เก็บโปรไฟล์ probe stylus ที่ผู้ใช้กำหนด (ใช้ ProbeProfile dataclass)
        self.probe_profile = ProbeProfile()

        # --- Feature: รายการรูที่ถูกเลือกเพื่อ inspect ---
        # เก็บ index ของรู (ตาม self.current_holes) ที่มี selected_for_inspection == True
        self.inspection_selected_holes = []   # list[int]

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
        # ใช้ scrollable frame เพื่อรองรับ probe panel ที่เพิ่มขึ้นมา
        self._left_scroll = ctk.CTkScrollableFrame(
            self.sidebar_left, fg_color="transparent", width=230)
        self._left_scroll.pack(fill="both", expand=True, padx=0, pady=0)

        ctk.CTkLabel(
            self._left_scroll, text="3D CNC Control",
            font=ctk.CTkFont(size=20, weight="bold")
        ).pack(pady=(20, 10))

        self.btn_upload = ctk.CTkButton(
            self._left_scroll, text="Upload STEP or STP",
            fg_color="#2e7d32", hover_color="#4caf50",
            command=self.open_file_dialog)
        self.btn_upload.pack(pady=10, padx=20, fill="x")

        self.info_frame = ctk.CTkFrame(self._left_scroll, fg_color="#1e1e1e", corner_radius=5)
        self.info_frame.pack(pady=(0, 15), padx=20, fill="x")

        self.lbl_width = ctk.CTkLabel(
            self.info_frame, text="Width (X): -- mm",
            text_color="gray", font=ctk.CTkFont(size=12))
        self.lbl_width.pack(pady=(5, 0), padx=10, anchor="w")

        self.lbl_length = ctk.CTkLabel(
            self.info_frame, text="Length (Y): -- mm",
            text_color="gray", font=ctk.CTkFont(size=12))
        self.lbl_length.pack(pady=0, padx=10, anchor="w")

        self.lbl_thick = ctk.CTkLabel(
            self.info_frame, text="Thickness (Z): -- mm",
            text_color="gray", font=ctk.CTkFont(size=12))
        self.lbl_thick.pack(pady=(0, 5), padx=10, anchor="w")

        self.btn_detect = ctk.CTkButton(
            self._left_scroll, text="🔍 Generate Holes",
            fg_color="#f57c00", hover_color="#ef6c00",
            command=self.on_generate_holes)
        self.btn_detect.pack(pady=(10, 5), padx=20, fill="x")

        self.btn_clear = ctk.CTkButton(
            self._left_scroll, text="❌ Clear & Unlock",
            fg_color="#c62828", hover_color="#b71c1c",
            command=self.on_clear_holes, state="disabled")
        self.btn_clear.pack(pady=(0, 10), padx=20, fill="x")

        ctk.CTkLabel(
            self._left_scroll, text="--- View Controls ---",
            text_color="gray").pack(pady=(20, 5))

        self.btn_rotate = ctk.CTkButton(
            self._left_scroll, text="⟳ Rotate 90°",
            fg_color="#0277bd", hover_color="#039be5",
            command=self.rotate_screen)
        self.btn_rotate.pack(pady=10, padx=20, fill="x")

        self.btn_reset = ctk.CTkButton(
            self._left_scroll, text="⌂ Reset Position",
            fg_color="#d84315", hover_color="#bf360c",
            command=self.reset_position)
        self.btn_reset.pack(pady=(0, 10), padx=20, fill="x")

        view_frame = ctk.CTkFrame(self._left_scroll, fg_color="transparent")
        view_frame.pack(pady=10, padx=20, fill="x")

        views = [('Top', 0, 0), ('Bottom', 0, 1),
                 ('Front', 1, 0), ('Back', 1, 1),
                 ('Left', 2, 0), ('Right', 2, 1)]

        for name, row, col in views:
            btn = ctk.CTkButton(
                view_frame, text=name, width=85,
                fg_color="#424242", hover_color="#616161",
                command=lambda v=name: self.show_view(v))
            btn.grid(row=row, column=col, padx=5, pady=5)
            self.view_buttons[name] = btn

        # ------------------------------------------------------------------
        # 🔩 Probe Stylus Profile Panel
        # ------------------------------------------------------------------
        self._setup_probe_profile_panel()

    def _setup_probe_profile_panel(self):
        """
        สร้าง collapsible panel สำหรับตั้งค่าขนาดทางกายภาพของ Touch Probe Stylus
        วางไว้ใน _left_scroll ต่อจาก View Controls
        """
        # ── Header (คลิกเพื่อ expand/collapse) ──────────────────────────
        probe_header_frame = ctk.CTkFrame(self._left_scroll, fg_color="#1a1a2e", corner_radius=6)
        probe_header_frame.pack(pady=(18, 0), padx=12, fill="x")

        self._probe_panel_expanded = False  # เริ่มต้น collapsed

        self._probe_toggle_btn = ctk.CTkButton(
            probe_header_frame,
            text="🔩 Probe Stylus Profile  ▸",
            fg_color="transparent",
            hover_color="#2a2a4e",
            anchor="w",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#90caf9",
            command=self._toggle_probe_panel,
        )
        self._probe_toggle_btn.pack(fill="x", padx=4, pady=6)

        # ── Body (collapsed by default) ──────────────────────────────────
        self._probe_body = ctk.CTkFrame(self._left_scroll, fg_color="#12122a", corner_radius=6)
        # ไม่ pack ตอนเริ่ม (collapsed)

        # ---- Stylus Length ----
        len_row = ctk.CTkFrame(self._probe_body, fg_color="transparent")
        len_row.pack(fill="x", padx=14, pady=(12, 4))

        ctk.CTkLabel(
            len_row, text="Stylus Length (mm):",
            font=ctk.CTkFont(size=12), text_color="#b0bec5"
        ).pack(anchor="w")

        len_entry_row = ctk.CTkFrame(len_row, fg_color="transparent")
        len_entry_row.pack(fill="x", pady=(4, 0))

        self._probe_length_entry = ctk.CTkEntry(
            len_entry_row, width=90, height=28,
            placeholder_text="50.0",
            font=ctk.CTkFont(size=13),
        )
        self._probe_length_entry.insert(0, str(self.probe_profile.stylus_length))
        self._probe_length_entry.pack(side="left")

        ctk.CTkLabel(
            len_entry_row, text="mm",
            font=ctk.CTkFont(size=11), text_color="#78909c"
        ).pack(side="left", padx=(6, 0))

        # ---- Tip Diameter ----
        tip_row = ctk.CTkFrame(self._probe_body, fg_color="transparent")
        tip_row.pack(fill="x", padx=14, pady=(6, 4))

        ctk.CTkLabel(
            tip_row, text="Tip Diameter ⌀ (mm):",
            font=ctk.CTkFont(size=12), text_color="#b0bec5"
        ).pack(anchor="w")

        tip_entry_row = ctk.CTkFrame(tip_row, fg_color="transparent")
        tip_entry_row.pack(fill="x", pady=(4, 0))

        self._probe_tip_entry = ctk.CTkEntry(
            tip_entry_row, width=90, height=28,
            placeholder_text="2.0",
            font=ctk.CTkFont(size=13),
        )
        self._probe_tip_entry.insert(0, str(self.probe_profile.tip_diameter))
        self._probe_tip_entry.pack(side="left")

        ctk.CTkLabel(
            tip_entry_row, text="mm",
            font=ctk.CTkFont(size=11), text_color="#78909c"
        ).pack(side="left", padx=(6, 0))

        # ---- Divider ----
        ctk.CTkFrame(self._probe_body, height=1, fg_color="#2a2a4e").pack(
            fill="x", padx=14, pady=(10, 6))

        # ---- Apply Button ----
        self._btn_apply_probe = ctk.CTkButton(
            self._probe_body,
            text="✔ Apply Profile",
            fg_color="#1565c0", hover_color="#1976d2",
            font=ctk.CTkFont(size=12, weight="bold"),
            height=30,
            command=self._apply_probe_profile,
        )
        self._btn_apply_probe.pack(fill="x", padx=14, pady=(0, 6))

        # ---- Reset Button ----
        self._btn_reset_probe = ctk.CTkButton(
            self._probe_body,
            text="↺ Reset to Default",
            fg_color="#37474f", hover_color="#546e7a",
            font=ctk.CTkFont(size=11),
            height=26,
            command=self._reset_probe_profile,
        )
        self._btn_reset_probe.pack(fill="x", padx=14, pady=(0, 10))

        # ---- Current values summary label ----
        self._lbl_probe_summary = ctk.CTkLabel(
            self._probe_body,
            text=self._probe_summary_text(),
            font=ctk.CTkFont(size=10),
            text_color="#546e7a",
            justify="left",
        )
        self._lbl_probe_summary.pack(anchor="w", padx=14, pady=(0, 10))

    # ------------------------------------------------------------------
    # Probe Panel Helpers
    # ------------------------------------------------------------------
    def _toggle_probe_panel(self):
        self._probe_panel_expanded = not self._probe_panel_expanded
        if self._probe_panel_expanded:
            self._probe_body.pack(pady=(0, 10), padx=12, fill="x")
            self._probe_toggle_btn.configure(text="🔩 Probe Stylus Profile  ▾")
        else:
            self._probe_body.pack_forget()
            self._probe_toggle_btn.configure(text="🔩 Probe Stylus Profile  ▸")

    def _probe_summary_text(self) -> str:
        return (
            f"  Length : {self.probe_profile.stylus_length:.1f} mm\n"
            f"  Tip ⌀  : {self.probe_profile.tip_diameter:.1f} mm  "
            f"(r = {self.probe_profile.tip_radius:.2f} mm)"
        )

    def _apply_probe_profile(self):
        """อ่านค่าจาก Entry fields และอัปเดต probe_profile แล้ว refresh warnings"""
        try:
            new_length = float(self._probe_length_entry.get().strip())
            if new_length <= 0:
                raise ValueError("ความยาวต้องมากกว่า 0")
        except ValueError as e:
            _mb.showerror("Invalid Input", f"Stylus Length ไม่ถูกต้อง:\n{e}")
            return

        try:
            new_tip_d = float(self._probe_tip_entry.get().strip())
            if new_tip_d <= 0:
                raise ValueError("เส้นผ่าศูนย์กลางต้องมากกว่า 0")
        except ValueError as e:
            _mb.showerror("Invalid Input", f"Tip Diameter ไม่ถูกต้อง:\n{e}")
            return

        self.probe_profile.stylus_length = new_length
        self.probe_profile.tip_diameter  = new_tip_d

        # อัปเดต summary label
        self._lbl_probe_summary.configure(text=self._probe_summary_text())

        print(f"[probe] Profile updated — length={new_length} mm, tip⌀={new_tip_d} mm")

        # Refresh warnings ในรายการรูทางขวา (ถ้ามีรูอยู่แล้ว)
        if self.holes_detected and self.current_holes:
            self.update_treeview(self.current_holes)

    def _reset_probe_profile(self):
        """Reset probe profile กลับค่า default แล้ว refresh"""
        self.probe_profile.stylus_length = self.probe_profile.DEFAULT_LENGTH
        self.probe_profile.tip_diameter  = self.probe_profile.DEFAULT_TIP_D

        # อัปเดต entry fields
        self._probe_length_entry.delete(0, "end")
        self._probe_length_entry.insert(0, str(self.probe_profile.stylus_length))
        self._probe_tip_entry.delete(0, "end")
        self._probe_tip_entry.insert(0, str(self.probe_profile.tip_diameter))

        self._lbl_probe_summary.configure(text=self._probe_summary_text())

        print("[probe] Profile reset to default")

        if self.holes_detected and self.current_holes:
            self.update_treeview(self.current_holes)

    def _setup_right_sidebar(self):
        # --- Header: ชื่อ + badge จำนวนรูที่เลือก ---
        header_frame = ctk.CTkFrame(self.sidebar_right, fg_color="transparent")
        header_frame.pack(pady=(20, 4), padx=20, fill="x")

        self.right_header = ctk.CTkLabel(
            header_frame, text="Detected Holes",
            font=ctk.CTkFont(size=16, weight="bold"))
        self.right_header.pack(side="left")

        self.lbl_selected_count = ctk.CTkLabel(
            header_frame, text="",
            font=ctk.CTkFont(size=11),
            text_color="#3694ED")
        self.lbl_selected_count.pack(side="right")

        self.holes_list_frame = ctk.CTkScrollableFrame(self.sidebar_right, fg_color="transparent")
        self.holes_list_frame.pack(fill="both", expand=True, padx=10, pady=5)

    def _refresh_selected_count_label(self):
        """อัปเดต badge "X selected" บน header ขวา"""
        count = len(self.inspection_selected_holes)
        if count == 0:
            self.lbl_selected_count.configure(text="")
        else:
            self.lbl_selected_count.configure(text=f"✅ {count} selected")

    def _set_view_controls_locked(self, is_locked):
        rotate_state = "disabled" if is_locked else "normal"
        self.btn_rotate.configure(state=rotate_state)
        for btn in self.view_buttons.values():
            btn.configure(state=rotate_state)

        self.btn_reset.configure(state="normal")
        self.btn_detect.configure(state="disabled" if is_locked else "normal")
        self.btn_clear.configure(state="normal" if is_locked else "disabled")

    # ---------------------------------------------------------
    # Core Functions
    # ---------------------------------------------------------
    def on_nav_change(self, selected_tab):
        # ── Guard: ห้าม switch ไป Customization ถ้ายังไม่มีรูถูกตรวจพบ ──────────
        if selected_tab == "Customization":
            if not self.holes_detected or len(self.current_holes) == 0:
                _mb.showwarning(
                    "ไม่พบรูในโมเดล",
                    "กรุณากด 'Generate Holes' และตรวจสอบให้แน่ใจว่ามีรูถูกตรวจพบก่อน\n"
                    "จึงจะสามารถเข้าใช้งานแท็บ Customization ได้"
                )
                # Reset segmented button กลับไปที่ tab เดิม
                self.nav_selector.set(self.current_tab)
                return
        # ─────────────────────────────────────────────────────────────────────────

        self.selection_tab.clear_pins()

        self.current_tab = selected_tab
        self.sidebar_right.pack(side="right", fill="y", before=self.center_frame)

        if selected_tab == "Customization":
            self.btn_reset.configure(state="disabled")
        else:
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
            self.selection_tab.clear_pins()
            self.geo.load_file(filepath)
            self.screen_rotation = 0
            self.holes_detected = False
            self.current_holes = []
            self.selected_hole_idx = None
            self.inspection_selected_holes = []
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
            # ── บันทึกสถานะ checkbox ของรูเดิมก่อน rebuild ──────────────────
            # จับคู่ด้วย hole.id เพื่อให้ทน view-switch / reorder ได้
            prev_states: dict[int, dict] = {}
            for h in self.current_holes:
                prev_states[h.id] = {
                    'selected':   getattr(h, 'selected_for_inspection', False),
                    'zigzag':     getattr(h, 'zigzag_inspection',       False),
                    'zigzag_deg': getattr(h, 'zigzag_degree',           45.0),
                    'layers':     getattr(h, 'layers',                  3),
                    'points':     getattr(h, 'points_per_layer',        4),
                }

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

            # ── Restore สถานะ checkbox และ config ลงบนรูชุดใหม่ ──────────────
            for h in self.current_holes:
                state = prev_states.get(h.id, {})
                h.selected_for_inspection = state.get('selected',    False)
                h.zigzag_inspection       = state.get('zigzag',      False)
                h.zigzag_degree           = state.get('zigzag_deg',  45.0)
                h.layers                  = state.get('layers',      3)
                h.points_per_layer        = state.get('points',      4)

            # Rebuild inspection_selected_holes จากสถานะที่ restore แล้ว
            self.inspection_selected_holes = [
                i for i, h in enumerate(self.current_holes)
                if h.selected_for_inspection
            ]
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
            saved_pins = list(self.selection_tab._pinned_pin_data)
            self.show_view(self.current_view)
            self.selection_tab._restore_pins(saved_pins)

    def on_clear_holes(self):
        self.holes_detected = False
        self.current_holes = []
        self.selected_hole_idx = None
        self.inspection_selected_holes = []
        self._set_view_controls_locked(False)
        self._refresh_selected_count_label()

        saved_pins = list(self.selection_tab._pinned_pin_data)
        self.nav_selector.set("Selection")
        self.on_nav_change("Selection")
        self.selection_tab._restore_pins(saved_pins)

    def rotate_screen(self):
        if self.geo.mesh is None: return
        self.selection_tab.clear_pins()
        self.screen_rotation = (self.screen_rotation + 90) % 360
        self.show_view(self.current_view)

    def reset_position(self):
        if self.geo.mesh is None: return
        if self.current_tab != "Selection": return

        saved_pins = list(self.selection_tab._pinned_pin_data)
        self.show_view(self.current_view)
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
            self._refresh_selected_count_label()
            return
        elif not self.holes_detected:
            ctk.CTkLabel(self.holes_list_frame, text="-- Press Generate Holes --", text_color="gray").pack(pady=20)
            self._refresh_selected_count_label()
            return

        for i, hole in enumerate(holes):
            # ── ตรวจสอบ probe compatibility สำหรับรูนี้ ──────────────────────
            probe_check = self.probe_profile.check_hole(hole.depth, hole.radius)
            has_warning = not probe_check['ok']

            container = ctk.CTkFrame(self.holes_list_frame, fg_color="transparent")
            container.pack(fill="x", pady=2)

            btn_text = f"🎯 Hole {hole.id} [X: {hole.x:.2f}, Y: {hole.y:.2f}] D: {hole.depth:.2f}"

            # ถ้ามี probe warning → ขอบปุ่มแดงอ่อน
            btn_border = "#c62828" if has_warning else None
            btn = ctk.CTkButton(
                container, text=btn_text, anchor="w",
                fg_color="#1f1f1f", hover_color="#2c2c2c", corner_radius=4,
                border_color=btn_border,
                border_width=1 if has_warning else 0,
                command=lambda idx=i: self.on_hole_select(idx))
            btn.pack(fill="x")

            # ── Probe Warning Labels (แสดงใต้ปุ่มของรูนี้เสมอ) ───────────────
            warning_labels = []
            for warn_text in [probe_check['depth_warning'], probe_check['fit_warning']]:
                if warn_text:
                    lbl_warn = ctk.CTkLabel(
                        container,
                        text=warn_text,
                        text_color="#ef5350",
                        font=ctk.CTkFont(size=10, weight="bold"),
                        anchor="w",
                        wraplength=290,
                    )
                    lbl_warn.pack(fill="x", padx=6, pady=(1, 0))
                    warning_labels.append(lbl_warn)

            # ---- Settings Panel (hidden by default, shown on hole select) ----
            settings_frame = ctk.CTkFrame(container, fg_color="#2b2b2b", corner_radius=4)

            # --- Z-Layers ---
            layer_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
            layer_frame.pack(fill="x", padx=15, pady=(10, 5))
            ctk.CTkLabel(layer_frame, text="Z-Layers:").pack(side="left")
            opt_layers = ctk.CTkOptionMenu(
                layer_frame, values=["3", "4", "5", "6", "8", "10"],
                command=lambda val, idx=i: self.on_config_change_for_hole(idx),
                width=60, height=25)
            opt_layers.set(str(hole.layers))
            opt_layers.pack(side="right")

            # --- Points / Layer ---
            points_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
            points_frame.pack(fill="x", padx=15, pady=(0, 5))
            ctk.CTkLabel(points_frame, text="Points/Layer:").pack(side="left")
            opt_points = ctk.CTkOptionMenu(
                points_frame, values=["4", "6", "8", "12", "16"],
                command=lambda val, idx=i: self.on_config_change_for_hole(idx),
                width=60, height=25)
            opt_points.set(str(hole.points_per_layer))
            opt_points.pack(side="right")

            # ---- Divider ----
            ctk.CTkFrame(settings_frame, height=1, fg_color="#444444").pack(fill="x", padx=15, pady=(4, 6))

            # ---- ✅ Selected for Inspection checkbox ----
            chk_selected_var = ctk.BooleanVar(value=hole.selected_for_inspection)
            chk_selected = ctk.CTkCheckBox(
                settings_frame,
                text="✅  Select for Inspection",
                variable=chk_selected_var,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="#4fc3f7",
                fg_color="#1f538d",
                hover_color="#2979ff",
                command=lambda idx=i, var=chk_selected_var: self._on_inspection_select_toggle(idx, var)
            )
            chk_selected.pack(anchor="w", padx=15, pady=(0, 4))

            # ---- ↕ Zigzag Inspection checkbox ----
            chk_zigzag_var = ctk.BooleanVar(value=hole.zigzag_inspection)
            chk_zigzag = ctk.CTkCheckBox(
                settings_frame,
                text="↕  Zigzag Inspection",
                variable=chk_zigzag_var,
                font=ctk.CTkFont(size=12),
                text_color="#a5d6a7",
                fg_color="#2e7d32",
                hover_color="#43a047",
                command=lambda idx=i, var=chk_zigzag_var: self._on_zigzag_toggle(idx, var)
            )
            chk_zigzag.pack(anchor="w", padx=15, pady=(0, 4))

            # ---- Zigzag degree input (visible only when zigzag is ON) ----
            degree_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
            ctk.CTkLabel(degree_frame, text="Rotation/Layer (°):",
                         font=ctk.CTkFont(size=11), text_color="#a5d6a7").pack(side="left")
            degree_entry = ctk.CTkEntry(
                degree_frame, width=58, height=25,
                placeholder_text="45",
                font=ctk.CTkFont(size=12),
            )
            degree_entry.insert(0, str(int(hole.zigzag_degree))
                                if hole.zigzag_degree == int(hole.zigzag_degree)
                                else str(hole.zigzag_degree))
            degree_entry.pack(side="right", padx=(6, 0))
            degree_entry.bind("<Return>",   lambda e, idx=i: self._on_zigzag_degree_change(idx))
            degree_entry.bind("<FocusOut>", lambda e, idx=i: self._on_zigzag_degree_change(idx))
            degree_frame.pack(fill="x", padx=15, pady=(0, 8))

            # hide degree row if zigzag currently off
            if not hole.zigzag_inspection:
                degree_frame.pack_forget()

            ctk.CTkFrame(settings_frame, height=1, fg_color="#333333").pack(fill="x", padx=15, pady=(0, 6))

            self.hole_widgets[i] = {
                'container':        container,
                'btn':              btn,
                'warning_labels':   warning_labels,
                'settings_frame':   settings_frame,
                'opt_layers':       opt_layers,
                'opt_points':       opt_points,
                'chk_selected':     chk_selected,
                'chk_selected_var': chk_selected_var,
                'chk_zigzag':       chk_zigzag,
                'chk_zigzag_var':   chk_zigzag_var,
                'degree_frame':     degree_frame,
                'degree_entry':     degree_entry,
                'is_expanded':      False,
                'probe_check':      probe_check,   # เก็บผลตรวจสอบไว้ใช้ตอน select
            }

        self._refresh_selected_count_label()

    # ------------------------------------------------------------------
    # Checkbox Callbacks
    # ------------------------------------------------------------------
    def _on_inspection_select_toggle(self, idx: int, var: ctk.BooleanVar):
        """เรียกเมื่อผู้ใช้ toggle checkbox 'Select for Inspection'"""
        if idx >= len(self.current_holes):
            return

        hole = self.current_holes[idx]

        # ── ถ้า probe ไม่ผ่านและผู้ใช้พยายาม select → popup error ────────────
        if var.get():
            probe_check = self.probe_profile.check_hole(hole.depth, hole.radius)
            if not probe_check['ok']:
                # Revert checkbox ก่อน (ยังไม่ allow select)
                var.set(False)

                # สร้างข้อความ error
                error_lines = []
                if probe_check['depth_warning']:
                    error_lines.append(probe_check['depth_warning'])
                if probe_check['fit_warning']:
                    error_lines.append(probe_check['fit_warning'])
                error_lines.append(
                    f"\nPlease update the Probe Stylus Profile\n"
                    f"(current: length={self.probe_profile.stylus_length:.1f} mm, "
                    f"tip⌀={self.probe_profile.tip_diameter:.1f} mm)"
                )

                _mb.showerror(
                    "Probe Cannot Reach This Hole",
                    "\n".join(error_lines)
                )
                return

        hole.selected_for_inspection = var.get()

        # อัปเดต inspection_selected_holes list
        if hole.selected_for_inspection:
            if idx not in self.inspection_selected_holes:
                self.inspection_selected_holes.append(idx)
                self.inspection_selected_holes.sort()
        else:
            if idx in self.inspection_selected_holes:
                self.inspection_selected_holes.remove(idx)

        self._refresh_selected_count_label()

        # เปลี่ยนสีปุ่มรูเพื่อให้เห็นชัดว่าถูกเลือก
        if idx in self.hole_widgets:
            btn = self.hole_widgets[idx]['btn']
            if hole.selected_for_inspection:
                btn.configure(fg_color="#1a3a5c")
            else:
                btn.configure(fg_color="#1f538d" if idx == self.selected_hole_idx else "#1f1f1f")

        print(f"[inspect] Selected holes for inspection: {self.inspection_selected_holes}")

    def _on_zigzag_toggle(self, idx: int, var: ctk.BooleanVar):
        """เรียกเมื่อผู้ใช้ toggle checkbox 'Zigzag Inspection'"""
        if idx >= len(self.current_holes):
            return

        hole = self.current_holes[idx]
        hole.zigzag_inspection = var.get()

        # แสดง/ซ่อน degree input ตาม state ของ checkbox
        if idx in self.hole_widgets:
            df = self.hole_widgets[idx]['degree_frame']
            sf = self.hole_widgets[idx]['settings_frame']
            if hole.zigzag_inspection:
                df.pack(in_=sf, fill="x", padx=15, pady=(0, 8),
                        after=self.hole_widgets[idx]['chk_zigzag'])
            else:
                df.pack_forget()

        print(f"[zigzag] Hole {hole.id} zigzag={hole.zigzag_inspection}, degree={hole.zigzag_degree}")

        if self.current_tab == "Customization" and self.selected_hole_idx == idx:
            self.customization_tab.draw_cross_section()

    def _on_zigzag_degree_change(self, idx: int):
        """เรียกเมื่อผู้ใช้กด Enter หรือ FocusOut บน degree entry"""
        if idx >= len(self.current_holes):
            return
        if idx not in self.hole_widgets:
            return

        hole  = self.current_holes[idx]
        entry = self.hole_widgets[idx]['degree_entry']
        raw   = entry.get().strip()

        try:
            val = float(raw)
            val = max(1.0, min(180.0, val))
        except ValueError:
            val = hole.zigzag_degree

        hole.zigzag_degree = val

        entry.delete(0, "end")
        entry.insert(0, str(int(val)) if val == int(val) else str(val))

        print(f"[zigzag] Hole {hole.id} degree={hole.zigzag_degree}")

        if self.current_tab == "Customization" and self.selected_hole_idx == idx:
            self.customization_tab.draw_cross_section()

    # ------------------------------------------------------------------
    # Hole Selection / Config
    # ------------------------------------------------------------------
    def on_hole_select(self, idx):
        # ── Toggle-off: คลิกซ้ำที่รูที่ถูกเลือกอยู่แล้ว → ยกเลิกการเลือก ──────
        is_deselecting = (self.selected_hole_idx == idx)

        for i, widgets in self.hole_widgets.items():
            hole_i = self.current_holes[i] if i < len(self.current_holes) else None
            default_color = "#1a3a5c" if (hole_i and hole_i.selected_for_inspection) else "#1f1f1f"
            widgets['btn'].configure(fg_color=default_color)

            if widgets['is_expanded'] and i != idx:
                widgets['settings_frame'].pack_forget()
                widgets['is_expanded'] = False

        if is_deselecting:
            sel = self.hole_widgets[idx]
            if sel['is_expanded']:
                sel['settings_frame'].pack_forget()
                sel['is_expanded'] = False

            self.selected_hole_idx = None
        else:
            sel = self.hole_widgets[idx]
            sel['btn'].configure(fg_color="#1f538d")
            if not sel['is_expanded']:
                sel['settings_frame'].pack(fill="x", pady=(0, 2))
                sel['is_expanded'] = True

            self.selected_hole_idx = idx

            # ── Probe warning popup เมื่อคลิกเลือกรู (แจ้งเตือนเชิง info เท่านั้น) ──
            # Popup นี้แสดงเพื่อ inform เท่านั้น ไม่บล็อกการเลือก
            # การบล็อกจริงๆ เกิดใน _on_inspection_select_toggle เมื่อพยายาม add to list
            if idx in self.hole_widgets:
                probe_check = self.hole_widgets[idx].get('probe_check', {'ok': True})
                if not probe_check['ok']:
                    # ไม่ popup ซ้ำถ้า setting_frame ถูก expand แล้ว (เห็น warning label อยู่แล้ว)
                    # warnings ถูกแสดงในรายการอยู่แล้ว ไม่ต้อง popup ซ้ำตอนแค่ click select
                    pass

        if self.current_tab == "Selection" and self.scatter_holes:
            colors = ['white'] * self.current_holes_count
            if self.selected_hole_idx is not None:
                colors[self.selected_hole_idx] = 'yellow'
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

    # ------------------------------------------------------------------
    # Public Helper: ดึงรายการรูที่ถูกเลือกเพื่อ inspect (ใช้จากโมดูลอื่น)
    # ------------------------------------------------------------------
    def get_holes_for_inspection(self) -> list:
        """
        คืนค่า list[HoleFeature] ที่มี selected_for_inspection == True
        เรียงตาม index ของรูในมุมมองปัจจุบัน
        """
        return [self.current_holes[i] for i in self.inspection_selected_holes
                if i < len(self.current_holes)]
