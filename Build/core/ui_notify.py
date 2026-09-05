# core/ui_notify.py
# VERSION: 01
# หน้าที่: Non-blocking, in-window notification ("toast") — เป็น widget
# ธรรมดา (tk.Canvas + ctk.CTkFrame) ที่ .place() ทับอยู่บน app.root ไม่ใช่
# ctk.CTkToplevel แยกหน้าต่าง — ใช้แพทเทิร์นเดียวกับ warning label ใน
# ui/main_window.py::_build_selected_item() (สร้าง widget ตอนจะโชว์ ทำลาย
# ทิ้งตอนจะซ่อน) ดู PLAN_non-blocking-notifications_v01.md §3 สำหรับ
# บริบทที่มาของฟีเจอร์นี้
#
# ทำไมไม่ใช้ grab_set()/Toplevel:
#   - ฟังก์ชันที่เรียก self.notify.show(...) ต้อง return ทันที (ไม่ block
#     เหมือน tkinter.messagebox) — เป็นเป้าหมายหลักของ PLAN นี้
#
# ทำไมมีเงามืดคลุมด้านหลัง (เพิ่มจาก PLAN v01 เดิม):
#   - ผู้ใช้ต้องการให้หน้าตาเหมือน popup/dialog มากขึ้น (มีอะไรมาคลุมพื้นหลัง)
#   - Tkinter/customtkinter ไม่มี true alpha blending ต่อ widget ตรง ๆ
#     (จะทำได้จริงต้อง screenshot + composite ซึ่งเกินความจำเป็น) จึงใช้เทคนิค
#     คลาสสิกของ Tk: tk.Canvas.create_rectangle(..., stipple='gray50')
#     วาดจุดดำสลับช่องแบบ ~50% density ทับของเดิม ได้เอฟเฟกต์ใกล้เคียง
#     "มืดลง 50%" โดยไม่ต้องพึ่งไลบรารีเพิ่ม
#   - ผลข้างเคียงที่ต้องรู้: เพราะ overlay คลุมเต็มหน้าต่าง มันจะ "ดัก" คลิก
#     บน canvas/sidebar ด้านหลังไว้ด้วย (คลิกที่ไหนก็ได้บน overlay = ปิด
#     toast ก่อนเวลา) — ต่างจาก PLAN v01 เดิมที่ตั้งใจให้พื้นหลังคลิกได้ปกติ
#     ระหว่างโชว์ toast แต่ตรงกับที่ผู้ใช้ขอเพิ่มเติมรอบนี้ (ทำให้ดูเหมือน
#     dialog มากขึ้น) — ในแง่ "ไม่ block" ยังคงจริงอยู่: self.notify.show()
#     คืนค่าทันที ไม่หยุดโปรแกรมรอ เหมือน _mb.show*() ทำ
#
# ตัวแปรสำคัญที่ปรับจูนได้:
#   _DEFAULT_DURATION   = ระยะเวลา auto-dismiss ต่อ severity (ms)
#   _COLOR_INFO/SUCCESS/WARN = สี border/ปุ่ม ตาม severity (อิงจากพาเลตเดิม
#                              ที่ใช้ทั่วโปรแกรมอยู่แล้ว — ดู PLAN §3)
#   _OVERLAY_STIPPLE    = ความหนาแน่นจุดของเงามืด ('gray50' ≈ 50%,
#                          'gray25' จางลง, 'gray75' เข้มขึ้น)
#   _BOX_FG_COLOR       = สีพื้นกล่องข้อความ
# ==============================================================================
import tkinter as tk
import customtkinter as ctk

_COLOR_INFO    = "#1565c0"
_COLOR_SUCCESS = "#2E7D32"
_COLOR_WARN    = "#8a6d00"

_ICONS = {"info": "ℹ", "success": "✅", "warn": "⚠"}

_DEFAULT_DURATION = {"info": 3500, "success": 3500, "warn": 5000}   # ms — ปรับได้

_OVERLAY_STIPPLE = "gray50"   # ความหนาแน่นจุดของเงามืด — ปรับได้ ('gray25'/'gray50'/'gray75')
_BOX_FG_COLOR    = "#1c1c1c"


class UINotify:
    """Non-blocking in-window notification.

    self.notify.show(...) สร้าง widget (tk.Canvas เงามืด + ctk.CTkFrame
    กล่องข้อความ) แล้ว .place() ทับ app.root — return ทันที ไม่ block
    เหมือน tkinter.messagebox แต่ยังคงมีเงามืดคลุมพื้นหลังให้ดูคล้าย dialog
    """

    def __init__(self, app):
        self.app = app
        self._overlay   = None   # tk.Canvas — เงามืด
        self._box       = None   # ctk.CTkFrame — กล่องข้อความ
        self._after_id  = None

    # ------------------------------------------------------------------
    def show(self, message: str, severity: str = "info", duration_ms: int = None):
        """โชว์ (หรือแทนที่) toast ปัจจุบัน — non-blocking, return ทันที

        severity: 'info' | 'success' | 'warn'
        duration_ms: None = ใช้ค่าเริ่มต้นตาม severity (_DEFAULT_DURATION);
                      0 หรือค่าลบ = ไม่ auto-dismiss (ต้องคลิกปิดเอง)
        """
        self._dismiss()   # toast เก่า (ถ้ามี) ถูกแทนที่เสมอ — ไม่ต่อคิว (PLAN §7)

        color = {"info": _COLOR_INFO, "success": _COLOR_SUCCESS,
                 "warn": _COLOR_WARN}.get(severity, _COLOR_INFO)
        icon  = _ICONS.get(severity, "ℹ")
        if duration_ms is None:
            duration_ms = _DEFAULT_DURATION.get(severity, 3500)

        root = self.app.root
        root.update_idletasks()
        w, h = root.winfo_width(), root.winfo_height()

        # --- เงามืดคลุมพื้นหลัง (จำลอง ~50% opacity ด้วย stipple) --------
        overlay = tk.Canvas(root, width=w, height=h, highlightthickness=0,
                            bd=0, bg="black")
        overlay.place(x=0, y=0, relwidth=1, relheight=1)
        overlay.create_rectangle(0, 0, w, h, fill="black",
                                  stipple=_OVERLAY_STIPPLE, outline="")
        overlay.bind("<Button-1>", lambda e: self._dismiss())
        self._overlay = overlay

        # --- กล่องข้อความ กึ่งกลางหน้าจอ ----------------------------------
        box = ctk.CTkFrame(root, fg_color=_BOX_FG_COLOR, corner_radius=10,
                           border_width=2, border_color=color)
        ctk.CTkLabel(box, text=f"{icon}  {message}", justify="left",
                    font=ctk.CTkFont(size=14, weight="bold"),
                    text_color="white", wraplength=360).pack(padx=24, pady=(20, 12))
        ctk.CTkButton(box, text="OK", width=80, fg_color=color, hover_color=color,
                     command=self._dismiss).pack(pady=(0, 18))
        box.place(relx=0.5, rely=0.5, anchor="center")
        self._box = box

        if duration_ms and duration_ms > 0:
            self._after_id = root.after(duration_ms, self._dismiss)

    # ------------------------------------------------------------------
    def _dismiss(self):
        if self._after_id is not None:
            try:
                self.app.root.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        if self._box is not None:
            try: self._box.destroy()
            except Exception: pass
            self._box = None
        if self._overlay is not None:
            try: self._overlay.destroy()
            except Exception: pass
            self._overlay = None