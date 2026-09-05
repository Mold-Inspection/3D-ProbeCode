# ==============================================================================
# ui/tool_bar.py — Thonny-style top toolbar (icon-only, thin dividers)
# ==============================================================================
# VERSION: 01
# หน้าที่: แถบเครื่องมือแนวนอนเต็มความกว้าง ปักอยู่บนสุดของหน้าต่าง (เหนือ
# sidebar ซ้าย/กลาง/ขวา) — ปุ่มไอคอนล้วน ไม่มีพื้นหลังสี ไม่มีข้อความยาว มี
# เส้นแบ่งบาง ๆ คั่นกลุ่มปุ่มที่เกี่ยวข้องกัน (ตามแบบ Thonny) ใช้
# ui/icon_loader.py ตัวเดียวกับที่ sidebar เดิมเคยใช้
#
# กลุ่มปุ่ม:
#   [⟳ Rotate 90°] [⌂ Reset Position]  │  [⚙ Hardware Setting] [⇓ G-code Export]
# 2 ปุ่มแรกเรียก handler เดิมของ UIManager ตรง ๆ (app.rotate_screen /
# app.reset_position) — พฤติกรรมเหมือนเดิมทุกประการ แค่ย้ายตำแหน่งปุ่ม
# ปุ่มหลังเปิด floating dialog (ui/hardware_setting_dialog.py /
# core/gcode_export_panel.py v05) แทนการกาง/ยุบ panel ใน sidebar แบบเดิม
#
# btn_rotate / btn_reset ถูกเก็บเป็น attribute สาธารณะ (self.btn_rotate /
# self.btn_reset) เพราะ ui/main_window.py ยังต้อง .configure(state=...)
# ปุ่มเหล่านี้ตอนล็อก/ปลดล็อก view controls (ดู _set_view_controls_locked()
# และ on_nav_change() ใน main_window.py v14) — เดิมเป็น self.btn_rotate/
# self.btn_reset ของ UIManager เอง ตอนนี้ต้องอ้างผ่าน self.tool_bar.btn_*
#
# Hover ปุ่มใดก็ตามจะโชว์ tooltip ชื่อปุ่ม (customtkinter ไม่มี tooltip
# built-in — ใช้ _Tooltip helper เล็ก ๆ ในไฟล์นี้เอง เป็น borderless
# Toplevel ที่โผล่หลัง hover ค้างสักครู่)
#
# ตัวแปรสำคัญที่ปรับจูนได้:
#   _TOOLBAR_HEIGHT   = ความสูงของแถบ toolbar (พิกเซล)
#   _ICON_SIZE        = ขนาดไอคอนในปุ่ม (พิกเซล) ส่งต่อให้ icon_loader.get_icon()
#   _TOOLTIP_DELAY_MS = หน่วงเวลาก่อนโชว์ tooltip หลัง hover ค้าง (ms)
#   _COLOR_BG / _COLOR_HOVER / _COLOR_DIVIDER = สีพื้นหลัง/hover/เส้นแบ่ง
# ==============================================================================
import tkinter as tk
import customtkinter as ctk

from ui.icon_loader import get_icon

_TOOLBAR_HEIGHT   = 40
_ICON_SIZE        = 20
_TOOLTIP_DELAY_MS = 500

_COLOR_BG      = "#1a1a1a"
_COLOR_HOVER   = "#2a2a2a"
_COLOR_DIVIDER = "#3a3a3a"


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
        tk.Label(tw, text=self.text, justify="left", background="#2e2e2e",
                 foreground="#e0e0e0", relief="solid", borderwidth=1,
                 font=("Segoe UI", 9), padx=6, pady=2).pack()
        self._tip_window = tw

    def _hide(self):
        if self._tip_window is not None:
            try:
                self._tip_window.destroy()
            except Exception:
                pass
            self._tip_window = None


class ToolBar:
    """Thonny-style top toolbar — สร้างครั้งเดียวใน ui/main_window.py และ
    .pack() ไว้เหนือ self.main_body (ดู PLAN_toolbar-and-settings-dialogs_v01.md
    §Layout restructuring)"""

    def __init__(self, app):
        self.app = app
        self.frame = ctk.CTkFrame(app.root, fg_color=_COLOR_BG, corner_radius=0,
                                  height=_TOOLBAR_HEIGHT)
        self.frame.pack_propagate(False)
        self.btn_reset    = self._add_icon_button("home",   "Reset Position",   app.reset_position)
        self.btn_rotate   = self._add_icon_button("rotate", "Rotate 90°",       app.rotate_screen)
        self._add_divider()
        self.btn_hardware = self._add_icon_button("gear",   "Hardware Setting", self._open_hardware_setting)
        self.btn_export   = self._add_icon_button("export", "G-code Export",    self._open_gcode_export)

    # ------------------------------------------------------------------
    def pack(self, **kwargs):
        self.frame.pack(**kwargs)

    # ------------------------------------------------------------------
    def _add_icon_button(self, icon_name: str, tooltip_text: str, command):
        btn = ctk.CTkButton(
            self.frame, text="", image=get_icon(icon_name, _ICON_SIZE),
            width=36, height=32, fg_color="transparent", hover_color=_COLOR_HOVER,
            corner_radius=6, command=command)
        btn.pack(side="left", padx=(6, 2), pady=4)
        _Tooltip(btn, tooltip_text)
        return btn

    def _add_divider(self):
        div = ctk.CTkFrame(self.frame, fg_color=_COLOR_DIVIDER, width=1,
                           height=_TOOLBAR_HEIGHT - 14)
        div.pack(side="left", padx=8, pady=7)

    # ------------------------------------------------------------------
    def _open_hardware_setting(self):
        self.app.hardware_setting_dialog.show()

    def _open_gcode_export(self):
        self.app.gcode_export_panel.show()