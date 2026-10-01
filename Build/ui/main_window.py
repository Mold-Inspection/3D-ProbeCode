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
# VERSION: 19
# CHANGE LOG (v18 -> v19):
#   FIX: ขนาดชิ้นงาน (Width X / Length Y / Thickness Z) ตามการหมุนจอแล้ว —
#   หมุน 90°/270° ค่ากว้าง/ยาวสลับกัน และบอกว่าตรงกับแกนไหนของโมเดล
# CHANGE LOG (v17 -> v18):
#   FEATURE: ช่องสี่เหลี่ยม (core/models.py::StepPocket) — Hole schedule
#   คอลัมน์ "Dia" เปลี่ยนเป็น "Size" (รูกลม = เส้นผ่านศูนย์กลาง, ช่อง =
#   ยาว×กว้าง) และการ์ด Properties แสดงชนิด/ขนาด/รัศมีมุมของช่อง
# CHANGE LOG (v16 -> v17):
#   FEATURE (user request — merge-into-one-click + rename to "Schema"):
#   renamed the v16 state field to match ui/evaluation_left_panel.py v07 /
#   core/expected_points_io.py v03's "Schema" terminology:
#     self.loaded_export_record -> self.loaded_schema   # full dict from
#                                   # core/expected_points_io.py::
#                                   # load_schema_json() (points +
#                                   # settings_snapshot + metadata, all
#                                   # from one export — same shape as
#                                   # before, just renamed field/file)
#   No other change — v07 of evaluation_left_panel.py now applies a
#   loaded schema's settings_snapshot to app.current_holes immediately on
#   load (via core/evaluation_engine.py v04's apply_settings_snapshot()),
#   reusing the existing _refresh_after_inspection_toggle() below
#   unmodified for renumbering/treeview/tab-redraw — no changes needed to
#   that method or anywhere else in this file. See v16's changelog (and
#   v14's before it) for older history.
# ==============================================================================
import os
import contextlib
import threading
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
from ui.tab_strip import TabStrip
from ui.hardware_setting_dialog import HardwareSettingDialog
from core.ui_notify import UINotify
from core import user_settings
from core.work_zero import WORK_ZERO_CHOICES, DEFAULT_WORK_ZERO
from ui import theme


_LEFT_WIDTH       = 420   # ความกว้างแผง Hole schedule (ซ้าย) — ปรับได้
_RIGHT_WIDTH      = 330   # ความกว้างแผง Properties (ขวา) — ปรับได้
_RIGHT_WIDTH_EVAL = 430   # ความกว้างแผงขวาตอนอยู่แท็บ Evaluation (ตารางจุดวัดกว้างกว่า)

# คอลัมน์ของ Hole schedule — ใช้ฟอนต์ความกว้างคงที่ (theme.FONT_MONO) ให้ตรงแนวกัน
_HOLE_COLS_HEADER = f"{'#':>3} {'Size':>11} {'Depth':>8} {'X':>8} {'Y':>8}"


def _fmt_num(value) -> str:
    return f"{value:>8.2f}" if isinstance(value, (int, float)) else f"{'--':>8}"


def _hole_size_cell(hole) -> str:
    """คอลัมน์ Size (กว้าง 11): รูกลม = เส้นผ่านศูนย์กลาง, ช่องสี่เหลี่ยม = ยาว×กว้าง"""
    sh = getattr(hole, '_step_hole', None)
    if getattr(sh, 'shape', 'circle') == 'rect':
        return f"{f'{sh.half_u * 2:.1f}x{sh.half_v * 2:.1f}':>11}"
    radius = getattr(hole, 'radius', None)
    return f"{'':>3}{_fmt_num(radius * 2 if isinstance(radius, (int, float)) else None)}"


def _hole_row_text(hole) -> str:
    """ข้อความ 1 แถวของ Hole schedule (เรียงคอลัมน์ตาม _HOLE_COLS_HEADER)"""
    segs = getattr(hole, 'segments', None)
    tail = f" x{len(segs)}" if segs else ""
    return (f"{str(hole.display_id):>3} {_hole_size_cell(hole)} {_fmt_num(getattr(hole, 'depth', None))} "
            f"{_fmt_num(getattr(hole, 'x', None))} {_fmt_num(getattr(hole, 'y', None))}{tail}")


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

        # ค่าที่ผู้ใช้ตั้งไว้ครั้งก่อน (%APPDATA%\3D ProbeCode\settings.json — core/user_settings.py)
        _saved = user_settings.load()
        user_settings.apply_numbers(self.probe_profile, _saved.get('probe'),
                                    ('stylus_holder_height', 'stylus_length', 'tip_diameter', 'wall_clearance'),
                                    allow_zero=('wall_clearance',))
        user_settings.apply_numbers(self.machine_profile, _saved.get('machine'),
                                    ('x_travel', 'y_travel', 'z_travel', 'z_height'))
        self.appearance_mode = (_saved.get('appearance')
                                if _saved.get('appearance') in ("Light", "Dark") else theme.DEFAULT_MODE)
        _zero = _saved.get('work_zero')
        self.inspection_selected_holes = []

        # v12: Evaluation tab state — see PLAN_evaluation-tab-openbuilds-log-comparison_v02.md
        self.loaded_step_filepath  = None   # เต็ม path ของไฟล์ STEP ที่โหลดล่าสุด (None ถ้ายังไม่โหลด)
        self.loaded_step_filename  = None   # basename อย่างเดียว — ใช้แสดงผลใน Evaluation left panel
        self.evaluation_result     = None   # dict ผลตรวจล่าสุด (ดู contract ใน ui/tabs/evaluation_tab.py)
        self.evaluation_tolerance_mm = 0.5  # ค่า tolerance เริ่มต้น (mm) — ปรับได้จาก Evaluation right sidebar
        self.last_export_snapshot  = None   # snapshot ตอน export G-code ล่าสุด (live path) — เขียนโดย core/gcode_export_panel.py
        # จุด X0 Y0 Z0 ของ G-code (core/work_zero.py) — เลือกได้ใน G-code Export, จำข้ามการเปิดโปรแกรม
        self.work_zero = _zero if _zero in dict(WORK_ZERO_CHOICES) else DEFAULT_WORK_ZERO

        # v15: Expected Points (.json) import state
        self.loaded_expected_points        = None   # list ของ point dicts ที่โหลดมา (None = ยังไม่ได้โหลด, ใช้ live recompute จาก app.current_holes แทน)
        self.loaded_expected_points_source = None   # basename ของไฟล์ที่โหลดล่าสุด — แสดงผลใน Evaluation left panel
        self.loaded_expected_points_view   = None   # view_name จาก metadata ของไฟล์ที่โหลด (informational เท่านั้น)

        # v17: Schema (.json) state (renamed from v16's "Export Record")
        self.loaded_schema = None   # dict เต็มจาก core/expected_points_io.py::load_schema_json()
                                     # (points + settings_snapshot + metadata จาก export ครั้งเดียวกันเสมอ)
                                     # None = ยังไม่ได้โหลด schema ใด ๆ — loaded_expected_points ด้านบนจะว่างตามไปด้วย
                                     # v07 ของ ui/evaluation_left_panel.py จะเรียก apply_settings_snapshot()
                                     # ทันทีตอนโหลดสำเร็จ (แทนที่ค่าปัจจุบันทั้งหมด) ไม่ใช่แค่เก็บไว้เฉย ๆ

        self.selection_tab     = SelectionTab(self)
        self.customization_tab = CustomizationTab(self)
        self.path_mapper_tab   = PathMapperTab(self)
        self.evaluation_tab    = EvaluationTab(self)

        theme.apply(self.appearance_mode)   # ต้องมาก่อน ctk.CTk() — ตั้ง default สีของ widget ทุกตัว
        self.root = ctk.CTk()
        self.root.title("3D ProbeCode")
        self.root.geometry("1400x800")   # ขนาดหน้าต่างเริ่มต้น (กว้าง x สูง, พิกเซล) — fallback ถ้าไม่ maximize
        # การ maximize ย้ายไปทำใน show() — ดูเหตุผลที่ _maximize()

        # โครงหน้าต่าง (mockup "A · Metrology"), บนลงล่าง:
        #   ribbon (ui/tool_bar.py) → แถบแท็บ (ui/tab_strip.py) →
        #   [Hole schedule | กราฟ | Properties] → status bar
        self.tool_bar = ToolBar(self)
        self.tool_bar.pack(fill="x", side="top")
        # ปุ่มที่เคยอยู่ใน sidebar ซ้าย ตอนนี้อยู่บน ribbon — คงชื่อ attribute เดิมไว้
        self.btn_upload   = self.tool_bar.btn_open
        self.btn_detect   = self.tool_bar.btn_detect
        self.btn_clear    = self.tool_bar.btn_clear
        self.view_buttons = self.tool_bar.view_buttons
        ctk.CTkFrame(self.root, height=1, fg_color=theme.BORDER, corner_radius=0).pack(fill="x", side="top")

        self.nav_selector = TabStrip(
            self.root, values=["Selection", "Customization", "Path Mapper", "Evaluation"],
            command=self.on_nav_change)
        self.nav_selector.set("Selection")
        self.nav_selector.pack(fill="x", side="top")
        ctk.CTkFrame(self.root, height=1, fg_color=theme.BORDER, corner_radius=0).pack(fill="x", side="top")

        self._setup_status_bar()   # pack(side="bottom") ก่อน main_body เพื่อให้ติดขอบล่างเสมอ

        self.main_body = ctk.CTkFrame(self.root, fg_color="transparent", corner_radius=0)
        self.main_body.pack(fill="both", expand=True, side="top")

        self.sidebar_left = ctk.CTkFrame(self.main_body, width=_LEFT_WIDTH, corner_radius=0, fg_color=theme.BG_PANEL)
        self.sidebar_left.pack_propagate(False)
        self.sidebar_left.pack(side="left", fill="y")

        self.sidebar_right = ctk.CTkFrame(self.main_body, width=_RIGHT_WIDTH, corner_radius=0, fg_color=theme.BG_PANEL)
        self.sidebar_right.pack_propagate(False)
        self.sidebar_right.pack(side="right", fill="y")

        self.center_frame = ctk.CTkFrame(self.main_body, corner_radius=0, fg_color=theme.BG_CANVAS)
        self.center_frame.pack(side="left", fill="both", expand=True)

        theme.apply_matplotlib()   # รวม plt.style.use(...) ตามโหมด Light/Dark
        colors    = ["white", "yellow", "orange", "red"]   # สีไล่ระดับความลึก (Depth colormap) — ปรับลำดับ/เพิ่มสีได้
        self.cmap = LinearSegmentedColormap.from_list("depth_color", colors)

        self.fig = Figure(figsize=(10, 8), facecolor=theme.c(theme.PLOT_FIG))   # ขนาดพื้นที่วาดกราฟ (นิ้ว) — ปรับได้
        self.fig.tight_layout(pad=3.0)
        self.ax  = self.fig.add_subplot(111, facecolor=theme.c(theme.PLOT_AX))
        self.fig.subplots_adjust(bottom=0.1, right=0.85, left=0.1, top=0.9)
        self.cax = self.fig.add_axes([0.88, 0.15, 0.03, 0.7])

        self.drag_state = {'is_dragging': False, 'x': 0, 'y': 0, 'xlim': None, 'ylim': None}

        self.canvas        = FigureCanvasTkAgg(self.fig, master=self.center_frame)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.pack(fill=ctk.BOTH, expand=True, padx=10, pady=10)

        self.hover_text = self.ax.annotate(
            "", xy=(0, 0), xytext=(15, 15), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.3", fc=theme.c(theme.BG_PANEL), ec=theme.c(theme.BORDER_STRONG), alpha=1), visible=False
        )

        self._setup_left_sidebar()
        self._setup_right_sidebar()
        self.selection_tab.setup_events()

        # v14: floating dialogs opened from the toolbar (replaces the old
        # inline sidebar panels for Probe Stylus / G-code Export).
        self.hardware_setting_dialog = HardwareSettingDialog(self)
        self.gcode_export_panel      = GCodeExportPanel(self)
        self.notify = UINotify(self)   # v15: non-blocking toast — see core/ui_notify.py
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

    def _setup_status_bar(self):
        """แถบสถานะล่างสุด: ชื่อไฟล์ + ขนาดชิ้นงานตามแกนของมุมมองปัจจุบัน
        (lbl_width / lbl_length / lbl_thick อัปเดตโดย _update_dimensions_for_view)"""
        self.status_bar = ctk.CTkFrame(self.root, height=28, corner_radius=0, fg_color=theme.BG_PANEL)
        self.status_bar.pack_propagate(False)
        self.status_bar.pack(fill="x", side="bottom")
        ctk.CTkFrame(self.root, height=1, fg_color=theme.BORDER, corner_radius=0).pack(fill="x", side="bottom")

        font = ctk.CTkFont(size=12)
        self.lbl_file = ctk.CTkLabel(self.status_bar, text="No model loaded", text_color=theme.TEXT_MUTED, font=font)
        self.lbl_file.pack(side="left", padx=(14, 18))

        self.lbl_width = ctk.CTkLabel(self.status_bar, text="Width (X): -- mm", text_color=theme.TEXT_MUTED, font=font)
        self.lbl_width.pack(side="left", padx=(0, 18))

        self.lbl_length = ctk.CTkLabel(self.status_bar, text="Length (Y): -- mm", text_color=theme.TEXT_MUTED, font=font)
        self.lbl_length.pack(side="left", padx=(0, 18))

        self.lbl_thick = ctk.CTkLabel(self.status_bar, text="Thickness (Z): -- mm", text_color=theme.TEXT_MUTED, font=font)
        self.lbl_thick.pack(side="left", padx=(0, 18))

        ctk.CTkLabel(self.status_bar, text="Units: mm", text_color=theme.TEXT_MUTED, font=font).pack(side="right", padx=14)

        self.lbl_status = ctk.CTkLabel(self.status_bar, text="Ready", text_color=theme.TEXT_MUTED, font=font)
        self.lbl_status.pack(side="right", padx=14)

    @contextlib.contextmanager
    def _busy(self, text: str):
        """งานที่ใช้เวลานาน (โหลด STEP, ค้นหารู): เปลี่ยนเคอร์เซอร์เป็นนาฬิกาทราย +
        แสดงข้อความบน status bar ก่อนเริ่มงาน เพื่อให้รู้ว่าโปรแกรมกำลังทำงาน ไม่ได้ค้าง"""
        self.lbl_status.configure(text=text, text_color=theme.ACCENT_TEXT)
        try:
            self.root.configure(cursor="watch")
        except Exception:
            pass
        self.root.update_idletasks()   # ให้ข้อความ/เคอร์เซอร์ขึ้นจอก่อนงานหนักเริ่ม
        try:
            yield
        finally:
            try:
                self.root.configure(cursor="")
            except Exception:
                pass
            self.lbl_status.configure(text="Ready", text_color=theme.TEXT_MUTED)

    def _setup_left_sidebar(self):
        # แผงซ้าย = Hole schedule (ตารางรู) — ห่อใน _left_scroll เพื่อให้
        # pack_forget() ทั้งแผงแล้วสลับเป็น evaluation_left_frame ตอนอยู่แท็บ
        # Evaluation ได้ (ชื่อ _left_scroll คงไว้จากโครงเดิม)
        self._left_scroll = ctk.CTkFrame(self.sidebar_left, fg_color="transparent")
        self._left_scroll.pack(fill="both", expand=True, padx=0, pady=0)

        header_frame = ctk.CTkFrame(self._left_scroll, fg_color="transparent")
        header_frame.pack(pady=(12, 6), padx=14, fill="x")

        self.right_header = ctk.CTkLabel(header_frame, text="Hole schedule", font=ctk.CTkFont(size=14, weight="bold"))
        self.right_header.pack(side="left")

        self.lbl_selected_count = ctk.CTkLabel(header_frame, text="", font=ctk.CTkFont(size=12), text_color=theme.TEXT_MUTED)
        self.lbl_selected_count.pack(side="right")

        ctk.CTkFrame(self._left_scroll, height=1, fg_color=theme.BORDER, corner_radius=0).pack(fill="x")

        self.holes_list_frame = ctk.CTkScrollableFrame(self._left_scroll, fg_color="transparent")
        self.holes_list_frame.pack(fill="both", expand=True, padx=4, pady=4)

        self.lbl_holes_empty = ctk.CTkLabel(
            self.holes_list_frame, justify="left", text_color=theme.TEXT_MUTED, font=ctk.CTkFont(size=12),
            text="No holes yet.\n\n1. Open a STEP model\n2. Pick a view\n3. Press Detect")
        self.lbl_holes_empty.pack(anchor="w", padx=12, pady=12)

    def _setup_right_sidebar(self):
        # แผงขวา = Properties ของรูที่เลือกอยู่ — ห่อใน normal_right_frame เพื่อ
        # สลับเป็น evaluation_right_frame ตอนอยู่แท็บ Evaluation ได้
        # การ์ดตั้งค่าของแต่ละรู (settings_frame) ถูกสร้างไว้ใน props_body โดย
        # _build_selected_item() แล้ว pack()/pack_forget() ตอนเลือก/เลิกเลือกรู
        self.normal_right_frame = ctk.CTkFrame(self.sidebar_right, fg_color="transparent")
        self.normal_right_frame.pack(fill="both", expand=True, padx=0, pady=0)

        header_frame = ctk.CTkFrame(self.normal_right_frame, fg_color="transparent")
        header_frame.pack(pady=(12, 6), padx=14, fill="x")
        ctk.CTkLabel(header_frame, text="Properties", font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")

        ctk.CTkFrame(self.normal_right_frame, height=1, fg_color=theme.BORDER, corner_radius=0).pack(fill="x")

        ctk.CTkLabel(
            self.normal_right_frame, justify="left", anchor="w", wraplength=_RIGHT_WIDTH - 40,
            text="Click a hole in the schedule to edit its probing plan.",
            text_color=theme.TEXT_MUTED, font=ctk.CTkFont(size=12)
        ).pack(fill="x", padx=14, pady=(10, 4))

        self.props_body = ctk.CTkScrollableFrame(self.normal_right_frame, fg_color="transparent")
        self.props_body.pack(fill="both", expand=True, padx=4, pady=4)

    def _refresh_selected_count_label(self):
        count = len(self.inspection_selected_holes)
        self.lbl_selected_count.configure(text=f"{count} selected" if count > 0 else "")

    def _update_rotate_button(self):
        """Rotate ใช้ได้เฉพาะแท็บ Selection และตอนที่มุมมองยังไม่ถูกล็อก (ยังไม่ได้ Detect)
        — เมื่อใช้ไม่ได้ ปุ่มจะจางลงและ tooltip บอกเหตุผล แทนที่จะกดแล้วเงียบ"""
        btn = self.tool_bar.btn_rotate
        if getattr(self, '_view_locked', False):
            state, tip = "disabled", "Rotate is locked while holes are detected.\nPress Clear to unlock the view."
        elif self.current_tab != "Selection":
            state, tip = "disabled", "Rotate is only available on the Selection tab."
        else:
            state, tip = "normal", "Rotate the view 90\u00b0"
        btn.configure(state=state)
        btn.tooltip.text = tip

    def _set_view_controls_locked(self, is_locked):
        rotate_state = "disabled" if is_locked else "normal"
        self._view_locked = is_locked
        self._update_rotate_button()
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
        self.sidebar_right.configure(width=_RIGHT_WIDTH)
        self._left_scroll.pack(fill="both", expand=True, padx=0, pady=0)
        self.normal_right_frame.pack(fill="both", expand=True, padx=0, pady=0)

    def _show_evaluation_sidebars(self):
        """สลับ sidebar ซ้าย/ขวาเป็นชุดของแท็บ Evaluation (§4, §5 ของแผน)
        และรีเฟรชทั้งสองแผงให้ตรงกับ state ล่าสุดทุกครั้งที่เข้าแท็บนี้"""
        self._left_scroll.pack_forget()
        self.normal_right_frame.pack_forget()
        self.sidebar_right.configure(width=_RIGHT_WIDTH_EVAL)
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
        self._update_rotate_button()
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
            self.ax  = self.fig.add_subplot(111, facecolor=theme.c(theme.PLOT_AX))
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

    def _maximize(self):
        try:
            self.root.state('zoomed')   # Windows/Linux — macOS ไม่รองรับ 'zoomed'
        except Exception:
            pass   # best-effort — ไม่ให้การ maximize ล้มเหลวไปบล็อกการเปิดโปรแกรม

    def refresh_work_zero_marker(self):
        """วาดเครื่องหมาย Work zero ใหม่หลังเปลี่ยนจุด zero (G-code Export)"""
        if self.geo.mesh is None:
            return
        if self.current_tab == "Selection":
            self.selection_tab.refresh_zero_marker()
        elif self.current_tab == "Customization":
            self.customization_tab.draw_cross_section()

    def show(self):
        # FIX: ตอนเริ่ม mainloop() customtkinter จะ withdraw() แล้ว deiconify()
        # หน้าต่าง 1 รอบ (เพื่อเปลี่ยนสี title bar บน Windows) ซึ่งล้าง state
        # 'zoomed' ที่ตั้งไว้ก่อนหน้า ทำให้หน้าต่างเปิดเต็มจอแล้วหดกลับเป็น
        # 1400x800 เอง — จึงต้องสั่ง maximize หลัง mainloop เริ่มทำงานแล้ว
        self.root.after(0, self._maximize)
        self.root.after(300, self._warm_up_heavy_imports)
        self.root.mainloop()

    def _warm_up_heavy_imports(self):
        """cadquery + trimesh ถูกเลื่อนไป import ตอนใช้งานครั้งแรก (ดู core/cad_loader.py)
        เพื่อให้หน้าต่างขึ้นเร็ว — ที่นี่ import ล่วงหน้าใน thread เบื้องหลังหลังหน้าต่าง
        ขึ้นแล้ว เพื่อไม่ให้การกด Open ครั้งแรกต้องรอ import เอง"""
        def work():
            try:
                import trimesh      # noqa: F401
                import cadquery     # noqa: F401
            except Exception:
                pass
        threading.Thread(target=work, daemon=True, name="warm-up-imports").start()

    def set_appearance(self, mode):
        """สลับ Light/Dark (เรียกจากปุ่มบน ui/tool_bar.py) — widget ของ
        customtkinter เปลี่ยนสีเอง ส่วนกราฟ matplotlib ต้องวาดใหม่ทั้งหมด"""
        ctk.set_appearance_mode(mode)
        self.appearance_mode = mode
        user_settings.save_section("appearance", mode)
        theme.apply_matplotlib()
        self.fig.set_facecolor(theme.c(theme.PLOT_FIG))

        if self.geo.mesh is None:
            self.fig.clf()
            self.ax  = self.fig.add_subplot(111, facecolor=theme.c(theme.PLOT_AX))
            self.fig.subplots_adjust(bottom=0.1, right=0.85, left=0.1, top=0.9)
            self.cax = self.fig.add_axes([0.88, 0.15, 0.03, 0.7])
            self.selection_tab.setup_events()
            self.canvas.draw_idle()
            return

        saved_pins = list(self.selection_tab._pinned_pin_data) if self.current_tab == "Selection" else []
        self.on_nav_change(self.current_tab)
        if saved_pins:
            self.selection_tab._restore_pins(saved_pins)

    def open_file_dialog(self):
        filepath = ctk.filedialog.askopenfilename(
            title="Select STEP/STP CAD Model", filetypes=[("STEP Files", "*.stp *.step")])
        if not filepath: return
        with self._busy("Loading model…"):
            self._load_model(filepath)

    def _load_model(self, filepath):
        self.selection_tab.clear_pins()
        try:
            self.geo.load_file(filepath)
        except ValueError as e:
            _mb.showerror("Unsupported File", str(e))
            return

        self.loaded_step_filepath = filepath
        self.loaded_step_filename = os.path.basename(filepath)
        self.lbl_file.configure(text=self.loaded_step_filename, text_color=theme.TEXT)

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

        # v19: ขนาดตามแกนบนจอ/บนเครื่อง (X ขวา, Y ขึ้นบนจอ, Z หนา) รวมการหมุน
        # จอด้วย — เดิมไม่สนใจปุ่ม Rotate ค่ากว้าง/ยาวจึงไม่สลับกันตอนหมุน 90°
        # วงเล็บท้ายบอกว่าตรงกับแกนไหนของโมเดล
        from core.projector import view_rotation_matrix
        extents = self.geo.get_physical_dimensions()
        m = view_rotation_matrix(view_name, self.screen_rotation)
        model_axis = [int(np.argmax(np.abs(m[i]))) for i in range(3)]
        names = "XYZ"
        for lbl, title, i in ((self.lbl_width, "Width", 0), (self.lbl_length, "Length", 1),
                              (self.lbl_thick, "Thickness", 2)):
            src = model_axis[i]
            tag = f"  (model {names[src]})" if src != i else ""
            lbl.configure(text=f"{title} ({names[i]}): {extents[src]:.2f} mm{tag}",
                          text_color=theme.TEXT)

    def show_view(self, view_name):
        if self.geo.mesh is None: return
        if view_name != self.current_view: self.selection_tab.clear_pins()
        self.current_view = view_name
        self.tool_bar.set_active_view(view_name)
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
                self.notify.show(f"ไม่พบรูในมุมมอง {view_name}", severity="info")

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
        with self._busy("Detecting holes…"):
            self._generate_holes()

    def _generate_holes(self):
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
            self.notify.show(f"ไม่พบรูในมุมมอง {view_name}\nลองเปลี่ยน View หรือหมุนโมเดลแล้วลองใหม่อีกครั้ง", severity="info")
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
        # FIX: เดิมกด Rotate ในแท็บอื่นได้ — ค่ามุมหมุนเปลี่ยนจริงแต่ไม่มีอะไรวาดใหม่
        # (ดูเหมือนปุ่มไม่ทำงาน แล้วมุมมองไปเปลี่ยนเองตอนกลับมาแท็บ Selection)
        if self.current_tab != "Selection" or getattr(self, '_view_locked', False): return
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
            return theme.ERR_BG

        if hasattr(self, 'probe_profile'):
            chk = self.probe_profile.check_hole(hole.depth, hole.radius)
            if not chk['ok']:
                return theme.WARN_BG

        return theme.BG_CARD

    def _hole_tab_selected_color(self, hole) -> str:
        return theme.ROW_SELECTED

    def _hole_list_signature(self, holes) -> tuple:
        """ทุกอย่างที่มีผลต่อหน้าตาของ Hole schedule + การ์ด Properties ของรูชุดนี้
        (ข้อความแถว, การเลือก, เหตุผลที่ถูกตัดออก, ค่าตั้งค่า, segment, probe profile)
        ใช้เทียบว่ารายการที่แสดงอยู่ยังตรงกับข้อมูลหรือไม่ — ดู update_treeview()"""
        def plain(obj):
            return tuple(sorted((k, v) for k, v in vars(obj).items()
                                if isinstance(v, (int, float, str, bool, type(None)))))
        parts = [plain(self.probe_profile)]
        for h in holes:
            parts.append((
                _hole_row_text(h), bool(h.selected_for_inspection),
                bool(getattr(h, 'is_rejected', False)), getattr(h, 'reject_reason', ''),
                bool(getattr(h, 'position_unknown', False)),
                getattr(h, 'layers', None), getattr(h, 'points_per_layer', None),
                getattr(h, 'zigzag_inspection', None), getattr(h, 'zigzag_degree', None),
                tuple(plain(seg) for seg in (getattr(h, 'segments', None) or [])),
            ))
        return tuple(parts)

    def update_treeview(self, holes):
        # PERF: widget ของ customtkinter สร้างช้า (รายการ 30 รู ≈ 3 วินาที) และ
        # show_view() เรียกเมธอดนี้ทุกครั้ง แม้ข้อมูลรูไม่เปลี่ยนเลย (กลับมาแท็บ
        # Selection, สลับ Light/Dark) — ถ้ารายการที่แสดงอยู่ยังตรงกับข้อมูล ให้ใช้ของเดิม
        signature = self._hole_list_signature(holes)
        if holes and self.hole_widgets and signature == getattr(self, '_hole_list_sig', None):
            for idx, h in enumerate(self.current_holes):   # show_view สร้าง HoleFeature ชุดใหม่ทุกครั้ง
                widgets = self.hole_widgets.get(idx)
                if widgets is not None and 'hole' in widgets:
                    widgets['hole'] = h
            return
        self._hole_list_sig = signature

        for widget in self.holes_list_frame.winfo_children():
            widget.destroy()
        for widget in self.props_body.winfo_children():   # การ์ดตั้งค่าของรูชุดเก่า
            widget.destroy()

        self.hole_widgets = {}

        if not holes:
            ctk.CTkLabel(
                self.holes_list_frame, justify="left", text_color=theme.TEXT_MUTED, font=ctk.CTkFont(size=12),
                text="No holes yet.\n\n1. Open a STEP model\n2. Pick a view\n3. Press Detect"
            ).pack(anchor="w", padx=12, pady=12)
            return

        apply_btn = ctk.CTkButton(
            self.holes_list_frame, text="Apply selection",
            fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER, font=("", 13, "bold"),
            command=self._refresh_after_inspection_toggle
        )
        apply_btn.pack(fill="x", padx=8, pady=(6, 10))

        selected = [h for h in holes if h.selected_for_inspection]
        unselected = [h for h in holes if not h.selected_for_inspection]

        # หัวตาราง — ใช้ CTkButton แบบเดียวกับแถวข้อมูล เพื่อให้คอลัมน์ตรงแนวกันพอดี
        col_row = ctk.CTkFrame(self.holes_list_frame, fg_color="transparent")
        col_row.pack(fill="x", padx=8, pady=(0, 2))
        ctk.CTkButton(
            col_row, text=_HOLE_COLS_HEADER, anchor="w", height=24, hover=False,
            fg_color=theme.BG_CARD_HOVER, text_color=theme.TEXT_MUTED,
            font=ctk.CTkFont(family=theme.FONT_MONO, size=12)
        ).pack(side="left", fill="x", expand=True, padx=(0, 10))
        ctk.CTkFrame(col_row, width=24, height=24, fg_color="transparent").pack(side="right")

        lbl_sel = ctk.CTkLabel(self.holes_list_frame, text=f"Selected for inspection ({len(selected)})", font=("", 12, "bold"), text_color=theme.OK_TEXT)
        lbl_sel.pack(anchor="w", padx=10, pady=(6, 2))

        for h in selected:
            idx = self.current_holes.index(h)
            self._build_selected_item(self.holes_list_frame, idx, h)

        lbl_unsel = ctk.CTkLabel(self.holes_list_frame, text=f"Not inspected ({len(unselected)})", font=("", 12, "bold"), text_color=theme.TEXT_MUTED)
        lbl_unsel.pack(anchor="w", padx=10, pady=(14, 2))

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
            # รูที่เลือกค้างอยู่ก่อนสร้างรายการใหม่ → โชว์การ์ด Properties ของมันต่อเลย
            self.hole_widgets[idx] = {'is_expanded': self.selected_hole_idx == idx}
        widgets = self.hole_widgets[idx]

        item_frame = ctk.CTkFrame(parent, fg_color="transparent")
        item_frame.pack(fill="x", padx=8, pady=1)

        header_row = ctk.CTkFrame(item_frame, fg_color="transparent")
        header_row.pack(fill="x")

        default_color = self._hole_tab_default_color(hole)
        widgets['resting_color'] = default_color
        current_color = self._hole_tab_selected_color(hole) if self.selected_hole_idx == idx else default_color

        is_multi_seg = bool(getattr(hole, 'segments', None))
        header_btn = ctk.CTkButton(
            header_row, text=_hole_row_text(hole), anchor="w", height=28, corner_radius=4,
            fg_color=current_color, hover_color=current_color, text_color=theme.TEXT,
            font=ctk.CTkFont(family=theme.FONT_MONO, size=12),
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

        # การ์ดตั้งค่าของรูนี้ (แผง Properties ด้านขวา) สร้างแบบ lazy — ดู
        # _ensure_settings_card(): สร้างเฉพาะตอนรูถูกเลือกครั้งแรก
        widgets['hole'] = hole
        if widgets['is_expanded']:
            self._ensure_settings_card(idx)
            widgets['settings_frame'].pack(fill="x", pady=(5, 0))

    def _ensure_settings_card(self, idx):
        """สร้างการ์ดตั้งค่า (Properties) ของรู idx ถ้ายังไม่เคยสร้าง

        PERF: เดิมสร้างการ์ดของทุกรูทันทีตอนสร้างรายการ (option menu, checkbox,
        entry ของ customtkinter แต่ละตัวช้า — ราว 150 ms ต่อรู) ทั้งที่เห็นได้ทีละ
        การ์ดเดียว ตอนนี้สร้างเฉพาะของรูที่ถูกเลือก รายการรูจึงขึ้นเร็วขึ้นมาก
        โดยเฉพาะชิ้นงานที่มีรูหลายสิบรู"""
        widgets = self.hole_widgets.get(idx)
        if widgets is None or 'settings_frame' in widgets or 'hole' not in widgets:
            return
        hole = widgets['hole']
        is_multi_seg = bool(getattr(hole, 'segments', None))

        setting_frame = ctk.CTkFrame(self.props_body, fg_color=theme.BG_CARD, corner_radius=6)
        widgets['settings_frame'] = setting_frame

        ctk.CTkLabel(setting_frame, text=f"Hole {hole.display_id}", anchor="w",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(fill="x", padx=10, pady=(8, 0))
        ctk.CTkLabel(
            setting_frame, anchor="w", justify="left", text_color=theme.TEXT_MUTED,
            font=ctk.CTkFont(family=theme.FONT_MONO, size=12),
            text=(self._hole_size_lines(hole) +
                  f"Depth {hole.depth:.2f} mm\n"
                  f"X {hole.x:.2f}   Y {hole.y:.2f}")
        ).pack(fill="x", padx=10, pady=(2, 6))
        ctk.CTkFrame(setting_frame, height=1, fg_color=theme.BORDER, corner_radius=0).pack(fill="x", padx=10, pady=(0, 4))

        segs_for_warn = getattr(hole, 'segments', None) or []
        size_warnings = [seg.size_warning for seg in segs_for_warn if getattr(seg, 'size_warning', '')]
        if size_warnings:
            combined_size_warn = "\n".join(size_warnings)
            lbl_size_warn = ctk.CTkLabel(
                setting_frame, text=combined_size_warn, text_color=theme.ERR_TEXT,
                font=("", 11, "bold"), wraplength=_RIGHT_WIDTH - 70, justify="left")
            lbl_size_warn.pack(anchor="w", padx=10, pady=(5, 0))

        if hasattr(self, 'probe_profile'):
            chk_res = self.probe_profile.check_hole(hole.depth, hole.radius)
            if not chk_res['ok']:
                warn_text = chk_res['depth_warning'] or chk_res['fit_warning']
                lbl_warn = ctk.CTkLabel(setting_frame, text=warn_text, text_color=theme.WARN_TEXT, font=("", 11, "bold"),
                                        wraplength=_RIGHT_WIDTH - 70, justify="left")
                lbl_warn.pack(anchor="w", padx=10, pady=(5, 0))

        if is_multi_seg:
            widgets['segment_blocks'] = {}
            for seg_idx, cfg in enumerate(hole.segments):
                self._build_segment_block(setting_frame, idx, seg_idx, hole, cfg)
        else:
            row1 = ctk.CTkFrame(setting_frame, fg_color="transparent")
            row1.pack(fill="x", padx=10, pady=(5,0))
            ctk.CTkLabel(row1, text="Z-Layers:", text_color=theme.TEXT_SECONDARY).pack(side="left")
            opt_layers = ctk.CTkOptionMenu(row1, values=["1","2","3","4","5"], width=60,
                                           command=lambda val: self.on_config_change_for_hole(idx))
            opt_layers.set(str(hole.layers))
            opt_layers.pack(side="right")
            widgets['opt_layers'] = opt_layers

            row2 = ctk.CTkFrame(setting_frame, fg_color="transparent")
            row2.pack(fill="x", padx=10, pady=(5,0))
            ctk.CTkLabel(row2, text="Points/Layer:", text_color=theme.TEXT_SECONDARY).pack(side="left")
            opt_points = ctk.CTkOptionMenu(row2, values=["4","6","8","12"], width=60,
                                           command=lambda val: self.on_config_change_for_hole(idx))
            opt_points.set(str(hole.points_per_layer))
            opt_points.pack(side="right")
            widgets['opt_points'] = opt_points

            zig_var = ctk.BooleanVar(value=hole.zigzag_inspection)
            chk_zig = ctk.CTkCheckBox(setting_frame, text="↕ Zigzag Inspection", text_color=theme.TEXT_SECONDARY, variable=zig_var,
                                      command=lambda: self._on_zigzag_toggle(idx, zig_var))
            chk_zig.pack(anchor="w", padx=10, pady=(10,5))
            widgets['chk_zigzag'] = chk_zig

            df = ctk.CTkFrame(setting_frame, fg_color="transparent")
            ctk.CTkLabel(df, text="Degree/Layer:", text_color=theme.TEXT_SECONDARY).pack(side="left")
            deg_ent = ctk.CTkEntry(df, width=50)
            deg_ent.insert(0, str(hole.zigzag_degree))
            deg_ent.pack(side="left", padx=5)
            deg_ent.bind("<Return>", lambda e: self._on_zigzag_degree_change(idx))
            widgets['degree_frame'] = df
            widgets['degree_entry'] = deg_ent

            if hole.zigzag_inspection:
                df.pack(fill="x", padx=15, pady=(0, 8))

    @staticmethod
    def _hole_size_lines(hole) -> str:
        """บรรทัดขนาดในการ์ด Properties (v18: แยกรูกลม / ช่องสี่เหลี่ยม)"""
        sh = getattr(hole, '_step_hole', None)
        if getattr(sh, 'shape', 'circle') != 'rect':
            return f"Dia   {hole.radius * 2:.2f} mm\n"
        if sh.is_slot:
            return (f"Pocket {sh.kind_text}, R{sh.corner_radius:.2f} ends\n"
                    f"Size  {sh.half_u * 2:.2f} x {sh.half_v * 2:.2f} mm\n")
        corner = (f"R{sh.corner_radius:.2f} corners" if sh.corner_radius > 1e-6
                  else "sharp corners")
        return (f"Pocket {sh.kind_text}, {corner}\n"
                f"Size  {sh.half_u * 2:.2f} x {sh.half_v * 2:.2f} mm\n")

    def _build_segment_block(self, parent, hole_idx, seg_idx, hole, cfg):
        block = ctk.CTkFrame(parent, fg_color=theme.BG_INPUT, corner_radius=6)
        block.pack(fill="x", padx=8, pady=(8 if seg_idx == 0 else 4, 4))

        seg_header = ctk.CTkFrame(block, fg_color="transparent")
        seg_header.pack(fill="x", padx=6, pady=6)

        arrow    = "▾" if cfg.is_expanded else "▸"
        warn_tag = "  ⚠" if cfg.size_warning else ""
        label_text = (f"{arrow} Segment {seg_idx + 1}  "
                      f"⌀{cfg.radius_open*2:.1f}→⌀{cfg.radius_deep*2:.1f} mm  "
                      f"D={cfg.depth:.1f} mm{warn_tag}")
        header_fg = theme.SELECT_BG if cfg.selected_for_inspection else theme.ERR_BG

        sel_var = ctk.BooleanVar(value=cfg.selected_for_inspection)
        sel_chk = ctk.CTkCheckBox(
            seg_header, text="", width=22, variable=sel_var,
            command=lambda: self._on_segment_inspection_toggle(hole_idx, seg_idx, sel_var))
        sel_chk.pack(side="right")

        seg_btn = ctk.CTkButton(
            seg_header, text=label_text, anchor="w",
            fg_color=header_fg, hover_color=theme.BG_CARD_HOVER, text_color=theme.TEXT, font=("", 12),
            command=lambda: self._toggle_segment_expand(hole_idx, seg_idx))
        seg_btn.pack(side="left", fill="x", expand=True, padx=(0, 8))

        seg_body = ctk.CTkFrame(block, fg_color="transparent")

        if cfg.size_warning:
            lbl_seg_warn = ctk.CTkLabel(seg_body, text=cfg.size_warning, text_color=theme.ERR_TEXT,
                                        font=("", 10, "bold"), wraplength=210, justify="left")
            lbl_seg_warn.pack(anchor="w", padx=8, pady=(6, 0))

        row1 = ctk.CTkFrame(seg_body, fg_color="transparent")
        row1.pack(fill="x", padx=8, pady=(6, 0))
        ctk.CTkLabel(row1, text="Z-Layers:", text_color=theme.TEXT_SECONDARY, font=("", 11)).pack(side="left")
        opt_layers = ctk.CTkOptionMenu(row1, values=["1","2","3","4","5"], width=60,
                                       command=lambda val: self._on_segment_config_change(hole_idx, seg_idx))
        opt_layers.set(str(cfg.layers))
        opt_layers.pack(side="right")

        row2 = ctk.CTkFrame(seg_body, fg_color="transparent")
        row2.pack(fill="x", padx=8, pady=(4, 0))
        ctk.CTkLabel(row2, text="Points/Layer:", text_color=theme.TEXT_SECONDARY, font=("", 11)).pack(side="left")
        opt_points = ctk.CTkOptionMenu(row2, values=["4","6","8","12"], width=60,
                                       command=lambda val: self._on_segment_config_change(hole_idx, seg_idx))
        opt_points.set(str(cfg.points_per_layer))
        opt_points.pack(side="right")

        zig_var = ctk.BooleanVar(value=cfg.zigzag_inspection)
        chk_zig = ctk.CTkCheckBox(seg_body, text="↕ Zigzag Inspection", text_color=theme.TEXT_SECONDARY, font=("", 11),
                                  variable=zig_var,
                                  command=lambda: self._on_segment_zigzag_toggle(hole_idx, seg_idx, zig_var))
        chk_zig.pack(anchor="w", padx=8, pady=(8, 4))

        deg_row = ctk.CTkFrame(seg_body, fg_color="transparent")
        ctk.CTkLabel(deg_row, text="Degree/Layer:", text_color=theme.TEXT_SECONDARY, font=("", 11)).pack(side="left")
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
        blk['btn'].configure(fg_color=theme.SELECT_BG if cfg.selected_for_inspection else theme.ERR_BG)

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
        item_frame.pack(fill="x", padx=8, pady=1)

        header_row = ctk.CTkFrame(item_frame, fg_color="transparent")
        header_row.pack(fill="x")

        header_btn = ctk.CTkButton(
            header_row, text=_hole_row_text(hole), anchor="w", height=28, corner_radius=4,
            fg_color=theme.BG_CARD, hover_color=theme.BG_CARD, text_color=theme.TEXT_MUTED,
            font=ctk.CTkFont(family=theme.FONT_MONO, size=12),
            command=lambda: self.on_hole_select(idx) if not hole.position_unknown else None
        )
        header_btn.pack(side="left", fill="x", expand=True, padx=(0, 10))
        widgets['btn'] = header_btn
        widgets['resting_color'] = theme.BG_CARD

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
        lbl_reason = ctk.CTkLabel(item_frame, text=reason_text, text_color=theme.WARN_TEXT, font=("", 11))
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
            default_color = widgets.get('resting_color', theme.BG_CARD)
            widgets['btn'].configure(fg_color=default_color, hover_color=default_color)
            if widgets.get('is_expanded') and i != idx:
                if 'settings_frame' in widgets:
                    widgets['settings_frame'].pack_forget()
                widgets['is_expanded'] = False

        if idx not in self.hole_widgets or 'btn' not in self.hole_widgets[idx]: return

        sel = self.hole_widgets[idx]
        if is_deselecting:
            resting_color = sel.get('resting_color', theme.BG_CARD)
            sel['btn'].configure(fg_color=resting_color, hover_color=resting_color)
            if sel.get('is_expanded'):
                if 'settings_frame' in sel:
                    sel['settings_frame'].pack_forget()
                sel['is_expanded'] = False
            self.selected_hole_idx = None
        else:
            resting_color  = sel.get('resting_color', theme.BG_CARD)
            selected_color = theme.ROW_SELECTED
            sel['btn'].configure(fg_color=selected_color, hover_color=selected_color)

            if not sel.get('is_expanded'):
                self._ensure_settings_card(idx)
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
            self.selection_tab.refresh_overlay()   # blit เฉพาะวงรู ไม่ต้องวาด mesh ใหม่
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