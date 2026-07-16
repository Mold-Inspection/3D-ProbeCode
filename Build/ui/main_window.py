# ui/main_window.py
# VERSION: 08
# CHANGE LOG:
#   - UX Update: "Select for Inspection" checkboxes moved to the right side of the hole header.
#   - UX Update: Toggling inspection checkbox no longer triggers auto-refresh. User must click "Apply Selection".
#   - UX Update: Unselected Holes item layout upgraded to match Selected Holes.
#   - Restored missing Z-Layers, Points/Layer, and Zigzag UI components inside expanded view.

import customtkinter as ctk
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

        # --- State ---
        self.current_view       = 'Top'
        self.screen_rotation    = 0
        self.scatter_holes      = None
        self.current_holes_count = 0
        self.current_holes      = []
        self.holes_detected     = False

        self.current_tab        = "Selection"
        self.selected_hole_idx  = None
        self.max_physical_dim   = None

        self.view_buttons  = {}
        self.hole_widgets  = {}

        self._visible_hole_map  = {}

        # --- Probe Profile ---
        self.probe_profile = ProbeProfile()

        # --- Inspection selection list ---
        self.inspection_selected_holes = []

        # --- Tab instances ---
        self.selection_tab     = SelectionTab(self)
        self.customization_tab = CustomizationTab(self)
        self.path_mapper_tab   = PathMapperTab(self)

        # --- Main window ---
        self.root = ctk.CTk()
        self.root.title("3D ProbeCode")
        self.root.geometry("1400x800")

        # Layout
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

        # --- Matplotlib canvas ---
        plt.style.use('dark_background')
        colors    = ["white", "yellow", "orange", "red"]
        self.cmap = LinearSegmentedColormap.from_list("depth_color", colors)

        self.fig = Figure(figsize=(10, 8), facecolor='#242424')
        self.fig.tight_layout(pad=3.0)
        self.ax  = self.fig.add_subplot(111, facecolor='#1e1e1e')
        self.fig.subplots_adjust(bottom=0.1, right=0.85, left=0.1, top=0.9)
        self.cax = self.fig.add_axes([0.88, 0.15, 0.03, 0.7])

        self.drag_state = {'is_dragging': False, 'x': 0, 'y': 0, 'xlim': None, 'ylim': None}

        self.canvas        = FigureCanvasTkAgg(self.fig, master=self.center_frame)
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
        self.selection_tab.setup_events()

        if self.geo.mesh is not None:
            self.show_view('Top')

    # ---------------------------------------------------------
    # UI Sidebar Setup
    # ---------------------------------------------------------
    def _setup_left_sidebar(self):
        self._left_scroll = ctk.CTkScrollableFrame(self.sidebar_left, fg_color="transparent", width=230)
        self._left_scroll.pack(fill="both", expand=True, padx=0, pady=0)

        ctk.CTkLabel(
            self._left_scroll, text="3D ProbeCode Control",
            font=ctk.CTkFont(size=20, weight="bold")
        ).pack(pady=(20, 10))

        self.btn_upload = ctk.CTkButton(
            self._left_scroll, text="Upload STEP or STP",
            fg_color="#2e7d32", hover_color="#4caf50",
            command=self.open_file_dialog)
        self.btn_upload.pack(pady=10, padx=20, fill="x")

        self.info_frame = ctk.CTkFrame(self._left_scroll, fg_color="#1e1e1e", corner_radius=5)
        self.info_frame.pack(pady=(0, 15), padx=20, fill="x")

        self.lbl_width = ctk.CTkLabel(self.info_frame, text="Width (X): -- mm", text_color="gray", font=ctk.CTkFont(size=12))
        self.lbl_width.pack(pady=(5, 0), padx=10, anchor="w")

        self.lbl_length = ctk.CTkLabel(self.info_frame, text="Length (Y): -- mm", text_color="gray", font=ctk.CTkFont(size=12))
        self.lbl_length.pack(pady=0, padx=10, anchor="w")

        self.lbl_thick = ctk.CTkLabel(self.info_frame, text="Thickness (Z): -- mm", text_color="gray", font=ctk.CTkFont(size=12))
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

        ctk.CTkLabel(self._left_scroll, text="--- View Controls ---", text_color="gray").pack(pady=(20, 5))

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

        self._setup_probe_profile_panel()

    def _setup_probe_profile_panel(self):
        probe_header_frame = ctk.CTkFrame(self._left_scroll, fg_color="#1a1a2e", corner_radius=6)
        probe_header_frame.pack(pady=(18, 0), padx=12, fill="x")

        self._probe_panel_expanded = False

        self._probe_toggle_btn = ctk.CTkButton(
            probe_header_frame,
            text="🔩 Probe Stylus Profile  ▸",
            fg_color="transparent", hover_color="#2a2a4e",
            anchor="w", font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#90caf9", command=self._toggle_probe_panel,
        )
        self._probe_toggle_btn.pack(fill="x", padx=4, pady=6)

        self._probe_body = ctk.CTkFrame(self._left_scroll, fg_color="#12122a", corner_radius=6)

        len_row = ctk.CTkFrame(self._probe_body, fg_color="transparent")
        len_row.pack(fill="x", padx=14, pady=(12, 4))
        ctk.CTkLabel(len_row, text="Stylus Length (mm):", font=ctk.CTkFont(size=12), text_color="#b0bec5").pack(anchor="w")
        len_entry_row = ctk.CTkFrame(len_row, fg_color="transparent")
        len_entry_row.pack(fill="x", pady=(4, 0))
        self._probe_length_entry = ctk.CTkEntry(len_entry_row, width=90, height=28, placeholder_text="50.0", font=ctk.CTkFont(size=13))
        self._probe_length_entry.insert(0, str(self.probe_profile.stylus_length))
        self._probe_length_entry.pack(side="left")
        ctk.CTkLabel(len_entry_row, text="mm", font=ctk.CTkFont(size=11), text_color="#78909c").pack(side="left", padx=(6, 0))

        tip_row = ctk.CTkFrame(self._probe_body, fg_color="transparent")
        tip_row.pack(fill="x", padx=14, pady=(6, 4))
        ctk.CTkLabel(tip_row, text="Tip Diameter ⌀ (mm):", font=ctk.CTkFont(size=12), text_color="#b0bec5").pack(anchor="w")
        tip_entry_row = ctk.CTkFrame(tip_row, fg_color="transparent")
        tip_entry_row.pack(fill="x", pady=(4, 0))
        self._probe_tip_entry = ctk.CTkEntry(tip_entry_row, width=90, height=28, placeholder_text="2.0", font=ctk.CTkFont(size=13))
        self._probe_tip_entry.insert(0, str(self.probe_profile.tip_diameter))
        self._probe_tip_entry.pack(side="left")
        ctk.CTkLabel(tip_entry_row, text="mm", font=ctk.CTkFont(size=11), text_color="#78909c").pack(side="left", padx=(6, 0))

        ctk.CTkFrame(self._probe_body, height=1, fg_color="#2a2a4e").pack(fill="x", padx=14, pady=(10, 6))

        self._btn_apply_probe = ctk.CTkButton(
            self._probe_body, text="✔ Apply Profile",
            fg_color="#1565c0", hover_color="#1976d2",
            font=ctk.CTkFont(size=12, weight="bold"), height=30,
            command=self._apply_probe_profile)
        self._btn_apply_probe.pack(fill="x", padx=14, pady=(0, 6))

        self._btn_reset_probe = ctk.CTkButton(
            self._probe_body, text="↺ Reset to Default",
            fg_color="#37474f", hover_color="#546e7a",
            font=ctk.CTkFont(size=11), height=26,
            command=self._reset_probe_profile)
        self._btn_reset_probe.pack(fill="x", padx=14, pady=(0, 10))

        self._lbl_probe_summary = ctk.CTkLabel(
            self._probe_body, text=self._probe_summary_text(),
            font=ctk.CTkFont(size=10), text_color="#546e7a", justify="left")
        self._lbl_probe_summary.pack(anchor="w", padx=14, pady=(0, 10))

    def _toggle_probe_panel(self):
        self._probe_panel_expanded = not self._probe_panel_expanded
        if self._probe_panel_expanded:
            self._probe_body.pack(pady=(0, 10), padx=12, fill="x")
            self._probe_toggle_btn.configure(text="🔩 Probe Stylus Profile  ▾")
        else:
            self._probe_body.pack_forget()
            self._probe_toggle_btn.configure(text="🔩 Probe Stylus Profile  ▸")

    def _probe_summary_text(self) -> str:
        return (f"  Length : {self.probe_profile.stylus_length:.1f} mm\n"
                f"  Tip ⌀  : {self.probe_profile.tip_diameter:.1f} mm  (r = {self.probe_profile.tip_radius:.2f} mm)")

    def _apply_probe_profile(self):
        try:
            new_length = float(self._probe_length_entry.get().strip())
            if new_length <= 0: raise ValueError("ความยาวต้องมากกว่า 0")
            new_tip_d = float(self._probe_tip_entry.get().strip())
            if new_tip_d <= 0: raise ValueError("เส้นผ่าศูนย์กลางต้องมากกว่า 0")
        except ValueError as e:
            _mb.showerror("Invalid Input", f"Profile ไม่ถูกต้อง:\n{e}")
            return

        self.probe_profile.stylus_length = new_length
        self.probe_profile.tip_diameter  = new_tip_d
        self._lbl_probe_summary.configure(text=self._probe_summary_text())
        if self.holes_detected and self.current_holes:
            self.update_treeview(self.current_holes)

    def _reset_probe_profile(self):
        self.probe_profile.stylus_length = self.probe_profile.DEFAULT_LENGTH
        self.probe_profile.tip_diameter  = self.probe_profile.DEFAULT_TIP_D
        self._probe_length_entry.delete(0, "end")
        self._probe_length_entry.insert(0, str(self.probe_profile.stylus_length))
        self._probe_tip_entry.delete(0, "end")
        self._probe_tip_entry.insert(0, str(self.probe_profile.tip_diameter))
        self._lbl_probe_summary.configure(text=self._probe_summary_text())
        if self.holes_detected and self.current_holes:
            self.update_treeview(self.current_holes)

    def _setup_right_sidebar(self):
        header_frame = ctk.CTkFrame(self.sidebar_right, fg_color="transparent")
        header_frame.pack(pady=(20, 4), padx=20, fill="x")

        self.right_header = ctk.CTkLabel(header_frame, text="Detected Holes", font=ctk.CTkFont(size=16, weight="bold"))
        self.right_header.pack(side="left")

        self.lbl_selected_count = ctk.CTkLabel(header_frame, text="", font=ctk.CTkFont(size=11), text_color="#3694ED")
        self.lbl_selected_count.pack(side="right")

        self.holes_list_frame = ctk.CTkScrollableFrame(self.sidebar_right, fg_color="transparent")
        self.holes_list_frame.pack(fill="both", expand=True, padx=10, pady=5)

    def _refresh_selected_count_label(self):
        count = len(self.inspection_selected_holes)
        self.lbl_selected_count.configure(text=f"✅ {count} selected" if count > 0 else "")

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
        if selected_tab == "Customization":
            if not self.holes_detected or len(self.current_holes) == 0:
                _mb.showwarning("ไม่พบรูในโมเดล", "กรุณากด 'Generate Holes' และตรวจสอบให้แน่ใจว่ามีรูถูกตรวจพบก่อน")
                self.nav_selector.set(self.current_tab)
                return

        self.selection_tab.clear_pins()
        self.current_tab = selected_tab
        self.sidebar_right.pack(side="right", fill="y", before=self.center_frame)

        if selected_tab == "Customization":
            self.btn_reset.configure(state="disabled")
        else:
            self.btn_reset.configure(state="normal" if self.geo.mesh is not None else "disabled")

        if selected_tab == "Selection":
            self.fig.clf()
            self.ax  = self.fig.add_subplot(111, facecolor='#1e1e1e')
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
            title="Select STEP/STP CAD Model", filetypes=[("STEP Files", "*.stp *.step")])
        if not filepath: return
        self.selection_tab.clear_pins()
        try:
            self.geo.load_file(filepath)
        except ValueError as e:
            _mb.showerror("Unsupported File", str(e))
            return

        self.screen_rotation   = 0
        self.holes_detected    = False
        self.current_holes     = []
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
        if view_name != self.current_view: self.selection_tab.clear_pins()
        self.current_view = view_name
        rot = self.screen_rotation

        if   view_name == 'Top':    x, y, z_v, z_f, tri = self.geo.get_top_view(rot)
        elif view_name == 'Bottom': x, y, z_v, z_f, tri = self.geo.get_bottom_view(rot)
        elif view_name == 'Front':  x, y, z_v, z_f, tri = self.geo.get_front_view(rot)
        elif view_name == 'Back':   x, y, z_v, z_f, tri = self.geo.get_back_view(rot)
        elif view_name == 'Left':   x, y, z_v, z_f, tri = self.geo.get_left_view(rot)
        elif view_name == 'Right':  x, y, z_v, z_f, tri = self.geo.get_right_view(rot)

        if self.holes_detected:
            prev_states = {}
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
                step_holes = self.geo.get_step_holes_in_view(view_name, rot)
                converted  = []
                for i, sh in enumerate(step_holes):
                    hf = HoleFeature(
                        hid=i + 1, x=sh.display_x, y=sh.display_y,
                        surface_z=sh.depth_top, bottom_z=sh.depth_bot, depth=sh.depth, radius=sh.radius
                    )
                    hf.hole_top_z = sh.depth_top
                    hf._step_hole = sh
                    hf.is_rejected      = getattr(sh, 'is_rejected', False)
                    hf.reject_reason    = getattr(sh, 'reject_reason', "")
                    hf.position_unknown = getattr(sh, 'position_unknown', False)
                    converted.append(hf)
                self.current_holes = converted
            else:
                visible_vert_idx   = np.unique(tri.ravel())
                self.current_holes = self.selection_tab.detect_holes_in_view(
                    x[visible_vert_idx], y[visible_vert_idx], z_v[visible_vert_idx], view_name)

            if len(self.current_holes) == 0:
                _mb.showinfo("No Holes", f"ไม่พบรูในมุมมอง {view_name}")

            for h in self.current_holes:
                state = prev_states.get(h.id)
                if state is not None:
                    h.selected_for_inspection = state.get('selected', False)
                    h.zigzag_inspection       = state.get('zigzag', False)
                    h.zigzag_degree           = state.get('zigzag_deg', 45.0)
                    h.layers                  = state.get('layers', 3)
                    h.points_per_layer        = state.get('points', 4)
                else:
                    h.selected_for_inspection = not getattr(h, 'is_rejected', False)
                    h.zigzag_inspection       = False
                    h.zigzag_degree           = 45.0
                    h.layers                  = 3
                    h.points_per_layer        = 4

            self.inspection_selected_holes = [i for i, h in enumerate(self.current_holes) if h.selected_for_inspection]
        else:
            self.current_holes = []

        self._renumber_holes_by_category()

        visible_holes = []
        self._visible_hole_map = {}
        for gi, h in enumerate(self.current_holes):
            if (getattr(h, 'selected_for_inspection', False) and h.x is not None and h.y is not None):
                self._visible_hole_map[gi] = len(visible_holes)
                visible_holes.append(h)

        title = f"{view_name} View"
        self.selection_tab.update_plot(x, y, z_v, z_f, tri, title, holes=visible_holes)
        self.update_treeview(self.current_holes)

    def on_generate_holes(self):
        if self.geo.mesh is None: return
        rot = self.screen_rotation
        view_name = self.current_view
        has_step = (hasattr(self.geo, 'step_data') and self.geo.step_data is not None)

        if has_step:
            candidate_holes = self.geo.get_step_holes_in_view(view_name, rot)
        else:
            if   view_name == 'Top':    x, y, z_v, z_f, tri = self.geo.get_top_view(rot)
            elif view_name == 'Bottom': x, y, z_v, z_f, tri = self.geo.get_bottom_view(rot)
            elif view_name == 'Front':  x, y, z_v, z_f, tri = self.geo.get_front_view(rot)
            elif view_name == 'Back':   x, y, z_v, z_f, tri = self.geo.get_back_view(rot)
            elif view_name == 'Left':   x, y, z_v, z_f, tri = self.geo.get_left_view(rot)
            elif view_name == 'Right':  x, y, z_v, z_f, tri = self.geo.get_right_view(rot)
            visible_vert_idx = np.unique(tri.ravel())
            candidate_holes  = self.selection_tab.detect_holes_in_view(
                x[visible_vert_idx], y[visible_vert_idx], z_v[visible_vert_idx], view_name)

        if len(candidate_holes) == 0:
            _mb.showinfo("No Holes Found", f"ไม่พบรูในมุมมอง {view_name}\nลองเปลี่ยน View หรือหมุนโมเดลแล้วลองใหม่อีกครั้ง")
            return

        self.holes_detected = True
        self._set_view_controls_locked(True)
        if self.current_tab == "Selection":
            saved_pins = list(self.selection_tab._pinned_pin_data)
            self.show_view(self.current_view)
            self.selection_tab._restore_pins(saved_pins)

    def on_clear_holes(self):
        self.holes_detected    = False
        self.current_holes     = []
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
        if self.geo.mesh is None or self.current_tab != "Selection": return
        saved_pins = list(self.selection_tab._pinned_pin_data)
        self.show_view(self.current_view)
        self.selection_tab._restore_pins(saved_pins)

    # ---------------------------------------------------------
    # Hole Settings UI (Right Sidebar)
    # ---------------------------------------------------------
    def update_treeview(self, holes):
        for widget in self.holes_list_frame.winfo_children():
            widget.destroy()

        self.hole_widgets = {} # Reset widget references

        # 1. ปุ่ม Apply Selection สำหรับอัปเดตและแยกหมวดหมู่รูใหม่
        apply_btn = ctk.CTkButton(
            self.holes_list_frame,
            text="✅ Apply Selection",
            fg_color="#2E7D32", hover_color="#1B5E20", 
            font=("", 14, "bold"),
            command=self._refresh_after_inspection_toggle
        )
        apply_btn.pack(fill="x", padx=10, pady=(10, 15))

        selected = [h for h in holes if h.selected_for_inspection]
        unselected = [h for h in holes if not h.selected_for_inspection]

        # 🟢 Selected Holes Section
        lbl_sel = ctk.CTkLabel(self.holes_list_frame, text=f"🟢 Selected Holes ({len(selected)})", font=("", 14, "bold"), text_color="#66bb6a")
        lbl_sel.pack(anchor="w", padx=10, pady=(5, 5))

        for h in selected:
            idx = self.current_holes.index(h)
            self._build_selected_item(self.holes_list_frame, idx, h)

        # ⚪ Unselected Holes Section
        lbl_unsel = ctk.CTkLabel(self.holes_list_frame, text=f"⚪ Unselected Holes ({len(unselected)})", font=("", 14, "bold"), text_color="#9aa4b2")
        lbl_unsel.pack(anchor="w", padx=10, pady=(20, 5))

        for h in unselected:
            idx = self.current_holes.index(h)
            self._build_unselected_item(self.holes_list_frame, idx, h)

    def _bind_hover_recursive(self, widget, on_enter, on_leave):
        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)
        for child in widget.winfo_children():
            self._bind_hover_recursive(child, on_enter, on_leave)

    def _build_selected_item(self, parent, idx, hole):
        if idx not in self.hole_widgets:
            self.hole_widgets[idx] = {'is_expanded': False}
        widgets = self.hole_widgets[idx]

        item_frame = ctk.CTkFrame(parent, fg_color="transparent")
        item_frame.pack(fill="x", padx=10, pady=4)

        header_row = ctk.CTkFrame(item_frame, fg_color="transparent")
        header_row.pack(fill="x")

        # กำหนดสีปุ่มถ้ากำลังถูกเลือก (Click expand)
        default_color = "#1a3a5c"
        current_color = "#1f538d" if self.selected_hole_idx == idx else default_color

        btn_text = f"🎯 Hole {hole.display_id} [X: {hole.x:.2f}, Y: {hole.y:.2f}] D: {hole.depth:.2f}"
        header_btn = ctk.CTkButton(
            header_row, text=btn_text, anchor="w", fg_color=current_color,
            command=lambda: self.on_hole_select(idx)
        )
        header_btn.pack(side="left", fill="x", expand=True, padx=(0, 10))
        widgets['btn'] = header_btn

        chk_var = ctk.BooleanVar(value=hole.selected_for_inspection)
        chk = ctk.CTkCheckBox(
            header_row, text="", width=24, variable=chk_var,
            command=lambda: self._on_inspection_select_toggle(idx, chk_var)
        )
        chk.pack(side="right")

        # Hover Effect (เชื่อมกับกราฟ)
        self._bind_hover_recursive(
            item_frame,
            lambda e, gi=idx: self.selection_tab.highlight_hole(gi),
            lambda e: self.selection_tab.clear_hole_highlight()
        )

        # ✅ แก้ไข: สร้างกล่อง Setting เตรียมไว้เสมอ (แม้จะยังไม่ได้กาง)
        setting_frame = ctk.CTkFrame(item_frame, fg_color="#1c212c", corner_radius=6)
        widgets['settings_frame'] = setting_frame

        if hasattr(self, 'probe_profile'):
            chk_res = self.probe_profile.check_hole(hole.depth, hole.radius)
            if not chk_res['ok']:
                warn_text = chk_res['depth_warning'] or chk_res['fit_warning']
                lbl_warn = ctk.CTkLabel(setting_frame, text=warn_text, text_color="#ef5350", font=("", 11, "bold"))
                lbl_warn.pack(anchor="w", padx=10, pady=(5, 0))

        # Z-Layers Dropdown
        row1 = ctk.CTkFrame(setting_frame, fg_color="transparent")
        row1.pack(fill="x", padx=10, pady=(5,0))
        ctk.CTkLabel(row1, text="Z-Layers:", text_color="#b0bec5").pack(side="left")
        opt_layers = ctk.CTkOptionMenu(row1, values=["1","2","3","4","5"], width=60, 
                                       command=lambda val: self.on_config_change_for_hole(idx))
        opt_layers.set(str(hole.layers))
        opt_layers.pack(side="right")
        widgets['opt_layers'] = opt_layers

        # Points/Layer Dropdown
        row2 = ctk.CTkFrame(setting_frame, fg_color="transparent")
        row2.pack(fill="x", padx=10, pady=(5,0))
        ctk.CTkLabel(row2, text="Points/Layer:", text_color="#b0bec5").pack(side="left")
        opt_points = ctk.CTkOptionMenu(row2, values=["4","6","8","12"], width=60,
                                       command=lambda val: self.on_config_change_for_hole(idx))
        opt_points.set(str(hole.points_per_layer))
        opt_points.pack(side="right")
        widgets['opt_points'] = opt_points

        # Zigzag checkbox
        zig_var = ctk.BooleanVar(value=hole.zigzag_inspection)
        chk_zig = ctk.CTkCheckBox(setting_frame, text="↕ Zigzag Inspection", text_color="#b0bec5", variable=zig_var,
                                  command=lambda: self._on_zigzag_toggle(idx, zig_var))
        chk_zig.pack(anchor="w", padx=10, pady=(10,5))
        widgets['chk_zigzag'] = chk_zig

        # Degree Config Frame
        df = ctk.CTkFrame(setting_frame, fg_color="transparent")
        ctk.CTkLabel(df, text="Degree/Layer:", text_color="#b0bec5").pack(side="left")
        deg_ent = ctk.CTkEntry(df, width=50)
        deg_ent.insert(0, str(hole.zigzag_degree))
        deg_ent.pack(side="left", padx=5)
        deg_ent.bind("<Return>", lambda e: self._on_zigzag_degree_change(idx))
        widgets['degree_frame'] = df
        widgets['degree_entry'] = deg_ent

        if hole.zigzag_inspection:
            df.pack(fill="x", padx=15, pady=(0, 8))

        # ✅ ถ้าสถานะมันเป็นกางอยู่ ถึงจะเอามาแสดงให้เห็น
        if widgets['is_expanded']:
            setting_frame.pack(fill="x", pady=(5, 0))

    def _build_unselected_item(self, parent, idx, hole):
        if idx not in self.hole_widgets:
            self.hole_widgets[idx] = {'is_expanded': False}
        widgets = self.hole_widgets[idx]
        
        item_frame = ctk.CTkFrame(parent, fg_color="transparent")
        item_frame.pack(fill="x", padx=10, pady=4)

        header_row = ctk.CTkFrame(item_frame, fg_color="transparent")
        header_row.pack(fill="x")

        # หน้าตาปุ่มเลียนแบบของ Selected แต่สีทึบกว่า
        btn_text = f"Hole {hole.display_id} [X: {hole.x:.2f}, Y: {hole.y:.2f}]"
        header_btn = ctk.CTkButton(
            header_row, text=btn_text, anchor="w",
            fg_color="#2a2f3a", hover_color="#3a404d", text_color="#9aa4b2",
            command=lambda: self.on_hole_select(idx) if not hole.position_unknown else None
        )
        header_btn.pack(side="left", fill="x", expand=True, padx=(0, 10))
        widgets['btn'] = header_btn

        chk_var = ctk.BooleanVar(value=hole.selected_for_inspection)
        chk = ctk.CTkCheckBox(
            header_row, text="", width=24, variable=chk_var,
            command=lambda: self._on_inspection_select_toggle(idx, chk_var)
        )
        chk.pack(side="right")

        # Hover Effect
        self._bind_hover_recursive(
            item_frame,
            lambda e, h_obj=hole: self.selection_tab.show_unselected_marker(h_obj),
            lambda e: self.selection_tab.clear_unselected_marker()
        )

        reason_text = f"⚠ {hole.reject_reason}" if hole.is_rejected else "└ Not selected for inspection"
        lbl_reason = ctk.CTkLabel(item_frame, text=reason_text, text_color="#ffb74d", font=("", 11))
        lbl_reason.pack(anchor="w", padx=10, pady=(2, 0))

    # ------------------------------------------------------------------
    # Checkbox Callbacks
    # ------------------------------------------------------------------
    def _on_inspection_select_toggle(self, idx, var):
        """รับค่า checkbox แล้วจำค่าไว้เงียบๆ ไม่ต้องกระตุกจอ รอจนกว่าจะกดปุ่ม Apply"""
        hole = self.current_holes[idx]
        hole.selected_for_inspection = var.get()

    def _renumber_holes_by_category(self):
        sel_count   = 0
        unsel_count = 0
        for h in self.current_holes:
            if getattr(h, 'selected_for_inspection', False):
                sel_count += 1
                h.display_id = sel_count
            else:
                unsel_count += 1
                h.display_id = f"U{unsel_count}"

    def _refresh_after_inspection_toggle(self):
        """กดยืนยันปุ๊บ จัดเรียงหมวดหมู่หมายเลขรูเจาะใหม่ และรีเฟรชกราฟทั้งหมด"""
        self._renumber_holes_by_category()

        visible_holes = []
        self._visible_hole_map = {}
        for gi, h in enumerate(self.current_holes):
            if getattr(h, 'selected_for_inspection', False) and h.x is not None and h.y is not None:
                self._visible_hole_map[gi] = len(visible_holes)
                visible_holes.append(h)

        if self.current_tab == "Selection":
            # สำหรับ update_plot ของ SelectionTab
            # จำเป็นต้องโยน params เก่าเข้าไป ซึ่งของเดิมไม่ได้เก็บตัวแปร current_x, current_y เอาไว้
            # เลยสั่งให้มัน render view ปัจจุบันใหม่ทับไปเลยจะปลอดภัยที่สุด
            saved_pins = list(self.selection_tab._pinned_pin_data)
            self.show_view(self.current_view)
            self.selection_tab._restore_pins(saved_pins)
            return # show_view จะไปเรียก update_treeview ให้อยู่แล้ว

        self.update_treeview(self.current_holes)

    def _on_zigzag_toggle(self, idx: int, var: ctk.BooleanVar):
        if idx >= len(self.current_holes): return
        hole = self.current_holes[idx]
        hole.zigzag_inspection = var.get()

        if idx in self.hole_widgets and 'degree_frame' in self.hole_widgets[idx]:
            df = self.hole_widgets[idx]['degree_frame']
            sf = self.hole_widgets[idx]['settings_frame']
            if hole.zigzag_inspection:
                df.pack(in_=sf, fill="x", padx=15, pady=(0, 8), after=self.hole_widgets[idx]['chk_zigzag'])
            else:
                df.pack_forget()

        if self.current_tab == "Customization" and self.selected_hole_idx == idx:
            self.customization_tab.draw_cross_section()

    def _on_zigzag_degree_change(self, idx: int):
        if idx >= len(self.current_holes) or idx not in self.hole_widgets or 'degree_entry' not in self.hole_widgets[idx]: return
        hole  = self.current_holes[idx]
        entry = self.hole_widgets[idx]['degree_entry']
        try:
            val = max(1.0, min(180.0, float(entry.get().strip())))
        except ValueError:
            val = hole.zigzag_degree

        hole.zigzag_degree = val
        entry.delete(0, "end")
        entry.insert(0, str(int(val)) if val == int(val) else str(val))

        if self.current_tab == "Customization" and self.selected_hole_idx == idx:
            self.customization_tab.draw_cross_section()

    # ------------------------------------------------------------------
    # Hole Selection / Config
    # ------------------------------------------------------------------
    def on_hole_select(self, idx):
        is_deselecting = (self.selected_hole_idx == idx)

        for i, widgets in self.hole_widgets.items():
            if 'btn' not in widgets: continue
            hole_i = self.current_holes[i] if i < len(self.current_holes) else None
            default_color = "#1a3a5c" if (hole_i and hole_i.selected_for_inspection) else "#1f1f1f"
            widgets['btn'].configure(fg_color=default_color)
            
            # ซ่อนเมนูรูอื่นที่ไม่ได้ถูกเลือก
            if widgets.get('is_expanded') and i != idx:
                if 'settings_frame' in widgets:
                    widgets['settings_frame'].pack_forget()
                widgets['is_expanded'] = False

        if idx not in self.hole_widgets or 'btn' not in self.hole_widgets[idx]: return

        if is_deselecting:
            sel = self.hole_widgets[idx]
            if sel.get('is_expanded'):
                if 'settings_frame' in sel:
                    sel['settings_frame'].pack_forget()
                sel['is_expanded'] = False
            self.selected_hole_idx = None
        else:
            sel = self.hole_widgets[idx]
            sel['btn'].configure(fg_color="#1f538d")
            if not sel.get('is_expanded'):
                if 'settings_frame' in sel:
                    sel['settings_frame'].pack(fill="x", pady=(5, 0))
                sel['is_expanded'] = True
            self.selected_hole_idx = idx

        # อัปเดตไฮไลต์กราฟ 2D/3D
        if self.current_tab == "Selection" and hasattr(self, 'scatter_holes') and self.scatter_holes:
            colors = ['white'] * len(self._visible_hole_map)
            if self.selected_hole_idx is not None:
                local_idx = self._visible_hole_map.get(self.selected_hole_idx)
                if local_idx is not None and local_idx < len(colors):
                    colors[local_idx] = 'yellow'
            self.scatter_holes.set_facecolors(colors)
            self.canvas.draw_idle()
        elif self.current_tab == "Customization":
            self.customization_tab.draw_cross_section()
        elif self.current_tab == "Path Mapper":
            self.path_mapper_tab.draw_path_mapper()

    def on_config_change_for_hole(self, idx):
        if idx >= len(self.current_holes): return
        hole    = self.current_holes[idx]
        widgets = self.hole_widgets[idx]
        hole.layers           = int(widgets['opt_layers'].get())
        hole.points_per_layer = int(widgets['opt_points'].get())
        if self.current_tab == "Path Mapper":
            self.path_mapper_tab.draw_path_mapper()
        elif self.current_tab == "Customization":
            self.customization_tab.draw_cross_section()

    def get_holes_for_inspection(self) -> list:
        return [self.current_holes[i] for i in self.inspection_selected_holes if i < len(self.current_holes)]