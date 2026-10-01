# ==============================================================================
# ui/tool_bar.py — Ribbon ด้านบนของหน้าต่าง (ปุ่มไอคอน + ข้อความ จัดเป็นกลุ่ม)
# ==============================================================================
# VERSION: 02
# CHANGE LOG (v01 -> v02):
#   เปลี่ยนจาก toolbar ไอคอนล้วนแบบ Thonny เป็น ribbon ตาม mockup "A · Metrology":
#   ปุ่มที่เคยอยู่ใน sidebar ซ้าย (Upload / Generate Holes / Clear / ปุ่มมุมมอง 6 ปุ่ม)
#   ย้ายมาอยู่ที่นี่ทั้งหมด จัดเป็นกลุ่มมีชื่อกำกับ:
#     MODEL  [Open] [Detect] [Clear]
#     VIEW   [Top Front Left / Bottom Back Right] [Rotate] [Reset]
#     SETUP  [Hardware]
#     ขวาสุด: สวิตช์ Light/Dark + ปุ่มหลัก "Export G-code"
#   handler ทุกตัวยังเป็นของ UIManager เหมือนเดิม (app.open_file_dialog,
#   app.on_generate_holes, app.on_clear_holes, app.show_view, app.rotate_screen,
#   app.reset_position) — ย้ายแค่ตำแหน่งปุ่ม
#
# attribute สาธารณะที่ ui/main_window.py ใช้ .configure(state=...):
#   btn_open, btn_detect, btn_clear, btn_rotate, btn_reset, view_buttons (dict)
# set_active_view(name) — ไฮไลต์ปุ่มมุมมองที่กำลังแสดงอยู่ (เรียกจาก show_view)
#
# ตัวแปรสำคัญที่ปรับจูนได้:
#   _RIBBON_HEIGHT    = ความสูงของ ribbon (พิกเซล)
#   _ICON_SIZE        = ขนาดไอคอนในปุ่มใหญ่ (พิกเซล)
#   _TOOLTIP_DELAY_MS = หน่วงเวลาก่อนโชว์ tooltip หลัง hover ค้าง (ms)
#   _VIEW_GRID        = ตำแหน่งปุ่มมุมมอง (ชื่อ, แถว, คอลัมน์)
# ==============================================================================
import tkinter as tk
import customtkinter as ctk

from ui import theme
from ui.icon_loader import get_icon

_RIBBON_HEIGHT    = 86
_ICON_SIZE        = 22
_TOOLTIP_DELAY_MS = 500

_VIEW_GRID = [('Top', 0, 0), ('Front', 0, 1), ('Left', 0, 2),
              ('Bottom', 1, 0), ('Back', 1, 1), ('Right', 1, 2)]


class _Tooltip:
    """Tooltip เล็ก ๆ แบบ borderless Toplevel — โผล่หลัง hover ค้าง
    _TOOLTIP_DELAY_MS แล้วหายเมื่อเมาส์ออกจากปุ่ม หรือกดปุ่ม"""

    def __init__(self, widget, text: str):
        self.widget = widget
        self.text   = text
        self._after_id   = None
        self._tip_window = None
        widget.bind("<Enter>",    self._on_enter, add="+")
        widget.bind("<Leave>",    self._on_leave, add="+")
        widget.bind("<Button-1>", self._on_leave, add="+")

    def _on_enter(self, _event=None):
        self._cancel_scheduled()
        self._after_id = self.widget.after(_TOOLTIP_DELAY_MS, self._show)

    def _on_leave(self, _event=None):
        self._cancel_scheduled()
        self._hide()

    def _cancel_scheduled(self):
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _show(self):
        if self._tip_window is not None:
            return
        try:
            x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        except Exception:
            return

        tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        try:
            tw.attributes("-topmost", True)
        except Exception:
            pass
        tk.Label(tw, text=self.text, justify="left", background=theme.c(theme.BG_CARD),
                 foreground=theme.c(theme.TEXT), relief="solid", borderwidth=1,
                 font=(theme.FONT_FAMILY, 9), padx=6, pady=2).pack()
        self._tip_window = tw

    def _hide(self):
        if self._tip_window is not None:
            try:
                self._tip_window.destroy()
            except Exception:
                pass
            self._tip_window = None


class _RibbonButton(ctk.CTkButton):
    """ปุ่มใหญ่บน ribbon (ไอคอนบน ข้อความล่าง) — ไอคอนจางลงเองเมื่อปุ่มถูก disable
    (CTkButton ปกติจางแค่ข้อความ ไอคอนยังเข้มเหมือนกดได้ ทำให้ดูไม่ออกว่าปุ่มถูกปิดอยู่)"""

    def __init__(self, master, icon_name: str, **kwargs):
        self._icon_name = icon_name
        super().__init__(master, image=get_icon(icon_name, _ICON_SIZE), **kwargs)

    def configure(self, require_redraw=False, **kwargs):
        if "state" in kwargs and "image" not in kwargs:
            color = theme.TEXT_FAINT if kwargs["state"] == "disabled" else theme.ICON
            kwargs["image"] = get_icon(self._icon_name, _ICON_SIZE, color)
        super().configure(require_redraw=require_redraw, **kwargs)


class ToolBar:
    """Ribbon บนสุดของหน้าต่าง — สร้างครั้งเดียวใน ui/main_window.py และ
    .pack() ไว้เหนือแถบแท็บ"""

    def __init__(self, app):
        self.app = app
        self.view_buttons = {}
        self._active_view = None

        self.frame = ctk.CTkFrame(app.root, fg_color=theme.BG_CARD, corner_radius=0,
                                  height=_RIBBON_HEIGHT)
        self.frame.pack_propagate(False)

        g = self._add_group("MODEL")
        self.btn_open   = self._add_big_button(g, "folder", "Open",   "Open a STEP / STP model", app.open_file_dialog)
        self.btn_detect = self._add_big_button(g, "target", "Detect", "Detect holes in this view", app.on_generate_holes)
        self.btn_clear  = self._add_big_button(g, "clear",  "Clear",  "Clear detected holes and unlock the view", app.on_clear_holes)
        self.btn_clear.configure(state="disabled")

        g = self._add_group("VIEW")
        grid = ctk.CTkFrame(g, fg_color="transparent")
        grid.pack(side="left", padx=(2, 8))
        for name, row, col in _VIEW_GRID:
            btn = ctk.CTkButton(
                grid, text=name, width=58, height=22, corner_radius=3,
                font=ctk.CTkFont(size=11), border_width=1,
                command=lambda v=name: app.show_view(v))
            btn.grid(row=row, column=col, padx=2, pady=2)
            self.view_buttons[name] = btn
        self.set_active_view(None)
        self.btn_rotate = self._add_big_button(g, "rotate", "Rotate", "Rotate the view 90\u00b0", app.rotate_screen)
        self.btn_reset  = self._add_big_button(g, "home",   "Reset",  "Reset pan / zoom", app.reset_position)

        g = self._add_group("SETUP")
        self.btn_hardware = self._add_big_button(g, "gear", "Hardware", "Probe stylus and machine settings",
                                                 self._open_hardware_setting)

        # ขวาสุด: ปุ่มหลักของโปรแกรม + สวิตช์ Light/Dark
        self.btn_export = ctk.CTkButton(
            self.frame, text="  Export G-code", image=get_icon("export", 18, theme.ON_FILL),
            compound="left", height=42, width=160, font=ctk.CTkFont(size=14, weight="bold"),
            command=self._open_gcode_export)
        self.btn_export.pack(side="right", padx=(8, 16))

        self.mode_switch = ctk.CTkSegmentedButton(
            self.frame, values=["Light", "Dark"], height=26,
            font=ctk.CTkFont(size=12), command=app.set_appearance)
        self.mode_switch.set(getattr(app, 'appearance_mode', theme.DEFAULT_MODE))
        self.mode_switch.pack(side="right", padx=8)

    # ------------------------------------------------------------------
    def pack(self, **kwargs):
        self.frame.pack(**kwargs)

    def set_active_view(self, name):
        """ไฮไลต์ปุ่มมุมมองที่กำลังแสดง (None = ยังไม่มีโมเดล ไม่ไฮไลต์ปุ่มใด)"""
        self._active_view = name
        for view, btn in self.view_buttons.items():
            on = (view == name)
            btn.configure(
                fg_color=theme.ACCENT if on else theme.BG_PANEL,
                hover_color=theme.ACCENT_HOVER if on else theme.BG_CARD_HOVER,
                border_color=theme.ACCENT if on else theme.BORDER_STRONG,
                text_color=theme.ON_FILL if on else theme.TEXT,
                text_color_disabled=theme.ON_FILL if on else theme.TEXT_FAINT)

    # ------------------------------------------------------------------
    def _add_group(self, caption: str):
        """กลุ่มปุ่ม 1 กลุ่ม: แถวปุ่มด้านบน + ชื่อกลุ่มตัวเล็กด้านล่าง + เส้นแบ่งขวา
        คืน frame แถวปุ่ม (ให้ _add_big_button ใส่ปุ่มลงไป)"""
        group = ctk.CTkFrame(self.frame, fg_color="transparent", corner_radius=0)
        group.pack(side="left", fill="y", padx=(10, 0), pady=(6, 4))
        row = ctk.CTkFrame(group, fg_color="transparent", corner_radius=0)
        row.pack(side="top", fill="both", expand=True)
        ctk.CTkLabel(group, text=caption, height=14, font=ctk.CTkFont(size=10),
                     text_color=theme.TEXT_MUTED).pack(side="bottom")
        div = ctk.CTkFrame(self.frame, fg_color=theme.BORDER, width=1, corner_radius=0)
        div.pack(side="left", fill="y", padx=(10, 0), pady=8)
        return row

    def _add_big_button(self, parent, icon_name: str, label: str, tooltip_text: str, command):
        btn = _RibbonButton(
            parent, icon_name, text=label, compound="top",
            width=62, height=52, corner_radius=4, font=ctk.CTkFont(size=11),
            fg_color="transparent", hover_color=theme.BG_CARD_HOVER,
            text_color=theme.TEXT, text_color_disabled=theme.TEXT_FAINT, command=command)
        btn.pack(side="left", padx=1)
        btn.tooltip = _Tooltip(btn, tooltip_text)   # .tooltip.text แก้ได้ภายหลัง (เช่นบอกเหตุผลที่ปุ่มถูกปิด)
        return btn

    # ------------------------------------------------------------------
    def _open_hardware_setting(self):
        self.app.hardware_setting_dialog.show()

    def _open_gcode_export(self):
        self.app.gcode_export_panel.show()
