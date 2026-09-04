# ==============================================================================
# ui/settings_dialog_base.py — Shared VS Code-style dialog chrome for
# floating settings dialogs (Hardware Setting / G-code Export)
# ==============================================================================
# VERSION: 01
# หน้าที่: กรอบ dialog กลางที่ใช้ร่วมกันระหว่าง Hardware Setting และ G-code
# Export — เลียนแบบหน้า Settings ของ VS Code: header bar (title + close),
# search bar แบบ cosmetic (ยังไม่กรองจริง — PLAN_toolbar-and-settings-
# dialogs_v01.md ข้อ 2), ซ้าย = รายการหมวดหมู่ (category list, แสดงเสมอแม้
# มีหมวดเดียว — ข้อ 3), ขวา = fields ของหมวดที่เลือกอยู่
#
# วิธีใช้ (จาก dialog ลูก เช่น hardware_setting_dialog.py):
#   dialog = SettingsDialogBase(app.root, title="Hardware Setting")
#   dialog.add_category("probe", "Probe Stylus", build_probe_fields)
#   dialog.show()
# โดย build_probe_fields(parent) รับ parent frame แล้วสร้าง widget ของ
# หมวดนั้นลงไป — เรียกครั้งเดียวตอนสลับมาหมวดนั้นครั้งแรก แล้วแคช frame ไว้
# (สลับหมวดคือแค่ pack/pack_forget ไม่ rebuild ทุกครั้ง)
#
# Non-modal ตามที่ตกลงกัน (PLAN ข้อ 4) — ไม่เรียก grab_set() หน้าต่างหลัก
# ยังใช้งานได้ระหว่างเปิด dialog นี้อยู่ เปิดซ้ำจะแค่ lift() ตัวเดิมขึ้นมา
# ไม่สร้าง Toplevel ใหม่ซ้อนกัน
#
# ตัวแปรสำคัญที่ปรับจูนได้:
#   _DIALOG_MIN_WIDTH / _DIALOG_MIN_HEIGHT = ขนาดขั้นต่ำของ dialog
#   _CATEGORY_LIST_WIDTH                    = ความกว้างแถบซ้าย (category list)
#   สี _COLOR_* ต่าง ๆ = โทนสี header/body/category ของ dialog
# ==============================================================================
import customtkinter as ctk

_DIALOG_MIN_WIDTH    = 640
_DIALOG_MIN_HEIGHT   = 420
_CATEGORY_LIST_WIDTH = 190

_COLOR_HEADER    = "#1e1e1e"
_COLOR_BODY      = "#181818"
_COLOR_CAT_BG    = "#141414"
_COLOR_CAT_SEL   = "#2a2a4e"
_COLOR_CAT_HOVER = "#232338"
_COLOR_FIELD_BG  = "#1c1c1c"


class SettingsDialogBase:
    """กรอบ dialog กลาง (VS Code Settings-style) — ใช้ร่วมกันระหว่าง
    Hardware Setting และ G-code Export dialogs"""

    def __init__(self, master, title: str):
        self.master      = master
        self.title_text  = title

        self._categories      = {}   # key -> {'label':, 'build_fn':, 'frame': None}
        self._category_order  = []
        self._cat_buttons     = {}
        self._active_key      = None

        self.toplevel = None

    # ------------------------------------------------------------------
    def add_category(self, key: str, label: str, build_fn):
        """ลงทะเบียนหมวดหมู่ใหม่ — build_fn(parent_frame) สร้าง widget ของ
        หมวดนั้น เรียกครั้งแรกที่หมวดถูกเปิดดูเท่านั้น (lazy build, แคชไว้)"""
        self._categories[key] = {'label': label, 'build_fn': build_fn, 'frame': None}
        self._category_order.append(key)

    # ------------------------------------------------------------------
    def show(self):
        """เปิด dialog (สร้างใหม่ถ้ายังไม่มี หรือดึงขึ้นหน้าถ้าเปิดอยู่แล้ว)"""
        if self.toplevel is not None and self.toplevel.winfo_exists():
            self.toplevel.lift()
            self.toplevel.focus_force()
            return

        self.toplevel = ctk.CTkToplevel(self.master)
        self.toplevel.title(self.title_text)
        self.toplevel.geometry(f"{_DIALOG_MIN_WIDTH}x{_DIALOG_MIN_HEIGHT}")
        self.toplevel.minsize(_DIALOG_MIN_WIDTH, _DIALOG_MIN_HEIGHT)
        self.toplevel.configure(fg_color=_COLOR_BODY)
        # Non-modal (PLAN §4) — no grab_set(); main window stays usable
        self.toplevel.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_header()
        self._build_search_bar()
        self._build_body()

        if self._category_order:
            self.show_category(self._category_order[0])

        self._center_on_master()

    def _center_on_master(self):
        try:
            self.toplevel.update_idletasks()
            mx, my = self.master.winfo_rootx(), self.master.winfo_rooty()
            mw, mh = self.master.winfo_width(),  self.master.winfo_height()
            dw, dh = self.toplevel.winfo_width(), self.toplevel.winfo_height()
            x = mx + (mw - dw) // 2
            y = my + (mh - dh) // 2
            self.toplevel.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass   # best-effort centering only — never block dialog opening

    # ------------------------------------------------------------------
    def _build_header(self):
        header = ctk.CTkFrame(self.toplevel, fg_color=_COLOR_HEADER, corner_radius=0, height=44)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        ctk.CTkLabel(header, text=self.title_text, font=ctk.CTkFont(size=15, weight="bold"),
                    text_color="#e0e0e0").pack(side="left", padx=16)

        ctk.CTkButton(header, text="✕", width=32, height=28, fg_color="transparent",
                     hover_color="#3a1f1f", text_color="#cccccc", font=ctk.CTkFont(size=14),
                     command=self._on_close).pack(side="right", padx=8)

    def _build_search_bar(self):
        # Cosmetic only (PLAN §2) — matches VS Code's search-bar strip
        # visually, does not filter fields.
        bar = ctk.CTkFrame(self.toplevel, fg_color=_COLOR_HEADER, corner_radius=0)
        bar.pack(fill="x", side="top", padx=16, pady=(8, 8))
        ctk.CTkEntry(bar, placeholder_text="Search settings...",
                    fg_color=_COLOR_FIELD_BG, border_color="#333333").pack(fill="x")

    def _build_body(self):
        body = ctk.CTkFrame(self.toplevel, fg_color=_COLOR_BODY, corner_radius=0)
        body.pack(fill="both", expand=True)

        self._category_frame = ctk.CTkFrame(body, fg_color=_COLOR_CAT_BG, corner_radius=0,
                                            width=_CATEGORY_LIST_WIDTH)
        self._category_frame.pack(side="left", fill="y")
        self._category_frame.pack_propagate(False)

        for key in self._category_order:
            self._build_category_button(key)

        self._content_frame = ctk.CTkFrame(body, fg_color=_COLOR_BODY, corner_radius=0)
        self._content_frame.pack(side="left", fill="both", expand=True, padx=18, pady=14)

    def _build_category_button(self, key: str):
        label = self._categories[key]['label']
        btn = ctk.CTkButton(
            self._category_frame, text=label, anchor="w",
            fg_color="transparent", hover_color=_COLOR_CAT_HOVER,
            text_color="#b0bec5", corner_radius=0, height=36,
            font=ctk.CTkFont(size=12),
            command=lambda k=key: self.show_category(k))
        btn.pack(fill="x")
        self._cat_buttons[key] = btn

    # ------------------------------------------------------------------
    def show_category(self, key: str):
        if key not in self._categories:
            return
        self._active_key = key

        for k, btn in self._cat_buttons.items():
            btn.configure(fg_color=_COLOR_CAT_SEL if k == key else "transparent")

        for cat in self._categories.values():
            if cat['frame'] is not None:
                cat['frame'].pack_forget()

        cat = self._categories[key]
        if cat['frame'] is None:
            cat['frame'] = ctk.CTkFrame(self._content_frame, fg_color="transparent")
            cat['build_fn'](cat['frame'])
        cat['frame'].pack(fill="both", expand=True)

    # ------------------------------------------------------------------
    def _on_close(self):
        if self.toplevel is not None:
            self.toplevel.destroy()
        self.toplevel = None