# ==============================================================================
# ui/tab_strip.py — แถบแท็บแบบเอกสาร (Selection / Customization / ...)
# ==============================================================================
# VERSION: 01
# หน้าที่: แทน ctk.CTkSegmentedButton ตัวเดิมของ ui/main_window.py ด้วยแท็บ
# แบบ "document tab" (แท็บที่เลือกมีพื้นขาว + เส้นใต้สี ACCENT) วางเต็มความกว้าง
# ใต้ ribbon — API เหมือนเดิม (.set() / .get() / command) จึงใช้แทน
# self.nav_selector ได้โดยไม่ต้องแก้ on_nav_change()
#
# ตัวแปรสำคัญที่ปรับจูนได้:
#   _STRIP_HEIGHT = ความสูงแถบแท็บ (พิกเซล)
#   _TAB_WIDTH    = ความกว้างแต่ละแท็บ (พิกเซล)
# ==============================================================================
import customtkinter as ctk

from ui import theme

_STRIP_HEIGHT = 38
_TAB_WIDTH    = 128


class TabStrip:
    def __init__(self, master, values, command):
        self.command = command
        self._value  = None
        self._tabs   = {}   # name -> (button, underline frame)

        self.frame = ctk.CTkFrame(master, fg_color=theme.BG_CANVAS, corner_radius=0,
                                  height=_STRIP_HEIGHT)
        self.frame.pack_propagate(False)

        for i, name in enumerate(values):
            cell = ctk.CTkFrame(self.frame, fg_color="transparent", corner_radius=0)
            cell.pack(side="left", padx=(12 if i == 0 else 2, 0), pady=(6, 0), fill="y")
            btn = ctk.CTkButton(
                cell, text=name, width=_TAB_WIDTH, height=28, corner_radius=4,
                fg_color="transparent", hover_color=theme.BG_CARD_HOVER,
                text_color=theme.TEXT_SECONDARY, font=ctk.CTkFont(size=13),
                command=lambda n=name: self._on_click(n))
            btn.pack(side="top")
            line = ctk.CTkFrame(cell, width=_TAB_WIDTH, height=3, fg_color="transparent", corner_radius=0)
            line.pack(side="bottom", fill="x")
            self._tabs[name] = (btn, line)

    def pack(self, **kwargs):
        self.frame.pack(**kwargs)

    def get(self):
        return self._value

    def set(self, value):
        """เปลี่ยนแท็บที่ไฮไลต์อยู่ (ไม่เรียก command — เหมือน CTkSegmentedButton.set)"""
        self._value = value
        for name, (btn, line) in self._tabs.items():
            on = (name == value)
            btn.configure(fg_color=theme.BG_PANEL if on else "transparent",
                          text_color=theme.TEXT if on else theme.TEXT_SECONDARY,
                          font=ctk.CTkFont(size=13, weight="bold" if on else "normal"))
            line.configure(fg_color=theme.ACCENT if on else "transparent")

    def _on_click(self, name):
        self.set(name)
        self.command(name)
