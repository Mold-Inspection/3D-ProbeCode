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
import sys
import tkinter.messagebox as _mb
import customtkinter as ctk

from ui import theme

_DIALOG_WIDTH        = 640
_DIALOG_HEIGHT       = 640
_CATEGORY_LIST_WIDTH = 190

_COLOR_HEADER    = theme.BG_CARD
_COLOR_BODY      = theme.BG_PANEL
_COLOR_CAT_BG    = theme.BG_CANVAS
_COLOR_CAT_SEL   = theme.SELECT_BG
_COLOR_CAT_HOVER = theme.BG_CARD_HOVER
_COLOR_FIELD_BG  = theme.BG_INPUT


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
        self.on_close = None   # callback ก่อนปิด dialog (เช่น จำค่าที่กรอกไว้) — ตั้งโดยเจ้าของ dialog
        self._drag_offset_x = 0
        self._drag_offset_y = 0
        self._master_focus_bind_id = None

    def add_category(self, key: str, label: str, build_fn):
        self._categories[key] = {'label': label, 'build_fn': build_fn, 'frame': None}
        self._category_order.append(key)

    def show(self):
        if self.toplevel is not None and self.toplevel.winfo_exists():
            self.toplevel.lift()
            self.toplevel.focus_force()
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
            self._set_owner_window()
            self.toplevel.grab_set()
        except Exception:
            pass
        # FIX: focus_force() (not focus_set()) - after an earlier settings dialog was
        # closed while it held the keyboard focus, Tk can be left believing the app
        # has no focus at all; a plain focus_set() is then only "remembered" and the
        # entry fields of the next dialog ignore typing. Forcing it always works.
        self.toplevel.focus_force()

        self.toplevel.bind("<Unmap>", self._on_dialog_unmap)
        self.toplevel.bind("<Map>",   self._on_dialog_map)
        self.toplevel.bind("<Escape>", lambda e: self._on_close())

        self._master_focus_bind_id = self.master.bind(
            "<FocusIn>", self._on_master_focus_in, add="+")

    def _set_owner_window(self):
        """Windows: ผูก dialog นี้เป็น "owned window" ของหน้าต่างหลัก

        FIX: dialog ใช้ overrideredirect(True) (ไม่มี title bar ของระบบ) ซึ่งทำให้
        transient() ของ Tk ไม่มีผลบน Windows — dialog จึงเป็นหน้าต่างอิสระที่ไม่
        ผูกลำดับชั้นกับหน้าต่างหลัก พอ Alt-Tab ออกแล้วกลับเข้ามา Windows ยกเฉพาะ
        หน้าต่างหลักขึ้นมาทับ dialog (dialog "หายไป") ทั้งที่ dialog ยังถือ
        grab_set() อยู่ ทุกคลิกจึงถูกกลืน โปรแกรมดูเหมือนค้างทั้งจอ
        การตั้ง owner ให้ Windows รู้จัก ทำให้ dialog อยู่เหนือหน้าต่างหลักเสมอ
        และย่อ/คืนหน้าต่างไปพร้อมกัน (ระบบอื่นที่ไม่ใช่ Windows ข้ามไป)"""
        if sys.platform != "win32" or self.toplevel is None:
            return
        try:
            import ctypes
            user32 = ctypes.windll.user32
            setter = getattr(user32, "SetWindowLongPtrW", None) or user32.SetWindowLongW
            setter.restype  = ctypes.c_void_p
            setter.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
            dialog_hwnd = int(self.toplevel.wm_frame(), 16)
            owner_hwnd  = int(self.master.winfo_toplevel().wm_frame(), 16)
            setter(dialog_hwnd, -8, owner_hwnd)   # -8 = GWLP_HWNDPARENT (owner)
        except Exception:
            pass   # best-effort — ถ้าตั้งไม่ได้ก็ยังทำงานแบบเดิม

    # ------------------------------------------------------------------
    # Native popups (messagebox / file dialog) ที่เปิดจากใน dialog นี้
    # ------------------------------------------------------------------
    def run_native(self, fn, *args, **kwargs):
        """เรียก popup ของระบบ (tkinter.messagebox.*, filedialog.*) โดยมี dialog
        นี้เป็นเจ้าของ แล้วคืนค่าที่ popup คืนมา

        FIX: เดิมเรียก _mb.showerror(...) ตรง ๆ โดยไม่ระบุ parent → popup ไปผูกกับ
        หน้าต่างหลักแทน ทำให้ Windows ดันหน้าต่างหลักขึ้นมาทับ dialog นี้ (dialog
        "หายไป") ในขณะที่ dialog ยังถือ grab_set() อยู่ — พอปิด popup ทุกคลิกจึง
        ยังถูกส่งไปที่ dialog ที่มองไม่เห็น โปรแกรมเลยดูเหมือนค้างทั้งจอ
        ที่นี่จึง (1) ปล่อย grab ก่อน (2) ให้ popup มี dialog เป็น parent
        (3) ยก dialog กลับขึ้นมาและ grab ใหม่หลัง popup ปิด"""
        top = self.toplevel
        if top is None or not top.winfo_exists():
            return fn(*args, parent=self.master, **kwargs)
        try:
            top.grab_release()
        except Exception:
            pass
        try:
            return fn(*args, parent=top, **kwargs)
        finally:
            if self.toplevel is not None and self.toplevel.winfo_exists():
                try:
                    self.toplevel.lift()
                    self.toplevel.focus_force()
                    self.toplevel.grab_set()
                except Exception:
                    pass

    def showerror(self, title: str, message: str):
        return self.run_native(_mb.showerror, title, message)

    def showwarning(self, title: str, message: str):
        return self.run_native(_mb.showwarning, title, message)

    def showinfo(self, title: str, message: str):
        return self.run_native(_mb.showinfo, title, message)

    def askyesno(self, title: str, message: str) -> bool:
        return bool(self.run_native(_mb.askyesno, title, message, icon="warning"))

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
                    text_color=theme.TEXT)
        title_label.pack(side="left", padx=16)

        ctk.CTkButton(header, text="✕", width=32, height=28, fg_color="transparent",
                     hover_color=theme.ERR_BG, text_color=theme.TEXT_SECONDARY, font=ctk.CTkFont(size=14),
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
                    fg_color=_COLOR_FIELD_BG, border_color=theme.BORDER).pack(fill="x")

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
            text_color=theme.TEXT_SECONDARY, corner_radius=0, height=36,
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
        if self.toplevel is not None and self.on_close is not None:
            try:
                self.on_close()
            except Exception as e:
                print(f"[settings_dialog_base] on_close failed: {e!r}")
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