# ui/settings_dialog_base.py — Shared VS Code-style dialog chrome for
# floating settings dialogs (Hardware Setting / G-code Export)
# ==============================================================================
# VERSION: 07
# CHANGE LOG (v06 -> v07):
#   FIX: Dialog is now a fixed size with a scrollable content area.
#   - Replaced _DIALOG_MIN_WIDTH/HEIGHT with fixed _DIALOG_WIDTH/HEIGHT (640x640).
#   - Categories now use ctk.CTkScrollableFrame so content taller than the 
#     window will scroll internally instead of stretching the toplevel.
#   - Removed dynamic sizing methods (_fit_to_content, _apply_fit_geometry, 
#     _second_pass_fit) as geometry is now statically set once in show().
# ==============================================================================
import customtkinter as ctk

_DIALOG_WIDTH        = 640
_DIALOG_HEIGHT       = 640
_CATEGORY_LIST_WIDTH = 190

_COLOR_HEADER    = "#1e1e1e"
_COLOR_BODY      = "#181818"
_COLOR_CAT_BG    = "#141414"
_COLOR_CAT_SEL   = "#2a2a4e"
_COLOR_CAT_HOVER = "#232338"
_COLOR_FIELD_BG  = "#1c1c1c"


class SettingsDialogBase:
    """กรอบ dialog กลาง (VS Code Settings-style) — ใช้ร่วมกันระหว่าง
    Hardware Setting และ G-code Export dialogs. MODAL, ขนาดคงที่ (v07)
    และสามารถเลื่อนดูเนื้อหาภายในได้หากมีขนาดใหญ่เกินหน้าต่าง"""

    def __init__(self, master, title: str):
        self.master      = master
        self.title_text  = title

        self._categories      = {}   # key -> {'label':, 'build_fn':, 'frame': None}
        self._category_order  = []
        self._cat_buttons     = {}
        self._active_key      = None

        self.toplevel = None
        self._drag_offset_x = 0
        self._drag_offset_y = 0
        self._master_focus_bind_id = None

    def add_category(self, key: str, label: str, build_fn):
        self._categories[key] = {'label': label, 'build_fn': build_fn, 'frame': None}
        self._category_order.append(key)

    def show(self):
        if self.toplevel is not None and self.toplevel.winfo_exists():
            self.toplevel.lift()
            self.toplevel.focus_set()
            return

        self.toplevel = ctk.CTkToplevel(self.master)
        self.toplevel.title(self.title_text)
        self.toplevel.geometry(f"{_DIALOG_WIDTH}x{_DIALOG_HEIGHT}")
        self.toplevel.configure(fg_color=_COLOR_BODY)
        self.toplevel.protocol("WM_DELETE_WINDOW", self._on_close)
        self.toplevel.overrideredirect(True)

        self._build_header()
        self._build_search_bar()
        self._build_body()

        if self._category_order:
            self.show_category(self._category_order[0])
            self._center_on_master()
        else:
            self._center_on_master()

        self.toplevel.transient(self.master)
        try:
            self.toplevel.wait_visibility()
            self.toplevel.grab_set()
        except Exception:
            pass
        self.toplevel.focus_set()

        self.toplevel.bind("<Unmap>", self._on_dialog_unmap)
        self.toplevel.bind("<Map>",   self._on_dialog_map)
        self.toplevel.bind("<Escape>", lambda e: self._on_close())

        self._master_focus_bind_id = self.master.bind(
            "<FocusIn>", self._on_master_focus_in, add="+")

    def _on_dialog_unmap(self, _event=None):
        if self.toplevel is not None:
            try:
                self.toplevel.grab_release()
            except Exception:
                pass

    def _on_dialog_map(self, _event=None):
        if self.toplevel is not None and self.toplevel.winfo_exists():
            try:
                self.toplevel.grab_set()
            except Exception:
                pass

    def _on_master_focus_in(self, _event=None):
        if self.toplevel is not None and self.toplevel.winfo_exists():
            self.toplevel.lift()
            self.toplevel.focus_set()

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
            pass

    def _build_header(self):
        header = ctk.CTkFrame(self.toplevel, fg_color=_COLOR_HEADER, corner_radius=0, height=44)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        title_label = ctk.CTkLabel(header, text=self.title_text, font=ctk.CTkFont(size=15, weight="bold"),
                    text_color="#e0e0e0")
        title_label.pack(side="left", padx=16)

        ctk.CTkButton(header, text="✕", width=32, height=28, fg_color="transparent",
                     hover_color="#3a1f1f", text_color="#cccccc", font=ctk.CTkFont(size=14),
                     command=self._on_close).pack(side="right", padx=8)

        self._make_draggable(header)
        self._make_draggable(title_label)

    def _make_draggable(self, widget):
        widget.bind("<ButtonPress-1>", self._on_drag_start)
        widget.bind("<B1-Motion>", self._on_drag_motion)

    def _on_drag_start(self, event):
        if self.toplevel is None:
            return
        self._drag_offset_x = event.x_root - self.toplevel.winfo_x()
        self._drag_offset_y = event.y_root - self.toplevel.winfo_y()

    def _on_drag_motion(self, event):
        if self.toplevel is None:
            return
        x = event.x_root - self._drag_offset_x
        y = event.y_root - self._drag_offset_y
        self.toplevel.geometry(f"+{x}+{y}")

    def _build_search_bar(self):
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
            # v07: เปลี่ยนไปใช้ CTkScrollableFrame เพื่อให้เลื่อนดูข้อมูลได้
            cat['frame'] = ctk.CTkScrollableFrame(self._content_frame, fg_color="transparent")
            cat['build_fn'](cat['frame'])
        cat['frame'].pack(fill="both", expand=True)

    def _on_close(self):
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