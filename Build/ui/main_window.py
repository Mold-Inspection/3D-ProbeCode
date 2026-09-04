# ==============================================================================
# ui/main_window.py — หน้าต่างหลักของโปรแกรม (UIManager)
# ==============================================================================
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
#   self.machine_profile      = ค่าเริ่มต้นพื้นที่ทำงานเครื่อง กำหนดจริงใน core/machine_profile.py
#   _hole_tab_default_color() = สีพื้นหลังการ์ดรู (resting state) ตามระดับ warning
#                                — แดง/เหลือง/ฟ้า ปรับ hex สีได้ในฟังก์ชันนี้
# ==============================================================================
# VERSION: 14
# CHANGE LOG (v12 -> v14):
#   NOTE: the v13 that PLAN_toolbar-and-settings-dialogs_v01.md refers to
#   (icon-swap of btn_rotate/btn_reset/Probe header per
#   core/gcode_export_panel.py v04's own changelog) was not available as
#   source when this version was written — this diff is taken directly
#   against v12. That's not a problem in practice: btn_rotate, btn_reset,
#   and the entire Probe Stylus collapsible panel are REMOVED from the
#   sidebar in this version (moved to the toolbar / Hardware Setting
#   dialog), so whatever icon-swap v13 did to them is superseded here.
#
#   FEATURE (PLAN_toolbar-and-settings-dialogs_v01.md): new full-width
#   top toolbar (ui/tool_bar.py, Thonny-style, icon-only) sits above the
#   existing 3-pane row. Layout restructured: sidebar_left / center_frame
#   / sidebar_right now pack into a new self.main_body frame instead of
#   directly into self.root, with self.tool_bar packed above main_body.
#   This is purely mechanical — no behavior change to anything already
#   inside those three panes.
#
#   REMOVED from left sidebar: btn_rotate, btn_reset (now toolbar icon
#   buttons calling the SAME self.rotate_screen / self.reset_position
#   handlers — no behavior change), the entire collapsible "Probe Stylus
#   Profile" panel (_setup_probe_profile_panel/_toggle_probe_panel/
#   _probe_summary_text/_apply_probe_profile/_reset_probe_profile — moved
#   verbatim into ui/hardware_setting_dialog.py's "Probe Stylus"
#   category), and the collapsible "G-code Export" panel
#   (_setup_gcode_export_panel — core/gcode_export_panel.py v05 now opens
#   as a dialog instead of building inline into self._left_scroll).
#   Upload, Generate Holes, Clear & Unlock, and the 6 view-direction
#   buttons are untouched.
#
#   NEW: self.machine_profile = MachineProfile() — instantiated here for
#   the first time; previously core/machine_profile.py existed but had no
#   UI consumer anywhere in the app. Consumed by the new "Machine Working
#   Area" category in ui/hardware_setting_dialog.py.
#
#   NEW: self.hardware_setting_dialog (ui/hardware_setting_dialog.py) and
#   self.gcode_export_panel (core/gcode_export_panel.py v05) are now
#   instantiated directly in __init__ instead of via
#   _setup_gcode_export_panel()/inline sidebar build — both are opened by
#   self.tool_bar's icon buttons via .show().
#
#   FIX: _set_view_controls_locked() and on_nav_change() now reference
#   self.tool_bar.btn_rotate / self.tool_bar.btn_reset instead of
#   self.btn_rotate / self.btn_reset (which no longer exist on UIManager
#   — those buttons live on ToolBar now). Same enable/disable behavior,
#   just re-pointed at the new button location.
# ==============================================================================
import os
import customtkinter as ctk
import numpy as np
import tkinter.messagebox as _mb
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.colors import LinearSegmentedColormap
import matplotlib.pyplot as plt
from core.models import HoleFeature, HoleSegmentSetting, validate_segment_reachability
from core.probe_profile import ProbeProfile
from core.machine_profile import MachineProfile
from ui.tabs.selection_tab import SelectionTab
from ui.tabs.customization_tab import CustomizationTab
from ui.tabs.path_mapper_tab import PathMapperTab
from ui.tabs.evaluation_tab import EvaluationTab
from ui.evaluation_left_panel import EvaluationLeftPanel
from ui.evaluation_sidebar_panel import EvaluationSidebarPanel
from core.gcode_export_panel import GCodeExportPanel
from ui.tool_bar import ToolBar
from ui.hardware_setting_dialog import HardwareSettingDialog


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

        self.probe_profile   = ProbeProfile()
        self.machine_profile = MachineProfile()   # v14: previously unused — now consumed by hardware_setting_dialog.py
        self.inspection_selected_holes = []

        # v12: Evaluation tab state — see PLAN_evaluation-tab-openbuilds-log-comparison_v02.md
        self.loaded_step_filepath  = None   # เต็ม path ของไฟล์ STEP ที่โหลดล่าสุด (None ถ้ายังไม่โหลด)
        self.loaded_step_filename  = None   # basename อย่างเดียว — ใช้แสดงผลใน Evaluation left panel
        self.evaluation_result     = None   # dict ผลตรวจล่าสุด (ดู contract ใน ui/tabs/evaluation_tab.py)
        self.evaluation_tolerance_mm = 0.5  # ค่า tolerance เริ่มต้น (mm) — ปรับได้จาก Evaluation right sidebar
        self.last_export_snapshot  = None   # snapshot ตอน export G-code ล่าสุด — เขียนโดย core/gcode_export_panel.py

        self.selection_tab     = SelectionTab(self)
        self.customization_tab = CustomizationTab(self)
        self.path_mapper_tab   = PathMapperTab(self)
        self.evaluation_tab    = EvaluationTab(self)

        self.root = ctk.CTk()
        self.root.title("3D ProbeCode")
        self.root.geometry("1400x800")   # ขนาดหน้าต่างเริ่มต้น (กว้าง x สูง พิกเซล) — ปรับได้

        # v14: full-width toolbar (Thonny-style) pinned above the 3-pane row
        self.tool_bar = ToolBar(self)
        self.tool_bar.pack(fill="x", side="top")

        # v14: sidebar_left / center_frame / sidebar_right now live inside
        # main_body instead of directly in root — mechanical re-parent only,
        # no behavior change to what's inside each pane.
        self.main_body = ctk.CTkFrame(self.root, fg_color="transparent", corner_radius=0)
        self.main_body.pack(fill="both", expand=True, side="top")

        self.sidebar_left = ctk.CTkFrame(self.main_body, width=300, corner_radius=0)   # ความกว้าง sidebar ซ้าย — ปรับได้
        self.sidebar_left.pack(side="left", fill="y")

        self.sidebar_right = ctk.CTkFrame(self.main_body, width=430, corner_radius=0, fg_color="#181818")   # ความกว้าง sidebar ขวา — ปรับได้
        self.sidebar_right.pack_propagate(False)
        self.sidebar_right.pack(side="right", fill="y")

        self.center_frame = ctk.CTkFrame(self.main_body, corner_radius=0, fg_color="#242424")
        self.center_frame.pack(side="left", fill="both", expand=True)

        self.top_bar = ctk.CTkFrame(self.center_frame, fg_color="transparent", height=50)
        self.top_bar.pack(side="top", fill="x", padx=20, pady=(10, 0))

        self.nav_selector = ctk.CTkSegmentedButton(
            self.top_bar,
            values=["Selection", "Customization", "Path Mapper", "Evaluation"],
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

        # v14: floating dialogs opened from the toolbar (replaces the old
        # inline sidebar panels for Probe Stylus / G-code Export).
        self.hardware_setting_dialog = HardwareSettingDialog(self)
        self.gcode_export_panel      = GCodeExportPanel(self)

        # v12: Evaluation tab's own sidebars — built as siblings of the
        # normal sidebar content (self._left_scroll / self.normal_right_frame)
        # so on_nav_change() can pack_forget() one pair and pack() the other.
        # Not packed here — _show_normal_sidebars() (called at startup below)
        # leaves the normal sidebars visible by default.
        self.evaluation_left_panel    = EvaluationLeftPanel(self)
        self.evaluation_sidebar_panel = EvaluationSidebarPanel(self)

        self.evaluation_left_frame = ctk.CTkFrame(self.sidebar_left, fg_color="transparent")
        self.evaluation_left_panel.build(self.evaluation_left_frame)

        self.evaluation_right_frame = ctk.CTkFrame(self.sidebar_right, fg_color="transparent")
        self.evaluation_sidebar_panel.build(self.evaluation_right_frame)

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

        # v14: Rotate 90° / Reset Position moved to the top toolbar
        # (ui/tool_bar.py — self.tool_bar.btn_rotate / .btn_reset) —
        # same self.rotate_screen / self.reset_position handlers, no
        # behavior change, just a different button location.

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

        # v14: Probe Stylus panel + G-code Export panel removed from here —
        # moved to ui/hardware_setting_dialog.py and core/gcode_export_panel.py
        # v05 respectively, both opened from self.tool_bar as floating dialogs.

    def _setup_right_sidebar(self):
        # v12: wrapped in normal_right_frame so the whole "Detected Holes"
        # sidebar (header + list) can be pack_forget()'d as one unit and
        # swapped for self.evaluation_right_frame while on the Evaluation tab.
        self.normal_right_frame = ctk.CTkFrame(self.sidebar_right, fg_color="transparent")
        self.normal_right_frame.pack(fill="both", expand=True, padx=0, pady=0)

        header_frame = ctk.CTkFrame(self.normal_right_frame, fg_color="transparent")
        header_frame.pack(pady=(20, 4), padx=20, fill="x")

        self.right_header = ctk.CTkLabel(header_frame, text="Detected Holes", font=ctk.CTkFont(size=16, weight="bold"))
        self.right_header.pack(side="left")

        self.lbl_selected_count = ctk.CTkLabel(header_frame, text="", font=ctk.CTkFont(size=11), text_color="#3694ED")
        self.lbl_selected_count.pack(side="right")

        self.holes_list_frame = ctk.CTkScrollableFrame(self.normal_right_frame, fg_color="transparent")
        self.holes_list_frame.pack(fill="both", expand=True, padx=10, pady=5)

    def _refresh_selected_count_label(self):
        count = len(self.inspection_selected_holes)
        self.lbl_selected_count.configure(text=f"✅ {count} selected" if count > 0 else "")

    def _set_view_controls_locked(self, is_locked):
        rotate_state = "disabled" if is_locked else "normal"
        self.tool_bar.btn_rotate.configure(state=rotate_state)   # v14: was self.btn_rotate
        for btn in self.view_buttons.values(): btn.configure(state=rotate_state)
        self.tool_bar.btn_reset.configure(state="normal")        # v14: was self.btn_reset
        self.btn_detect.configure(state="disabled" if is_locked else "normal")
        self.btn_clear.configure(state="normal" if is_locked else "disabled")

    # ------------------------------------------------------------------
    # v12: sidebar swap for the Evaluation tab
    # ------------------------------------------------------------------
    def _show_normal_sidebars(self):
        """คืน sidebar ซ้าย/ขวาปกติ (Upload/Dimensions/View ซ้าย, Detected
        Holes ขวา) — เรียกทุกครั้งที่ออกจากแท็บ Evaluation"""
        if hasattr(self, 'evaluation_left_frame'):
            self.evaluation_left_frame.pack_forget()
        if hasattr(self, 'evaluation_right_frame'):
            self.evaluation_right_frame.pack_forget()
        self._left_scroll.pack(fill="both", expand=True, padx=0, pady=0)
        self.normal_right_frame.pack(fill="both", expand=True, padx=0, pady=0)

    def _show_evaluation_sidebars(self):
        """สลับ sidebar ซ้าย/ขวาเป็นชุดของแท็บ Evaluation (§4, §5 ของแผน)
        และรีเฟรชทั้งสองแผงให้ตรงกับ state ล่าสุดทุกครั้งที่เข้าแท็บนี้"""
        self._left_scroll.pack_forget()
        self.normal_right_frame.pack_forget()
        self.evaluation_left_frame.pack(fill="both", expand=True, padx=0, pady=0)
        self.evaluation_right_frame.pack(fill="both", expand=True, padx=0, pady=0)
        self.evaluation_left_panel.refresh()
        self.evaluation_sidebar_panel.refresh()

    def on_nav_change(self, selected_tab):
        if selected_tab == "Customization":
            if not self.holes_detected or len(self.current_holes) == 0:
                _mb.showwarning("ไม่พบรูในโมเดล", "กรุณากด 'Generate Holes' และตรวจสอบให้แน่ใจว่ามีรูถูกตรวจพบก่อน")
                self.nav_selector.set(self.current_tab)
                return

        if selected_tab == "Evaluation":
            if self.geo.mesh is None or self.geo.step_data is None:
                _mb.showwarning("ไม่มีไฟล์ STEP", "กรุณาโหลดไฟล์ STEP ก่อนใช้งานแท็บ Evaluation")
                self.nav_selector.set(self.current_tab)
                return
            if not self.holes_detected or len(self.current_holes) == 0:
                _mb.showwarning("ไม่พบรูในโมเดล", "กรุณากด 'Generate Holes' ก่อนใช้งานแท็บ Evaluation")
                self.nav_selector.set(self.current_tab)
                return

        self.selection_tab.clear_pins()
        self.current_tab = selected_tab
        self.sidebar_right.pack(side="right", fill="y", before=self.center_frame)

        if selected_tab in ("Customization", "Evaluation"):
            self.tool_bar.btn_reset.configure(state="disabled")   # v14: was self.btn_reset
        else:
            self.tool_bar.btn_reset.configure(state="normal" if self.geo.mesh is not None else "disabled")

        if selected_tab == "Evaluation":
            self._show_evaluation_sidebars()
        else:
            self._show_normal_sidebars()

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
        elif selected_tab == "Evaluation":
            self.evaluation_tab.draw_evaluation()

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

        self.loaded_step_filepath = filepath
        self.loaded_step_filename = os.path.basename(filepath)

        self.screen_rotation   = 0
        self.holes_detected    = False
        self.current_holes     = []
        self.selected_hole_idx = None
        self.inspection_selected_holes = []
        self.evaluation_result    = None
        self.last_export_snapshot = None
        self._set_view_controls_locked(False)
        self.nav_selector.set("Selection")
        self.on_nav_change("Selection")

        if self.geo.mesh is not None:
            extents = self.geo.get_physical_dimensions()
            self.max_physical_dim = max(extents)

        self.show_view('Top')

    def _update_dimensions_for_view(self, view_name):
        """อัปเดต Label ข้อมูลขนาดชิ้นงาน (Width, Length, Thickness) ให้สอดคล้องกับแกนในมุมมองปัจจุบัน"""
        if self.geo.mesh is None:
            return

        extents = self.geo.get_physical_dimensions()
        dx, dy, dz = extents[0], extents[1], extents[2]

        if view_name in ['Top', 'Bottom']:
            w_lbl, w_val = "X", dx
            l_lbl, l_val = "Y", dy
            t_lbl, t_val = "Z", dz
        elif view_name in ['Front', 'Back']:
            w_lbl, w_val = "X", dx
            l_lbl, l_val = "Z", dz
            t_lbl, t_val = "Y", dy
        elif view_name in ['Left', 'Right']:
            w_lbl, w_val = "Y", dy
            l_lbl, l_val = "Z", dz
            t_lbl, t_val = "X", dx
        else:
            w_lbl, w_val = "X", dx
            l_lbl, l_val = "Y", dy
            t_lbl, t_val = "Z", dz

        self.lbl_width.configure(text=f"Width ({w_lbl}): {w_val:.2f} mm", text_color="white")
        self.lbl_length.configure(text=f"Length ({l_lbl}): {l_val:.2f} mm", text_color="white")
        self.lbl_thick.configure(text=f"Thickness ({t_lbl}): {t_val:.2f} mm", text_color="white")

    def show_view(self, view_name):
        if self.geo.mesh is None: return
        if view_name != self.current_view: self.selection_tab.clear_pins()
        self.current_view = view_name
        self.selected_segment_idx = None
        rot = self.screen_rotation

        self._update_dimensions_for_view(view_name)

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
          1) แดง  — มี segment ที่ขนาดขวางกัน
          2) เหลือง — probe_profile ตรวจแล้วเข้าไม่ถึง
          3) ฟ้า (ค่าเดิม) — ไม่มี warning ใดๆ
        แก้ไข hex สี 3 ค่านี้ได้โดยตรงที่นี่"""
        segs = getattr(hole, 'segments', None) or []
        if any(getattr(seg, 'size_warning', '') for seg in segs):
            return "#b71c1c"

        if hasattr(self, 'probe_profile'):
            chk = self.probe_profile.check_hole(hole.depth, hole.radius)
            if not chk['ok']:
                return "#8a6d00"

        return "#1a3a5c"

    def _lighten_hex(self, hex_color: str, factor: float = 0.38) -> str:
        h = hex_color.lstrip('#')
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        r = int(r + (255 - r) * factor)
        g = int(g + (255 - g) * factor)
        b = int(b + (255 - b) * factor)
        return f"#{r:02x}{g:02x}{b:02x}"

    def _hole_tab_selected_color(self, hole) -> str:
        return self._lighten_hex(self._hole_tab_default_color(hole))

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

        default_color = self._hole_tab_default_color(hole)
        widgets['resting_color'] = default_color
        current_color = self._hole_tab_selected_color(hole) if self.selected_hole_idx == idx else default_color

        is_multi_seg = bool(getattr(hole, 'segments', None))
        folder_tag = f" 📂×{len(hole.segments)}" if is_multi_seg else ""
        btn_text = f"🎯 Hole {hole.display_id}{folder_tag} [X: {hole.x:.2f}, Y: {hole.y:.2f}] D: {hole.depth:.2f}"
        header_btn = ctk.CTkButton(
            header_row, text=btn_text, anchor="w", fg_color=current_color,
            hover_color=current_color,
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

        def enter_selected(e, gi=idx):
            if self.current_tab == "Selection":
                self.selection_tab.highlight_hole(gi)
            elif self.current_tab == "Customization":
                self.customization_tab.highlight_hole(gi)
            elif self.current_tab == "Path Mapper":
                self.path_mapper_tab.highlight_hole(gi)
            elif self.current_tab == "Evaluation":
                self.evaluation_tab.highlight_hole(gi)

        def leave_selected(e):
            if self.current_tab == "Selection":
                self.selection_tab.clear_hole_highlight()
            elif self.current_tab == "Customization":
                self.customization_tab.clear_hole_highlight()
            elif self.current_tab == "Path Mapper":
                self.path_mapper_tab.clear_hole_highlight()
            elif self.current_tab == "Evaluation":
                self.evaluation_tab.clear_hole_highlight()

        self._bind_hover_recursive(item_frame, enter_selected, leave_selected)

        setting_frame = ctk.CTkFrame(item_frame, fg_color="#1c212c", corner_radius=6)
        widgets['settings_frame'] = setting_frame

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
            opt_layers = ctk.CTkOptionMenu(row1, values=["1","2","3","4","5"], width=60,
                                           command=lambda val: self.on_config_change_for_hole(idx))
            opt_layers.set(str(hole.layers))
            opt_layers.pack(side="right")
            widgets['opt_layers'] = opt_layers

            row2 = ctk.CTkFrame(setting_frame, fg_color="transparent")
            row2.pack(fill="x", padx=10, pady=(5,0))
            ctk.CTkLabel(row2, text="Points/Layer:", text_color="#b0bec5").pack(side="left")
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
            fg_color="#1f1f1f", hover_color="#1f1f1f", text_color="#9aa4b2",
            command=lambda: self.on_hole_select(idx) if not hole.position_unknown else None
        )
        header_btn.pack(side="left", fill="x", expand=True, padx=(0, 10))
        widgets['btn'] = header_btn
        widgets['resting_color'] = "#1f1f1f"

        chk_var = ctk.BooleanVar(value=hole.selected_for_inspection)
        chk = ctk.CTkCheckBox(
            header_row, text="", width=24, variable=chk_var,
            command=lambda: self._on_inspection_select_toggle(idx, chk_var)
        )
        chk.pack(side="right")

        header_btn.pack(side="left", fill="x", expand=True, padx=(0, 10))
        widgets['btn'] = header_btn

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
            val = max(1.0, min(180.0, float(entry.get().strip())))
        except ValueError:
            val = hole.zigzag_degree
        hole.zigzag_degree = val
        entry.delete(0, "end")
        entry.insert(0, str(int(val)) if val == int(val) else str(val))

        if self.current_tab == "Customization" and self.selected_hole_idx == idx:
            self.customization_tab.draw_cross_section()

    def on_hole_select(self, idx):
        self.selected_segment_idx = None
        is_deselecting = (self.selected_hole_idx == idx)
        for i, widgets in self.hole_widgets.items():
            if 'btn' not in widgets: continue
            default_color = widgets.get('resting_color', "#1f1f1f")
            widgets['btn'].configure(fg_color=default_color, hover_color=default_color)
            if widgets.get('is_expanded') and i != idx:
                if 'settings_frame' in widgets:
                    widgets['settings_frame'].pack_forget()
                widgets['is_expanded'] = False

        if idx not in self.hole_widgets or 'btn' not in self.hole_widgets[idx]: return

        sel = self.hole_widgets[idx]
        if is_deselecting:
            resting_color = sel.get('resting_color', "#1f1f1f")
            sel['btn'].configure(fg_color=resting_color, hover_color=resting_color)
            if sel.get('is_expanded'):
                if 'settings_frame' in sel:
                    sel['settings_frame'].pack_forget()
                sel['is_expanded'] = False
            self.selected_hole_idx = None
        else:
            resting_color  = sel.get('resting_color', "#1f1f1f")
            selected_color = self._lighten_hex(resting_color)
            sel['btn'].configure(fg_color=selected_color, hover_color=selected_color)

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