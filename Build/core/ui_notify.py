# core/ui_notify.py
# VERSION: 02
# CHANGE LOG (v01 -> v02):
#   เปลี่ยนจาก toast ในหน้าต่าง (กล่องข้อความ + เงามืดคลุมทั้งหน้าต่าง) เป็น
#   popup ปกติของ Windows (tkinter.messagebox) ตามที่ผู้ใช้ขอ — เงามืดแบบ
#   stipple ทำให้ทั้งจอดูดำ และกล่องข้อความยังถูก dialog อื่นบังได้
#   ผู้เรียกทุกจุด (self.notify.show(...)) ใช้ต่อได้โดยไม่ต้องแก้: signature เดิม
#
# หน้าที่: แจ้งข้อความสั้น ๆ ให้ผู้ใช้ (เช่น "ไม่พบรูในมุมมองนี้", "คำนวณผลลัพธ์
# ใหม่แล้ว") ด้วย message box มาตรฐานของระบบ
#
# ยังคง "ไม่ block ผู้เรียก": show() แค่จองคิวให้ popup ขึ้นหลังจากฟังก์ชันที่
# เรียกทำงานจบ (root.after) แล้ว return ทันที — ฟังก์ชันอย่าง show_view() ที่
# เรียก notify กลางทาง จึงวาดกราฟ/อัปเดตรายการเสร็จก่อน popup จะขึ้น ไม่ค้างอยู่
# ครึ่งทางระหว่างรอผู้ใช้กด OK
#
# ตัวแปรสำคัญที่ปรับจูนได้:
#   _TITLE        = ข้อความบน title bar ของ popup
#   _SHOW_DELAY_MS = หน่วงก่อน popup ขึ้น (ms) — ให้การวาดหน้าจอของผู้เรียกเสร็จก่อน
# ==============================================================================
import tkinter.messagebox as _mb

_TITLE         = "3D ProbeCode"
_SHOW_DELAY_MS = 10


class UINotify:
    """แจ้งเตือนด้วย message box ปกติของ Windows

    self.notify.show(message, severity) — severity: 'info' | 'success' | 'warn'
    ('warn' ใช้ไอคอนเตือน, อีกสองแบบใช้ไอคอนข้อมูล)
    """

    def __init__(self, app):
        self.app = app

    # ------------------------------------------------------------------
    def show(self, message: str, severity: str = "info", duration_ms: int = None):
        """จองคิวแสดง popup แล้ว return ทันที (ไม่ block ผู้เรียก)

        duration_ms: คงไว้เพื่อให้เข้ากับผู้เรียกเดิม — ไม่ใช้แล้ว (message box
        ปิดเมื่อผู้ใช้กด OK ไม่ได้หายเองตามเวลา)
        """
        box = _mb.showwarning if severity == "warn" else _mb.showinfo
        root = self.app.root

        def _open():
            try:
                box(_TITLE, message, parent=root)
            except Exception:
                pass   # หน้าต่างหลักถูกปิดไปก่อน popup จะขึ้น

        root.after(_SHOW_DELAY_MS, _open)
