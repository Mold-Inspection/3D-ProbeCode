# ==============================================================================
# ui/settings_dialog_base.py — Shared VS Code-style dialog chrome for
# floating settings dialogs (Hardware Setting / G-code Export)
# ==============================================================================
# VERSION: 04
# CHANGE LOG (v01 -> v02):
#   FIX: _on_close() previously only nulled out self.toplevel — every
#   category's cached 'frame' (and the category buttons / _active_key)
#   kept pointing at widgets that were children of the just-destroyed
#   Toplevel. Reopening the dialog created a NEW Toplevel, but
#   show_category() saw cat['frame'] was still non-None and skipped
#   rebuilding it, then tried to .pack() a frame whose underlying Tcl
#   widget no longer existed -> 'bad window path name' TclError on the
#   SECOND open of any dialog built on this base class (Hardware
#   Setting / G-code Export). Fix: drop all per-category widget caches
#   and the category-button dict in _on_close() too, so the next show()
#   rebuilds every category frame from scratch inside the new Toplevel,
#   exactly like the very first open.
#
# CHANGE LOG (v02 -> v03):
#   FEATURE (per user request — overrides the original "Non-modal ตามที่
#   ตกลงกัน" decision documented below): dialog is now MODAL, matching
#   ctk.filedialog.askopenfilename's behavior — self.root (canvas,
#   sidebars, toolbar, nav) is frozen/unclickable while this dialog is
#   open. User must either use a category's "Apply" button (which does
#   NOT auto-close — see hardware_setting_dialog.py / gcode_export_panel.py,
#   unchanged) or click ✕ to close before the main window responds again.
#   Implemented via self.toplevel.transient(self.master) +
#   self.toplevel.grab_set() in show(), released in _on_close() before
#   destroy() (grab_release() must run on a window that still exists,
#   so it's called first, then destroy()).
#
# CHANGE LOG (v03 -> v04):
#   FIX: modal grab (v03) could leave the ENTIRE app unresponsive after
#   alt-tab / window-switch on Windows, requiring a force-quit — a known
#   Tk+grab_set() failure mode, not specific to this app. Root causes
#   addressed:
#     1) focus_force() right after grab_set() aggressively fights the OS
#        focus manager; switched to focus_set() instead.
#     2) grab_set() was called before the window was guaranteed viewable;
#        now preceded by wait_visibility() (wrapped in try/except —
#        TclError here just means the window closed before it finished
#        opening, which is harmless).
#     3) No handling for minimize/restore — grab could persist on a
#        window that's no longer visible. Now released on <Unmap>,
#        re-acquired on <Map>.
#     4) No recovery path if the user alt-tabbed back onto the main
#        window while the dialog was open — now self.master's <FocusIn>
#        lifts + refocuses the dialog instead of leaving both windows
#        stuck fighting over input.
#     5) Added <Escape> on the dialog as a manual close/escape hatch.
#   _on_close() now also releases the grab and unbinds the master
#   <FocusIn> hook it registered in show().
#
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
# (สลับหมวดคือแค่ pack/pack_forget ไม่ rebuild ทุกครั้ง — cache ถูกล้างทิ้ง
# ทุกครั้งที่ dialog ปิด ดู v02 changelog ด้านบน)
#
# MODALITY (v03 — เปลี่ยนจากของเดิม): dialog นี้ MODAL เหมือน
# ctk.filedialog.askopenfilename — ผู้ใช้ต้องกด Apply (ค่าถูกยืนยันแต่
# dialog ยังไม่ปิด) หรือกด ✕ / Escape ปิด dialog ก่อน ถึงจะกลับไปใช้
# หน้าต่างหลักได้ ดู v04 changelog สำหรับการแก้ปัญหาค้างทั้งโปรแกรมตอน
# alt-tab ที่มากับ grab_set() แบบเดิม
#
# ตัวแปรสำคัญที่ปรับจูนได้:
#   _DIALOG_MIN_WIDTH / _DIALOG_MIN_HEIGHT = ขนาดขั้นต่ำของ dialog
#   _CATEGORY_LIST_WIDTH                    = ความกว้างแถบซ้าย (category list)
#   สี _COLOR_* ต่าง ๆ = โทนสี header/body/category ของ dialog
# ==============================================================================
import customtkinter as ctk

_DIALOG_MIN_WIDTH    = 640
_DIALOG_MIN_HEIGHT   = 530
_CATEGORY_LIST_WIDTH = 190

_COLOR_HEADER    = "#1e1e1e"
_COLOR_BODY      = "#181818"
_COLOR_CAT_BG    = "#141414"
_COLOR_CAT_SEL   = "#2a2a4e"
_COLOR_CAT_HOVER = "#232338"
_COLOR_FIELD_BG  = "#1c1c1c"


class SettingsDialogBase:
    """กรอบ dialog กลาง (VS Code Settings-style) — ใช้ร่วมกันระหว่าง
    Hardware Setting และ G-code Export dialogs. MODAL (v03/v04) —
    ดู CHANGE LOG ด้านบนไฟล์"""

    def __init__(self, master, title: str):
        self.master      = master
        self.title_text  = title

        self._categories      = {}   # key -> {'label':, 'build_fn':, 'frame': None}
        self._category_order  = []
        self._cat_buttons     = {}
        self._active_key      = None

        self.toplevel = None

        self._master_focus_bind_id = None   # v04: <FocusIn> hook id on self.master, set/cleared in show()/_on_close()

    # ------------------------------------------------------------------
    def add_category(self, key: str, label: str, build_fn):
        """ลงทะเบียนหมวดหมู่ใหม่ — build_fn(parent_frame) สร้าง widget ของ
        หมวดนั้น เรียกครั้งแรกที่หมวดถูกเปิดดูเท่านั้น (lazy build, แคชไว้
        จนกว่า dialog จะถูกปิด — ดู _on_close())"""
        self._categories[key] = {'label': label, 'build_fn': build_fn, 'frame': None}
        self._category_order.append(key)

    # ------------------------------------------------------------------
    def show(self):
        """เปิด dialog (สร้างใหม่ถ้ายังไม่มี หรือดึงขึ้นหน้าถ้าเปิดอยู่แล้ว)
        v04: MODAL แบบทนต่อการสลับหน้าต่าง (alt-tab) — ดู v03->v04 changelog
        ด้านบนคลาสสำหรับสาเหตุที่ v03 เดิมค้างทั้งโปรแกรมได้"""
        if self.toplevel is not None and self.toplevel.winfo_exists():
            self.toplevel.lift()
            self.toplevel.focus_set()
            return

        self.toplevel = ctk.CTkToplevel(self.master)
        self.toplevel.title(self.title_text)
        self.toplevel.geometry(f"{_DIALOG_MIN_WIDTH}x{_DIALOG_MIN_HEIGHT}")
        self.toplevel.minsize(_DIALOG_MIN_WIDTH, _DIALOG_MIN_HEIGHT)
        self.toplevel.configure(fg_color=_COLOR_BODY)
        self.toplevel.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_header()
        self._build_search_bar()
        self._build_body()

        if self._category_order:
            self.show_category(self._category_order[0])

        self._center_on_master()

        # v04: modal grab, hardened against the alt-tab freeze —
        # wait until the window is actually viewable before grabbing
        # (grabbing too early is a known source of a stuck/half-applied
        # grab state), and use focus_set() instead of focus_force()
        # (focus_force() fighting the OS focus manager during a
        # window-switch is the main cause of the full-app freeze seen
        # under v03).
        self.toplevel.transient(self.master)
        try:
            self.toplevel.wait_visibility()
            self.toplevel.grab_set()
        except Exception:
            pass   # window was closed before it finished opening — nothing to grab
        self.toplevel.focus_set()

        # v04: release grab if the dialog gets minimized, reacquire on
        # restore — a grab surviving on a non-visible window is part of
        # the freeze chain.
        self.toplevel.bind("<Unmap>", self._on_dialog_unmap)
        self.toplevel.bind("<Map>",   self._on_dialog_map)

        # v04: keyboard escape hatch, independent of mouse/focus state
        self.toplevel.bind("<Escape>", lambda e: self._on_close())

        # v04: recovery path — if the user alt-tabs back to the MAIN
        # window while this dialog is still open, bring the dialog back
        # to front/focus instead of leaving both windows unresponsive.
        self._master_focus_bind_id = self.master.bind(
            "<FocusIn>", self._on_master_focus_in, add="+")

    # ------------------------------------------------------------------
    def _on_dialog_unmap(self, _event=None):
        """v04: dialog minimized — release the grab so it can't get stuck
        held by a window that's no longer visible/interactable."""
        if self.toplevel is not None:
            try:
                self.toplevel.grab_release()
            except Exception:
                pass

    def _on_dialog_map(self, _event=None):
        """v04: dialog restored from minimize — reacquire the modal grab."""
        if self.toplevel is not None and self.toplevel.winfo_exists():
            try:
                self.toplevel.grab_set()
            except Exception:
                pass

    def _on_master_focus_in(self, _event=None):
        """v04: user alt-tabbed back onto the main window while this
        dialog is open — without this, self.master can't respond
        (grab_set() is still active) but the dialog also isn't the
        frontmost window, which is exactly the stuck state being fixed.
        Bring the dialog back in front and refocus it instead."""
        if self.toplevel is not None and self.toplevel.winfo_exists():
            self.toplevel.lift()
            self.toplevel.focus_set()

    # ------------------------------------------------------------------
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
        """v02 FIX: clear cached per-category frames/buttons so the next
        show() rebuilds them fresh inside a new Toplevel.
        v03: release the modal grab before destroying the window.
        v04: also unbind the <FocusIn> hook registered on self.master in
        show() — leaving it bound after close would keep calling
        .lift()/.focus_set() on a destroyed self.toplevel reference
        every time the main window regains OS focus."""
        if self.toplevel is not None:
            try:
                self.toplevel.grab_release()
            except Exception:
                pass
            try:
                self.toplevel.destroy()
            except Exception:
                pass
        self.toplevel = None

        if self._master_focus_bind_id is not None:
            try:
                self.master.unbind("<FocusIn>", self._master_focus_bind_id)
            except Exception:
                pass
            self._master_focus_bind_id = None

        for cat in self._categories.values():
            cat['frame'] = None
        self._cat_buttons = {}
        self._active_key  = None