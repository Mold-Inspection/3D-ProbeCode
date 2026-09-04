# ==============================================================================
# ui/icon_loader.py — สร้างไอคอนเครื่องมือขนาดเล็ก (mini tool icons) แบบ
# procedurally-generated ด้วย PIL แทนการใช้ emoji เดิม (⟳ ⌂ 🔩 🖨) — ไม่ต้องพึ่ง
# ไฟล์ภาพภายนอกเลย ทุกไอคอนถูกวาดด้วยโค้ดล้วน ๆ ตอน runtime
# ==============================================================================
# VERSION: 01
# หน้าที่: วาดไอคอน monochrome เรียบง่าย (rotate / home / gear / export / ruler)
# ที่ความละเอียดสูงกว่าจริง (_SUPERSAMPLE เท่า) แล้วย่อลงด้วย LANCZOS เพื่อความ
# คมชัด (anti-aliasing) จากนั้นห่อเป็น customtkinter.CTkImage พร้อมแคชผลลัพธ์
# ไว้ (คีย์ = ชื่อไอคอน + ขนาด + สี) เรียกใช้จาก ui/main_window.py และ
# core/gcode_export_panel.py แทนการใส่ emoji นำหน้าข้อความปุ่ม เช่น:
#   old: text="⟳ Rotate 90°"
#   new: text="  Rotate 90°", image=get_icon("rotate", 18), compound="left"
#
# ตัวแปรสำคัญที่ปรับจูนได้:
#   _SUPERSAMPLE   = อัตราขยายก่อนวาด (ยิ่งมาก เส้นยิ่งคมแต่ช้าลงตอนสร้างครั้งแรก)
#   _STROKE_FRAC   = ความหนาเส้น เป็นสัดส่วนของ canvas เต็ม — ปรับความหนาไอคอนได้
#   _DEFAULT_COLOR = สีไอคอนเริ่มต้น (ขาว) — ใช้ได้กับพื้นปุ่มสีเข้ม/สี accent ทุกแบบ
#     ที่ใช้อยู่ในโปรแกรม (ฟ้า/ส้ม/แดง/กรมท่า) — ถ้าจะใช้บนปุ่มพื้นอ่อน ส่ง
#     color="#202020" (หรือสีอื่น) เข้า get_icon() แทนได้
# ==============================================================================
import math
import customtkinter as ctk
from PIL import Image, ImageDraw

_SUPERSAMPLE   = 8       # วาดที่ N เท่าของขนาดจริงแล้วย่อลง — ปรับได้
_STROKE_FRAC   = 0.09    # ความหนาเส้น (สัดส่วนของ canvas เต็ม) — ปรับได้
_DEFAULT_COLOR = "#ffffff"

_cache: dict = {}   # (name, size, color) -> CTkImage


def _stroke_w(px: int) -> int:
    return max(2, int(px * _STROKE_FRAC))


# ------------------------------------------------------------------
# แต่ละฟังก์ชันคืน PIL.Image (RGBA, พื้นหลังโปร่งใส) ขนาด px×px
# ------------------------------------------------------------------
def _icon_rotate(px: int, color: str) -> Image.Image:
    """ลูกศรวงกลม (270°) — ใช้กับปุ่ม Rotate 90°"""
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    w = _stroke_w(px)
    pad = int(px * 0.16)
    bbox = [pad, pad, px - pad, px - pad]
    d.arc(bbox, start=-40, end=250, fill=color, width=w)

    cx, cy = px / 2, px / 2
    r = (px - 2 * pad) / 2
    end_deg = 250
    ang = math.radians(end_deg)
    tip = (cx + r * math.cos(ang), cy + r * math.sin(ang))
    head = px * 0.16
    a1 = math.radians(end_deg - 45)
    a2 = math.radians(end_deg + 45)
    p1 = (tip[0] - head * math.cos(a1), tip[1] - head * math.sin(a1))
    p2 = (tip[0] - head * math.cos(a2), tip[1] - head * math.sin(a2))
    d.polygon([tip, p1, p2], fill=color)
    return img


def _icon_home(px: int, color: str) -> Image.Image:
    """บ้าน (หลังคา + ผนัง + ประตู) — ใช้กับปุ่ม Reset Position"""
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    w = _stroke_w(px)
    pad = int(px * 0.14)
    roof_top = (px / 2, pad)
    roof_l = (pad, px * 0.5)
    roof_r = (px - pad, px * 0.5)
    d.line([roof_l, roof_top, roof_r], fill=color, width=w, joint="curve")
    base = [px * 0.22, px * 0.5, px * 0.78, px * 0.86]
    d.rectangle(base, outline=color, width=w)
    door = [px * 0.44, px * 0.62, px * 0.56, px * 0.86]
    d.rectangle(door, outline=color, width=max(2, int(w * 0.7)))
    return img


def _icon_gear(px: int, color: str) -> Image.Image:
    """เฟือง (วงกลม + ฟันเฟือง + รูตรงกลาง) — ใช้กับหัวข้อ Hardware Setting"""
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy = px / 2, px / 2
    r_outer = px * 0.30
    teeth, tooth_len, tooth_w_deg = 8, px * 0.10, 20

    for i in range(teeth):
        ang = 360 / teeth * i
        a1 = math.radians(ang - tooth_w_deg / 2)
        a2 = math.radians(ang + tooth_w_deg / 2)
        p1 = (cx + r_outer * math.cos(a1), cy + r_outer * math.sin(a1))
        p2 = (cx + r_outer * math.cos(a2), cy + r_outer * math.sin(a2))
        p3 = (cx + (r_outer + tooth_len) * math.cos(a2), cy + (r_outer + tooth_len) * math.sin(a2))
        p4 = (cx + (r_outer + tooth_len) * math.cos(a1), cy + (r_outer + tooth_len) * math.sin(a1))
        d.polygon([p1, p2, p3, p4], fill=color)

    d.ellipse([cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer], fill=color)
    hole_r = r_outer * 0.42
    d.ellipse([cx - hole_r, cy - hole_r, cx + hole_r, cy + hole_r], fill=(0, 0, 0, 0))
    return img


def _icon_export(px: int, color: str) -> Image.Image:
    """ลูกศรลงถาด (export tray) — ใช้กับหัวข้อ G-code Export"""
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    w = _stroke_w(px)
    tray = [px * 0.20, px * 0.62, px * 0.80, px * 0.86]
    d.line([(tray[0], tray[1]), (tray[0], tray[3]), (tray[2], tray[3]), (tray[2], tray[1])],
           fill=color, width=w, joint="curve")
    d.line([(px * 0.5, px * 0.10), (px * 0.5, px * 0.56)], fill=color, width=w)
    head = px * 0.16
    d.polygon([
        (px * 0.5 - head, px * 0.56 - head * 0.2),
        (px * 0.5 + head, px * 0.56 - head * 0.2),
        (px * 0.5, px * 0.56 + head * 0.6),
    ], fill=color)
    return img


def _icon_ruler(px: int, color: str) -> Image.Image:
    """ไม้บรรทัด (กรอบ + ขีดสเกล) — ใช้กับหัวข้อย่อย Machine Working Area"""
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    w = _stroke_w(px)
    rect = [px * 0.10, px * 0.36, px * 0.90, px * 0.64]
    d.rectangle(rect, outline=color, width=w)
    n = 5
    for i in range(1, n):
        x = rect[0] + (rect[2] - rect[0]) * i / n
        d.line([(x, rect[1]), (x, rect[1] + (rect[3] - rect[1]) * 0.5)],
               fill=color, width=max(2, int(w * 0.7)))
    return img


_DRAWERS = {
    "rotate": _icon_rotate,
    "home":   _icon_home,
    "gear":   _icon_gear,
    "export": _icon_export,
    "ruler":  _icon_ruler,
}


def get_icon(name: str, size: int = 18, color: str = _DEFAULT_COLOR) -> ctk.CTkImage:
    """คืน CTkImage ของไอคอนที่ขอ (แคชไว้ — เรียกซ้ำไม่เสียเวลาวาดใหม่)
    ใช้กับปุ่ม/label ผ่าน image=get_icon(...), compound="left" """
    key = (name, size, color)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    drawer = _DRAWERS.get(name)
    if drawer is None:
        raise ValueError(f"Unknown icon name: {name!r} (available: {list(_DRAWERS)})")

    px = size * _SUPERSAMPLE
    big = drawer(px, color)
    small = big.resize((size, size), Image.LANCZOS)
    ctk_img = ctk.CTkImage(light_image=small, dark_image=small, size=(size, size))
    _cache[key] = ctk_img
    return ctk_img