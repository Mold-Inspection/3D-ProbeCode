# ==============================================================================
# ui/main_window.py — หน้าต่างหลักของโปรแกรม (UIManager)
# ==============================================================================
# หน้าที่หลัก: สร้างหน้าต่างโปรแกรม, Sidebar ซ้าย (ควบคุมมุมมอง/Probe Profile),
# Sidebar ขวา (รายการรูที่ตรวจพบ), และแท็บกลาง (Selection / Customization /
# Path Mapper — ไฟล์ใน ui/tabs/) รวมถึงจัดการ state ของรูทั้งหมด
# (เลือกรู, ตั้งค่า layers/points/zigzag ต่อรู, สลับมุมมอง ฯลฯ)
#
# ตัวแปรสำคัญที่ปรับจูนได้:
#   root.geometry(...)      = ขนาดหน้าต่างเริ่มต้น (กว้าง x สูง, พิกเซล)
#   sidebar_left width       = ความกว้าง Sidebar ซ้าย (แถบควบคุม)
#   sidebar_right width      = ความกว้าง Sidebar ขวา (รายการรู)
#   colors (cmap)            = สีไล่ระดับความลึกบนกราฟ 2D (ขาว→เหลือง→ส้ม→แดง)
#   self.fig = Figure(figsize=...) = ขนาดพื้นที่วาดกราฟ
#   Z-Layers options          = ตัวเลือกจำนวนชั้นตรวจสอบที่ผู้ใช้เลือกได้ใน dropdown
#   Points/Layer options      = ตัวเลือกจำนวนจุดตรวจสอบต่อชั้นที่ผู้ใช้เลือกได้
#   zigzag degree min/max      = ช่วงองศาต่อชั้นที่ยอมให้ตั้งค่า (ค่าเริ่มต้น 1–180°)
#   self.probe_profile        = ค่าเริ่มต้นหัวโพรบ กำหนดจริงใน core/probe_profile.py
#   _hole_tab_default_color() = สีพื้นหลังการ์ดรู (resting state) ตามระดับ warning
#                                — แดง/เหลือง/ฟ้า ปรับ hex สีได้ในฟังก์ชันนี้
# ==============================================================================
# VERSION: 08
# CHANGE LOG (v07 -> v08):
#   FEATURE: Hole-card warning system now has two independent signals,
#   shown together and reflected in the card's resting (unselected) tab
#   color:
#     1) SIZE warning (red) — aggregated from any segment whose
#        cfg.size_warning is set (core/models.py
#        validate_segment_reachability() — "upper segment narrower than
#        a lower one -> probe can't physically reach it"). Rendered as
#        its own red label ABOVE the existing probe-profile warning,
#        inside _build_selected_item()'s setting_frame.
#     2) PROBE warning (yellow) — the existing probe_profile.check_hole()
#        result (depth/fit). Text color changed #ef5350 -> #eed202.
#   New helper _hole_tab_default_color(hole): red (size warning present)
#   > yellow (probe warning present, no size warning) > original blue
#   (#1a3a5c, no warnings). Used both when a hole card is first built
#   (_build_selected_item) and whenever card colors are reset after a
#   selection change (on_hole_select), so the tab color always reflects
#   current warning state regardless of click history.
#
# CHANGE LOG (v06 -> v07):
#   FIX: Probe Stylus Profile dropdown (_probe_body) now pack()s with
#   after=self._probe_header_frame instead of a bare pack() — previously,
#   since the body was never packed at setup time, Tkinter appended it
#   after whichever sidebar widget was packed last at the moment of the
#   first expand (which could be the G-code Export panel's header),
#   making both dropdowns appear to open in the same spot. Now it always
#   opens directly under its own header no matter what else was toggled.
# ==============================================================================
import customtkinter as ctk
import numpy as np
import tkinter.messagebox as _mb
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.colors import LinearSegmentedColormap
import matplotlib.pyplot as plt
from core.models import HoleFeature, HoleSegmentSetting, validate_segment_reachability
from core.probe_profile import ProbeProfile
from ui.tabs.selection_tab import SelectionTab
from ui.tabs.customization_tab import CustomizationTab
from ui.tabs.path_mapper_tab import PathMapperTab
from core.gcode_export_panel import GCodeExportPanel


def _build_segment_settings(sh) -> list:
    segs = getattr(sh, 'segments', None)
    if not segs or len(segs) <= 1:
        return []
    result = [
        HoleSegmentSetting(idx, seg.radius_open, seg.radius_deep, seg.depth)
        for idx, seg in enumerate(segs)
    ]
    validate_segment_reachability(result)   # v06: auto-flag unreachable segments
    return result


class UIManager:
    def __init__(self, geometry_engine):
        self.geo = geometry_engine

        self.current_view       = 'Top'
        self.screen_rotation    = 0
        self.scatter_holes      = None
        self.current_holes_count = 0
        self.current_holes      = []
        self.holes_detected     = False

        self.current_tab        = "Selection"
        self.selected_hole_idx  = None
        self.selected_segment_idx = None   # segment ที่ถูก "isolate" ในกราฟ 3D (None = แสดงทั้งรู)
        self.max_physical_dim   = None

        self.view_buttons  = {}
        self.hole_widgets  = {}
        self._visible_hole_map  = {}

        self.probe_profile = ProbeProfile()
        self.inspection_selected_holes = []

        self.selection_tab     = SelectionTab(self)
        self.customization_tab = CustomizationTab(self)
        self.path_mapper_tab   = PathMapperTab(self)

        self.root = ctk.CTk()
        self.root.title("3D ProbeCode")
        self.root.geometry("1400x800")   # ขนาดหน้าต่างเริ่มต้น (กว้าง x สูง พิกเซล) — ปรับได้

        self.sidebar_left = ctk.CTkFrame(self.root, width=300, corner_radius=0)   # ความกว้าง sidebar ซ้าย — ปรับได้
        self.sidebar_left.pack(side="left", fill="y")

        self.sidebar_right = ctk.CTkFrame(self.root, width=430, corner_radius=0, fg_color="#181818")   # ความกว้าง sidebar ขวา — ปรับได้
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
        colors    = ["white", "yellow", "orange", "red"]   # สีไล่ระดับความลึก (Depth colormap) — ปรับลำดับ/เพิ่มสีได้
        self.cmap = LinearSegmentedColormap.from_list("depth_color", colors)

        self.fig = Figure(figsize=(10, 8), facecolor='#242424')   # ขนาดพื้นที่วาดกราฟ (นิ้ว) — ปรับได้
        self.fig.tight_layout(pad=3.0)
        self.ax  = self.fig.add_subplot(111, facecolor='#1e1e1e')
        self.fig.subplots_adjust(bottom=0.1, right=0.85, left=0.1, top=0.9)
        self.cax = self.fig.add_axes([0.88, 0.15, 0.03, 0.7])

        self.drag_state = {'is_dragging': False, 'x': 0, 'y': 0, 'xlim': None, 'ylim': None}

        self.canvas        = FigureCanvasTkAgg(self.fig, master=self.center_frame)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.pack(fill=ctk.BOTH, expand=True, padx=10, pady=10)

        self.hover_text = self.ax.annotate(
            "", xy=(0, 0), xytext=(15, 15), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.3", fc="red", ec="gray", alpha=1), visible=False
        )

        self._setup_left_sidebar()
        self._setup_right_sidebar()
        self.selection_tab.setup_events()

        if self.geo.mesh is not None:
            self.show_view('Top')

    def _setup_left_sidebar(self):
        self._left_scroll = ctk.CTkScrollableFrame(self.sidebar_left, fg_color="transparent", width=230)
        self._left_scroll.pack(fill="both", expand=True, padx=0, pady=0)

        ctk.CTkLabel(self._left_scroll, text="3D ProbeCode Control", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(20, 10))

        self.btn_upload = ctk.CTkButton(
            self._left_scroll, text="Upload STEP or STP",
            fg_color="#2e7d32", hover_color="#4caf50", command=self.open_file_dialog)
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
            fg_color="#f57c00", hover_color="#ef6c00", command=self.on_generate_holes)
        self.btn_detect.pack(pady=(10, 5), padx=20, fill="x")

        self.btn_clear = ctk.CTkButton(
            self._left_scroll, text="❌ Clear & Unlock",
            fg_color="#c62828", hover_color="#b71c1c", command=self.on_clear_holes, state="disabled")
        self.btn_clear.pack(pady=(0, 10), padx=20, fill="x")

        ctk.CTkLabel(self._left_scroll, text="--- View Controls ---", text_color="gray").pack(pady=(20, 5))

        self.btn_rotate = ctk.CTkButton(
            self._left_scroll, text="⟳ Rotate 90°",
            fg_color="#0277bd", hover_color="#039be5", command=self.rotate_screen)
        self.btn_rotate.pack(pady=10, padx=20, fill="x")

        self.btn_reset = ctk.CTkButton(
            self._left_scroll, text="⌂ Reset Position",
            fg_color="#d84315", hover_color="#bf360c", command=self.reset_position)
        self.btn_reset.pack(pady=(0, 10), padx=20, fill="x")

        view_frame = ctk.CTkFrame(self._left_scroll, fg_color="transparent")
        view_frame.pack(pady=10, padx=20, fill="x")

        # ตำแหน่งปุ่มมุมมองบน grid (ชื่อ, แถว, คอลัมน์) — ปรับ layout ปุ่มได้ที่นี่
        views = [('Top', 0, 0), ('Bottom', 0, 1), ('Front', 1, 0), ('Back', 1, 1), ('Left', 2, 0), ('Right', 2, 1)]

        for name, row, col in views:
            btn = ctk.CTkButton(
                view_frame, text=name, width=85,
                fg_color="#424242", hover_color="#616161",
                command=lambda v=name: self.show_view(v))
            btn.grid(row=row, column=col, padx=5, pady=5)
            self.view_buttons[name] = btn

        self._setup_probe_profile_panel()
        self._setup_gcode_export_panel()

    def _setup_probe_profile_panel(self):
        probe_header_frame = ctk.CTkFrame(self._left_scroll, fg_color="#1a1a2e", corner_radius=6)
        probe_header_frame.pack(pady=(18, 0), padx=12, fill="x")
        self._probe_header_frame = probe_header_frame   # v07: keep ref so dropdown can anchor after it

        self._probe_panel_expanded = False

        self._probe_toggle_btn = ctk.CTkButton(
            probe_header_frame, text="🔩 Probe Stylus Profile  ▸",
            fg_color="transparent", hover_color="#2a2a4e", anchor="w", font=ctk.CTkFont(size=13, weight="bold"),
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
            self._probe_body, text="✔ Apply Profile", fg_color="#1565c0", hover_color="#1976d2",
            font=ctk.CTkFont(size=12, weight="bold"), height=30, command=self._apply_probe_profile)
        self._btn_apply_probe.pack(fill="x", padx=14, pady=(0, 6))

        self._btn_reset_probe = ctk.CTkButton(
            self._probe_body, text="↺ Reset to Default", fg_color="#37474f", hover_color="#546e7a",
            font=ctk.CTkFont(size=11), height=26, command=self._reset_probe_profile)
        self._btn_reset_probe.pack(fill="x", padx=14, pady=(0, 10))

        self._lbl_probe_summary = ctk.CTkLabel(
            self._probe_body, text=self._probe_summary_text(), font=ctk.CTkFont(size=10), text_color="#546e7a", justify="left")
        self._lbl_probe_summary.pack(anchor="w", padx=14, pady=(0, 10))

    def _setup_gcode_export_panel(self):
        self.gcode_export_panel = GCodeExportPanel(self)
        self.gcode_export_panel.build(self._left_scroll)

    def _toggle_probe_panel(self):
        self._probe_panel_expanded = not self._probe_panel_expanded
        if self._probe_panel_expanded:
            # v07 FIX: anchor with after=self._probe_header_frame so this dropdown
            # always appears directly under ITS OWN header, regardless of what
            # else has been packed/toggled elsewhere in the sidebar since.
            self._probe_body.pack(pady=(0, 10), padx=12, fill="x", after=self._probe_header_frame)
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
        for btn in self.view_buttons.values(): btn.configure(state=rotate_state)
        self.btn_reset.configure(state="normal")
        self.btn_detect.configure(state="disabled" if is_locked else "normal")
        self.btn_clear.configure(state="normal" if is_locked else "disabled")

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
        self.selected_segment_idx = None   # เปลี่ยนมุมมอง = ตำแหน่งรูอาจขยับ ต้องเคลียร์ segment ที่ isolate ไว้
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
                    'segments':   getattr(h, 'segments', []),
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
                    hf.segments          = _build_segment_settings(sh)
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
                    old_segments = state.get('segments') or []
                    if old_segments and len(old_segments) == len(getattr(h, 'segments', [])):
                        h.segments = old_segments
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

    # ------------------------------------------------------------------
    # v08: Warning-driven tab (card) color
    # ------------------------------------------------------------------
    def _hole_tab_default_color(self, hole) -> str:
        """สีพื้นหลัง (resting state, ตอนไม่ได้เลือกอยู่) ของการ์ดรู
        เปลี่ยนไปตามระดับ warning ของรูนั้น เรียงลำดับความสำคัญ:
          1) แดง  — มี segment ที่ขนาดขวางกัน (probe เข้าไปไม่ถึง เพราะรู
             ด้านบนแคบกว่ารูด้านล่าง) — ดู core/models.py
             validate_segment_reachability()
          2) เหลือง — ไม่มีปัญหาเรื่องขนาด segment แต่ probe_profile
             ตรวจแล้วเข้าไม่ถึง (Probe too short) หรือหัวโพรบใหญ่เกินไป
             (Tip too large)
          3) ฟ้า (ค่าเดิม) — ไม่มี warning ใดๆ
        แก้ไข hex สี 3 ค่านี้ได้โดยตรงที่นี่"""
        segs = getattr(hole, 'segments', None) or []
        if any(getattr(seg, 'size_warning', '') for seg in segs):
            return "#b71c1c"   # แดง — ปัญหาเรื่องขนาดรู (bottleneck)

        if hasattr(self, 'probe_profile'):
            chk = self.probe_profile.check_hole(hole.depth, hole.radius)
            if not chk['ok']:
                return "#8a6d00"   # เหลือง (เข้ม เพื่อให้ตัวหนังสือขาวยังอ่านออก) — probe too short / tip too large

        return "#1a3a5c"   # ฟ้า (ค่าเดิม) — ไม่มี warning

    def update_treeview(self, holes):
        for widget in self.holes_list_frame.winfo_children():
            widget.destroy()

        self.hole_widgets = {}

        apply_btn = ctk.CTkButton(
            self.holes_list_frame, text="✅ Apply Selection",
            fg_color="#2E7D32", hover_color="#1B5E20", font=("", 14, "bold"),
            command=self._refresh_after_inspection_toggle
        )
        apply_btn.pack(fill="x", padx=10, pady=(10, 15))

        selected = [h for h in holes if h.selected_for_inspection]
        unselected = [h for h in holes if not h.selected_for_inspection]

        lbl_sel = ctk.CTkLabel(self.holes_list_frame, text=f"🟢 Selected Holes ({len(selected)})", font=("", 14, "bold"), text_color="#66bb6a")
        lbl_sel.pack(anchor="w", padx=10, pady=(5, 5))

        for h in selected:
            idx = self.current_holes.index(h)
            self._build_selected_item(self.holes_list_frame, idx, h)

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

        # v08: resting-state tab color now reflects this hole's current warning level
        default_color = self._hole_tab_default_color(hole)
        current_color = "#1f538d" if self.selected_hole_idx == idx else default_color

        is_multi_seg = bool(getattr(hole, 'segments', None))
        folder_tag = f" 📂×{len(hole.segments)}" if is_multi_seg else ""
        btn_text = f"🎯 Hole {hole.display_id}{folder_tag} [X: {hole.x:.2f}, Y: {hole.y:.2f}] D: {hole.depth:.2f}"
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

        # เชื่อม hover effect เข้ากับทั้งฝั่ง Selection (2D), Customization (3D)
        # และ Path Mapper (overview) — ทุกแท็บแค่ไฮไลต์ ไม่สลับหน้า
        def enter_selected(e, gi=idx):
            if self.current_tab == "Selection":
                self.selection_tab.highlight_hole(gi)
            elif self.current_tab == "Customization":
                self.customization_tab.highlight_hole(gi)
            elif self.current_tab == "Path Mapper":
                self.path_mapper_tab.highlight_hole(gi)

        def leave_selected(e):
            if self.current_tab == "Selection":
                self.selection_tab.clear_hole_highlight()
            elif self.current_tab == "Customization":
                self.customization_tab.clear_hole_highlight()
            elif self.current_tab == "Path Mapper":
                self.path_mapper_tab.clear_hole_highlight()

        self._bind_hover_recursive(item_frame, enter_selected, leave_selected)

        setting_frame = ctk.CTkFrame(item_frame, fg_color="#1c212c", corner_radius=6)
        widgets['settings_frame'] = setting_frame

        # v08: SIZE warning (segment bottleneck — upper hole narrower than
        # lower one) shown ABOVE the probe-profile warning, always in red,
        # regardless of the probe check result below it.
        segs_for_warn = getattr(hole, 'segments', None) or []
        size_warnings = [seg.size_warning for seg in segs_for_warn if getattr(seg, 'size_warning', '')]
        if size_warnings:
            combined_size_warn = "\n".join(size_warnings)
            lbl_size_warn = ctk.CTkLabel(
                setting_frame, text=combined_size_warn, text_color="#ff1744",
                font=("", 11, "bold"), wraplength=280, justify="left")
            lbl_size_warn.pack(anchor="w", padx=10, pady=(5, 0))

        if hasattr(self, 'probe_profile'):
            chk_res = self.probe_profile.check_hole(hole.depth, hole.radius)
            if not chk_res['ok']:
                warn_text = chk_res['depth_warning'] or chk_res['fit_warning']
                # สีข้อความแจ้งเตือน probe too short / tip too large — ปรับได้ที่นี่
                lbl_warn = ctk.CTkLabel(setting_frame, text=warn_text, text_color="#eed202", font=("", 11, "bold"))
                lbl_warn.pack(anchor="w", padx=10, pady=(5, 0))

        if is_multi_seg:
            widgets['segment_blocks'] = {}
            for seg_idx, cfg in enumerate(hole.segments):
                self._build_segment_block(setting_frame, idx, seg_idx, hole, cfg)
        else:
            row1 = ctk.CTkFrame(setting_frame, fg_color="transparent")
            row1.pack(fill="x", padx=10, pady=(5,0))
            ctk.CTkLabel(row1, text="Z-Layers:", text_color="#b0bec5").pack(side="left")
            # ตัวเลือกจำนวนชั้นตรวจสอบ (Z-Layers) ใน dropdown — เพิ่ม/ลดตัวเลือกได้
            opt_layers = ctk.CTkOptionMenu(row1, values=["1","2","3","4","5"], width=60, 
                                           command=lambda val: self.on_config_change_for_hole(idx))
            opt_layers.set(str(hole.layers))
            opt_layers.pack(side="right")
            widgets['opt_layers'] = opt_layers

            row2 = ctk.CTkFrame(setting_frame, fg_color="transparent")
            row2.pack(fill="x", padx=10, pady=(5,0))
            ctk.CTkLabel(row2, text="Points/Layer:", text_color="#b0bec5").pack(side="left")
            # ตัวเลือกจำนวนจุดตรวจสอบต่อชั้น ใน dropdown — เพิ่ม/ลดตัวเลือกได้
            opt_points = ctk.CTkOptionMenu(row2, values=["4","6","8","12"], width=60,
                                           command=lambda val: self.on_config_change_for_hole(idx))
            opt_points.set(str(hole.points_per_layer))
            opt_points.pack(side="right")
            widgets['opt_points'] = opt_points

            zig_var = ctk.BooleanVar(value=hole.zigzag_inspection)
            chk_zig = ctk.CTkCheckBox(setting_frame, text="↕ Zigzag Inspection", text_color="#b0bec5", variable=zig_var,
                                      command=lambda: self._on_zigzag_toggle(idx, zig_var))
            chk_zig.pack(anchor="w", padx=10, pady=(10,5))
            widgets['chk_zigzag'] = chk_zig

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

        if widgets['is_expanded']:
            setting_frame.pack(fill="x", pady=(5, 0))

    def _build_segment_block(self, parent, hole_idx, seg_idx, hole, cfg):
        block = ctk.CTkFrame(parent, fg_color="#000000", corner_radius=6)
        block.pack(fill="x", padx=8, pady=(8 if seg_idx == 0 else 4, 4))

        seg_header = ctk.CTkFrame(block, fg_color="transparent")
        seg_header.pack(fill="x", padx=6, pady=6)

        arrow    = "▾" if cfg.is_expanded else "▸"
        warn_tag = "  ⚠" if cfg.size_warning else ""
        label_text = (f"{arrow} Segment {seg_idx + 1}  "
                      f"⌀{cfg.radius_open*2:.1f}→⌀{cfg.radius_deep*2:.1f} mm  "
                      f"D={cfg.depth:.1f} mm{warn_tag}")
        header_fg = "#22283a" if cfg.selected_for_inspection else "#3a1f1f"

        # pack checkbox FIRST so it always claims its space before the
        # button's fill="x"+expand="True" eats the row (v07 fix) —
        # this is the ONLY checkbox widget created in this method
        sel_var = ctk.BooleanVar(value=cfg.selected_for_inspection)
        sel_chk = ctk.CTkCheckBox(
            seg_header, text="", width=22, variable=sel_var,
            command=lambda: self._on_segment_inspection_toggle(hole_idx, seg_idx, sel_var))
        sel_chk.pack(side="right")

        seg_btn = ctk.CTkButton(
            seg_header, text=label_text, anchor="w",
            fg_color=header_fg, hover_color="#2c3348", font=("", 12),
            command=lambda: self._toggle_segment_expand(hole_idx, seg_idx))
        seg_btn.pack(side="left", fill="x", expand=True, padx=(0, 8))

        seg_body = ctk.CTkFrame(block, fg_color="transparent")

        if cfg.size_warning:
            lbl_seg_warn = ctk.CTkLabel(seg_body, text=cfg.size_warning, text_color="#ef5350",
                                        font=("", 10, "bold"), wraplength=210, justify="left")
            lbl_seg_warn.pack(anchor="w", padx=8, pady=(6, 0))

        row1 = ctk.CTkFrame(seg_body, fg_color="transparent")
        row1.pack(fill="x", padx=8, pady=(6, 0))
        ctk.CTkLabel(row1, text="Z-Layers:", text_color="#b0bec5", font=("", 11)).pack(side="left")
        opt_layers = ctk.CTkOptionMenu(row1, values=["1","2","3","4","5"], width=60,
                                       command=lambda val: self._on_segment_config_change(hole_idx, seg_idx))
        opt_layers.set(str(cfg.layers))
        opt_layers.pack(side="right")

        row2 = ctk.CTkFrame(seg_body, fg_color="transparent")
        row2.pack(fill="x", padx=8, pady=(4, 0))
        ctk.CTkLabel(row2, text="Points/Layer:", text_color="#b0bec5", font=("", 11)).pack(side="left")
        opt_points = ctk.CTkOptionMenu(row2, values=["4","6","8","12"], width=60,
                                       command=lambda val: self._on_segment_config_change(hole_idx, seg_idx))
        opt_points.set(str(cfg.points_per_layer))
        opt_points.pack(side="right")

        zig_var = ctk.BooleanVar(value=cfg.zigzag_inspection)
        chk_zig = ctk.CTkCheckBox(seg_body, text="↕ Zigzag Inspection", text_color="#b0bec5", font=("", 11),
                                  variable=zig_var,
                                  command=lambda: self._on_segment_zigzag_toggle(hole_idx, seg_idx, zig_var))
        chk_zig.pack(anchor="w", padx=8, pady=(8, 4))

        deg_row = ctk.CTkFrame(seg_body, fg_color="transparent")
        ctk.CTkLabel(deg_row, text="Degree/Layer:", text_color="#b0bec5", font=("", 11)).pack(side="left")
        deg_ent = ctk.CTkEntry(deg_row, width=50)
        deg_ent.insert(0, str(cfg.zigzag_degree))
        deg_ent.pack(side="left", padx=5)
        deg_ent.bind("<Return>", lambda e: self._on_segment_zigzag_degree_change(hole_idx, seg_idx))

        if cfg.zigzag_inspection:
            deg_row.pack(fill="x", padx=12, pady=(0, 6))

        if cfg.is_expanded:
            seg_body.pack(fill="x", pady=(0, 6))

        self.hole_widgets[hole_idx]['segment_blocks'][seg_idx] = {
            'btn': seg_btn, 'body': seg_body, 'opt_layers': opt_layers,
            'opt_points': opt_points, 'chk_zigzag': chk_zig,
            'degree_frame': deg_row, 'degree_entry': deg_ent,
            'chk_select': sel_chk,
        }

    def _toggle_segment_expand(self, hole_idx, seg_idx):
        if hole_idx >= len(self.current_holes): return
        hole = self.current_holes[hole_idx]
        segments = getattr(hole, 'segments', None)
        if not segments or seg_idx >= len(segments): return

        now_expanding = not segments[seg_idx].is_expanded
        for i, cfg in enumerate(segments):
            cfg.is_expanded = (now_expanding and i == seg_idx)

        seg_blocks = self.hole_widgets.get(hole_idx, {}).get('segment_blocks', {})
        for i, cfg in enumerate(segments):
            blk = seg_blocks.get(i)
            if not blk: continue
            arrow    = "▾" if cfg.is_expanded else "▸"
            warn_tag = "  ⚠" if cfg.size_warning else ""
            blk['btn'].configure(text=(f"{arrow} Segment {i + 1}  "
                                        f"⌀{cfg.radius_open*2:.1f}→⌀{cfg.radius_deep*2:.1f} mm  "
                                        f"D={cfg.depth:.1f} mm{warn_tag}"))
            if cfg.is_expanded:
                blk['body'].pack(fill="x", pady=(0, 6))
            else:
                blk['body'].pack_forget()

        self.selected_segment_idx = seg_idx if now_expanding else None

        if self.current_tab == "Customization" and self.selected_hole_idx == hole_idx:
            self.customization_tab.draw_cross_section()

    def _on_segment_config_change(self, hole_idx, seg_idx):
        if hole_idx >= len(self.current_holes): return
        cfg     = self.current_holes[hole_idx].segments[seg_idx]
        widgets = self.hole_widgets[hole_idx]['segment_blocks'][seg_idx]
        cfg.layers           = int(widgets['opt_layers'].get())
        cfg.points_per_layer = int(widgets['opt_points'].get())
        if self.current_tab == "Path Mapper":
            self.path_mapper_tab.draw_path_mapper()
        elif self.current_tab == "Customization" and self.selected_hole_idx == hole_idx:
            self.customization_tab.draw_cross_section()

    def _on_segment_inspection_toggle(self, hole_idx, seg_idx, var):
        """v06: toggle segment เข้า/ออกจาก probe path (Customization/Path Mapper) และ G-code"""
        if hole_idx >= len(self.current_holes): return
        cfg = self.current_holes[hole_idx].segments[seg_idx]
        cfg.selected_for_inspection = var.get()

        blk = self.hole_widgets[hole_idx]['segment_blocks'][seg_idx]
        blk['btn'].configure(fg_color="#22283a" if cfg.selected_for_inspection else "#3a1f1f")

        if self.current_tab == "Path Mapper":
            self.path_mapper_tab.draw_path_mapper()
        elif self.current_tab == "Customization" and self.selected_hole_idx == hole_idx:
            self.customization_tab.draw_cross_section()

    def _on_segment_zigzag_toggle(self, hole_idx, seg_idx, var):
        if hole_idx >= len(self.current_holes): return
        cfg = self.current_holes[hole_idx].segments[seg_idx]
        cfg.zigzag_inspection = var.get()
        widgets = self.hole_widgets[hole_idx]['segment_blocks'][seg_idx]
        df = widgets['degree_frame']
        if cfg.zigzag_inspection:
            df.pack(fill="x", padx=12, pady=(0, 6))
        else:
            df.pack_forget()
        if self.current_tab == "Customization" and self.selected_hole_idx == hole_idx:
            self.customization_tab.draw_cross_section()

    def _on_segment_zigzag_degree_change(self, hole_idx, seg_idx):
        if hole_idx >= len(self.current_holes): return
        cfg     = self.current_holes[hole_idx].segments[seg_idx]
        widgets = self.hole_widgets[hole_idx]['segment_blocks'][seg_idx]
        entry   = widgets['degree_entry']
        try:
            # ช่วงองศาต่อชั้นที่ยอมให้ตั้งค่า Zigzag ได้ (ต่ำสุด–สูงสุด) — ปรับได้
            val = max(1.0, min(180.0, float(entry.get().strip())))
        except ValueError:
            val = cfg.zigzag_degree
        cfg.zigzag_degree = val
        entry.delete(0, "end")
        entry.insert(0, str(int(val)) if val == int(val) else str(val))
        if self.current_tab == "Customization" and self.selected_hole_idx == hole_idx:
            self.customization_tab.draw_cross_section()

    def _build_unselected_item(self, parent, idx, hole):
        if idx not in self.hole_widgets:
            self.hole_widgets[idx] = {'is_expanded': False}
        widgets = self.hole_widgets[idx]
        
        item_frame = ctk.CTkFrame(parent, fg_color="transparent")
        item_frame.pack(fill="x", padx=10, pady=4)

        header_row = ctk.CTkFrame(item_frame, fg_color="transparent")
        header_row.pack(fill="x")

        btn_text = f"Hole {hole.display_id} [X: {hole.x:.2f}, Y: {hole.y:.2f}]"
        header_btn = ctk.CTkButton(
            header_row, text=btn_text, anchor="w",
            fg_color="#2a2f3a", hover_color="#3a404d", text_color="#9aa4b2",
            command=lambda: self.on_hole_select(idx) if not hole.position_unknown else None
        )
        header_btn.pack(side="left", fill="x", expand=True, padx=(0, 10))
        widgets['btn'] = header_btn

        # v07: pack checkbox FIRST (same fix as _build_selected_item)
        chk_var = ctk.BooleanVar(value=hole.selected_for_inspection)
        chk = ctk.CTkCheckBox(
            header_row, text="", width=24, variable=chk_var,
            command=lambda: self._on_inspection_select_toggle(idx, chk_var)
        )
        chk.pack(side="right")

        header_btn.pack(side="left", fill="x", expand=True, padx=(0, 10))
        widgets['btn'] = header_btn

        # เชื่อม hover effect เข้ากับทั้งฝั่ง Selection (2D) และ Customization (3D)
        def enter_unselected(e, gi=idx, h_obj=hole):
            if self.current_tab == "Selection":
                self.selection_tab.show_unselected_marker(h_obj)
            elif self.current_tab == "Customization":
                self.customization_tab.highlight_hole(gi)

        def leave_unselected(e):
            if self.current_tab == "Selection":
                self.selection_tab.clear_unselected_marker()
            elif self.current_tab == "Customization":
                self.customization_tab.clear_hole_highlight()

        self._bind_hover_recursive(item_frame, enter_unselected, leave_unselected)

        reason_text = f"⚠ {hole.reject_reason}" if hole.is_rejected else "└ Not selected for inspection"
        lbl_reason = ctk.CTkLabel(item_frame, text=reason_text, text_color="#ffb74d", font=("", 11))
        lbl_reason.pack(anchor="w", padx=10, pady=(2, 0))

    def _on_inspection_select_toggle(self, idx, var):
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
        """หลังกดยืนยันเลือกรู: จัดเรียงหมายเลขรูใหม่ตามหมวดหมู่ แล้วรีเฟรชกราฟที่กำลังแสดงอยู่"""
        self._renumber_holes_by_category()

        visible_holes = []
        self._visible_hole_map = {}
        for gi, h in enumerate(self.current_holes):
            if getattr(h, 'selected_for_inspection', False) and h.x is not None and h.y is not None:
                self._visible_hole_map[gi] = len(visible_holes)
                visible_holes.append(h)

        if self.current_tab == "Selection":
            saved_pins = list(self.selection_tab._pinned_pin_data)
            self.show_view(self.current_view)
            self.selection_tab._restore_pins(saved_pins)
            return

        self.update_treeview(self.current_holes)

        if self.current_tab == "Customization":
            self.customization_tab.draw_cross_section()
        elif self.current_tab == "Path Mapper":
            self.path_mapper_tab.draw_path_mapper()

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
            # ช่วงองศาต่อชั้นที่ยอมให้ตั้งค่า Zigzag ได้ (ต่ำสุด–สูงสุด) — ปรับได้
            val = max(1.0, min(180.0, float(entry.get().strip())))
        except ValueError:
            val = hole.zigzag_degree
        hole.zigzag_degree = val
        entry.delete(0, "end")
        entry.insert(0, str(int(val)) if val == int(val) else str(val))

        if self.current_tab == "Customization" and self.selected_hole_idx == idx:
            self.customization_tab.draw_cross_section()

    def on_hole_select(self, idx):
        self.selected_segment_idx = None   # เลือก/ยกเลิกเลือกรูใหม่ ต้องเคลียร์ segment ที่ isolate ไว้เสมอ
        is_deselecting = (self.selected_hole_idx == idx)
        for i, widgets in self.hole_widgets.items():
            if 'btn' not in widgets: continue
            hole_i = self.current_holes[i] if i < len(self.current_holes) else None
            # v08: resting color now driven by warning level instead of a
            # single fixed blue — red (size) > yellow (probe) > blue (none)
            if hole_i is not None and hole_i.selected_for_inspection:
                default_color = self._hole_tab_default_color(hole_i)
            else:
                default_color = "#1f1f1f"
            widgets['btn'].configure(fg_color=default_color)
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
            # v05: click ไม่สลับหน้าใน Path Mapper อีกต่อไป — คง overview เดิม
            # แค่ไฮไลต์ marker ของรูที่กด (หรือเคลียร์ไฮไลต์ถ้ายกเลิกเลือก)
            if self.selected_hole_idx is not None:
                self.path_mapper_tab.highlight_hole(self.selected_hole_idx)
            else:
                self.path_mapper_tab.clear_hole_highlight()

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