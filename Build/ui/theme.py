# ==============================================================================
# ui/theme.py — สี / ฟอนต์ / ระยะ ของทั้งโปรแกรม (Design tokens) — Light + Dark
# ==============================================================================
# VERSION: 01
# หน้าที่: รวมค่าสีที่เคย hardcode กระจายอยู่ทุกไฟล์ใน ui/ และ core/ ไว้ที่
# เดียว — ไฟล์อื่นให้ `from ui import theme` แล้วอ้าง theme.BG_CARD ฯลฯ
# แทนการเขียน hex ตรง ๆ (สไตล์ "A · Metrology" ใน mockup)
#
# ทุก token สีเป็นคู่ (light, dark):
#   - widget ของ customtkinter รับคู่นี้ได้ตรง ๆ (fg_color=theme.BG_CARD) และ
#     สลับสีเองเมื่อเรียก ctk.set_appearance_mode()
#   - ของที่ไม่ใช่ customtkinter (matplotlib, tk.Label, tk.Canvas) ต้องแปลง
#     เป็น hex เดี่ยวของโหมดปัจจุบันก่อนด้วย theme.c(theme.BG_CARD)
#
# กติกา:
#   - ปุ่มสี ACCENT = action หลัก 1 อันต่อหน้าจอ (Export, Apply, Generate)
#   - ปุ่มรอง = BTN_SECONDARY, ปุ่มลบ/ล้าง = DANGER (ตัวอักษรขาวทั้งคู่)
#   - *_BG = พื้นจาง ๆ ของสถานะ (ใช้คู่กับตัวอักษร TEXT / *_TEXT)
#   - *_FILL = พื้นเข้มของสถานะ (ใช้คู่กับตัวอักษรขาว)
#
# apply()             — เรียกครั้งเดียวก่อนสร้าง ctk.CTk() (ใน ui/main_window.py)
# apply_matplotlib()  — เรียกตอนเริ่ม และทุกครั้งที่สลับ Light/Dark
#
# สีข้อมูลบนกราฟ (สีแต่ละ layer, marker pass/fail, highlight) ยังอยู่ในไฟล์
# tab ของตัวเอง — ไฟล์นี้คุมเฉพาะ "โครง" UI และพื้นหลัง/ตัวอักษรของกราฟ
# ==============================================================================
import customtkinter as ctk

DEFAULT_MODE = "Light"   # โหมดตอนเปิดโปรแกรม — "Light" หรือ "Dark"

# --- Surfaces -------------------- (light,     dark) --------------------------
BG_CANVAS      = ("#e4e9ee", "#15181c")   # พื้นหลังพื้นที่กราฟ
BG_PANEL       = ("#ffffff", "#23282e")   # sidebar, toolbar, dialog
BG_CARD        = ("#f3f5f7", "#2a3037")   # การ์ด / กล่องข้อมูลบน panel
BG_CARD_HOVER  = ("#e6eaee", "#323941")
BG_INPUT       = ("#ffffff", "#1b1f24")   # ช่องกรอก, กล่องย่อยซ้อนในการ์ด
BORDER         = ("#d5dbe1", "#39414a")
BORDER_STRONG  = ("#c4ccd5", "#4a535e")
SELECT_BG      = ("#e3edf7", "#1f3550")   # แถว/ปุ่มที่ถูกเลือกอยู่
ROW_SELECTED   = ("#c5dcf5", "#2b5a94")   # แถวของ Hole schedule ที่กำลังเลือก

# --- Text ---------------------------------------------------------------------
TEXT           = ("#1c2630", "#e6e9ed")
TEXT_SECONDARY = ("#3a4856", "#c3cad2")   # label ของฟิลด์
TEXT_MUTED     = ("#5b6875", "#9aa5b1")   # คำอธิบาย, หน่วย, hint
TEXT_FAINT     = ("#8a96a3", "#6f7884")   # disabled / ไม่สำคัญ
ON_FILL        = ("#ffffff", "#ffffff")   # ตัวอักษรบนปุ่มสีเข้ม

# --- Actions ------------------------------------------------------------------
ACCENT               = ("#0b5cad", "#2b74c7")   # ปุ่มหลัก (ตัวอักษรขาว)
ACCENT_HOVER         = ("#08457f", "#3a84d6")
ACCENT_TEXT          = ("#0b5cad", "#6fb1f5")   # ลิงก์ / ตัวเลขเน้น / ไอคอนเน้น
BTN_SECONDARY        = ("#5f6b78", "#3a424c")   # ปุ่มรอง (ตัวอักษรขาว)
BTN_SECONDARY_HOVER  = ("#4c5762", "#48515d")
DANGER               = ("#b3261e", "#b8433b")
DANGER_HOVER         = ("#8f1d17", "#9e3730")

# --- Status -------------------------------------------------------------------
OK        = ("#1a7f4b", "#34c38f")
OK_BG     = ("#e3f4ea", "#16261f")
OK_TEXT   = ("#1a7f4b", "#9fe3c6")
OK_FILL   = ("#1a7f4b", "#1e7a55")
WARN      = ("#a15c00", "#f0a53a")
WARN_BG   = ("#fff6e5", "#3a2c14")
WARN_TEXT = ("#8a5200", "#f5c27a")
WARN_FILL = ("#8a5200", "#8a5a12")
ERR       = ("#b3261e", "#f26b5b")
ERR_BG    = ("#fde8e6", "#3d1f1c")
ERR_TEXT  = ("#b3261e", "#f7a197")
ERR_FILL  = ("#b3261e", "#b8433b")

# --- Toolbar icons ------------------------------------------------------------
ICON = ("#3a4856", "#e6e9ed")

# --- Plots (matplotlib) — ต้องผ่าน c() ก่อนส่งให้ matplotlib -------------------
PLOT_FIG  = BG_CANVAS
PLOT_AX   = ("#d3dae1", "#1b1f24")
PLOT_GRID = ("#8a96a3", "#4a5360")

# กราฟ 3D (แท็บ Customization) พื้นมืดเสมอทั้งสองโหมด — สีเส้นทาง/จุดสัมผัสออกแบบ
# มาสำหรับพื้นมืด จึงใช้ค่าเดี่ยว ไม่ต้องผ่าน c()
VIEW3D_BG    = "#1b1f24"
VIEW3D_TEXT  = "#e6e9ed"
VIEW3D_MUTED = "#9aa5b1"

# --- Type & spacing -----------------------------------------------------------
FONT_FAMILY = "Segoe UI"
FONT_MONO   = "Consolas"
RADIUS      = 6
PAD         = 16
GAP         = 8


def is_dark() -> bool:
    return ctk.get_appearance_mode() == "Dark"


def c(token) -> str:
    """แปลง token (light, dark) เป็น hex เดี่ยวของโหมดปัจจุบัน — ใช้กับ
    matplotlib / tk ธรรมดา ที่ไม่รู้จักคู่สีของ customtkinter"""
    if isinstance(token, (tuple, list)):
        return token[1] if is_dark() else token[0]
    return token


def shade(token, factor: float = 0.3):
    """สีตอน "ถูกเลือก" ของการ์ด: โหมดสว่างทำให้เข้มขึ้น, โหมดมืดทำให้สว่างขึ้น"""
    def mix(hex_color, target):
        h = hex_color.lstrip('#')
        rgb = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
        return "#" + "".join(f"{int(v + (target - v) * factor):02x}" for v in rgb)
    light, dark = token if isinstance(token, (tuple, list)) else (token, token)
    return (mix(light, 0), mix(dark, 255))


def apply(mode: str = DEFAULT_MODE):
    """ตั้ง default ของ widget customtkinter ทุกชนิดให้ตรงกับ token ด้านบน
    ต้องเรียกก่อนสร้าง widget ตัวแรก (ก่อน ctk.CTk())"""
    ctk.set_appearance_mode(mode)
    ctk.set_default_color_theme("blue")
    t = ctk.ThemeManager.theme
    p = list   # customtkinter เก็บสีใน theme เป็น list [light, dark]

    t["CTk"]["fg_color"]         = p(BG_PANEL)
    t["CTkToplevel"]["fg_color"] = p(BG_PANEL)

    t["CTkFrame"].update(fg_color=p(BG_PANEL), top_fg_color=p(BG_CARD), border_color=p(BORDER))
    t["CTkScrollableFrame"]["label_fg_color"] = p(BG_CARD)

    t["CTkButton"].update(corner_radius=RADIUS, fg_color=p(ACCENT), hover_color=p(ACCENT_HOVER),
                          border_color=p(BORDER_STRONG), text_color=p(ON_FILL),
                          text_color_disabled=["#d5dbe1", "#8a939e"])
    t["CTkLabel"]["text_color"] = p(TEXT)

    t["CTkEntry"].update(corner_radius=4, fg_color=p(BG_INPUT), border_color=p(BORDER_STRONG),
                         text_color=p(TEXT), placeholder_text_color=p(TEXT_FAINT))
    t["CTkTextbox"].update(fg_color=p(BG_INPUT), border_color=p(BORDER_STRONG), text_color=p(TEXT),
                           scrollbar_button_color=p(BORDER_STRONG),
                           scrollbar_button_hover_color=p(TEXT_FAINT))

    t["CTkCheckBox"].update(corner_radius=4, fg_color=p(ACCENT), hover_color=p(ACCENT_HOVER),
                            border_color=p(TEXT_FAINT), checkmark_color=p(ON_FILL),
                            text_color=p(TEXT), text_color_disabled=p(TEXT_FAINT))
    t["CTkSwitch"].update(fg_color=p(BORDER_STRONG), progress_color=p(ACCENT),
                          button_color=["#ffffff", "#e6e9ed"], button_hover_color=p(ON_FILL),
                          text_color=p(TEXT), text_color_disabled=p(TEXT_FAINT))
    t["CTkRadioButton"].update(fg_color=p(ACCENT), border_color=p(TEXT_FAINT),
                               hover_color=p(ACCENT_HOVER), text_color=p(TEXT),
                               text_color_disabled=p(TEXT_FAINT))
    t["CTkProgressBar"].update(fg_color=p(BG_CARD_HOVER), progress_color=p(ACCENT),
                               border_color=p(BORDER))
    t["CTkSlider"].update(fg_color=p(BORDER_STRONG), progress_color=p(ACCENT),
                          button_color=p(ACCENT), button_hover_color=p(ACCENT_HOVER))

    t["CTkOptionMenu"].update(corner_radius=4, fg_color=p(BTN_SECONDARY),
                              button_color=p(BTN_SECONDARY_HOVER),
                              button_hover_color=p(BTN_SECONDARY_HOVER),
                              text_color=p(ON_FILL), text_color_disabled=p(TEXT_FAINT))
    t["CTkComboBox"].update(corner_radius=4, fg_color=p(BG_INPUT), border_color=p(BORDER_STRONG),
                            button_color=p(BORDER_STRONG), button_hover_color=p(TEXT_FAINT),
                            text_color=p(TEXT), text_color_disabled=p(TEXT_FAINT))
    t["DropdownMenu"].update(fg_color=p(BG_PANEL), hover_color=p(SELECT_BG), text_color=p(TEXT))

    t["CTkScrollbar"].update(button_color=p(BORDER_STRONG), button_hover_color=p(TEXT_FAINT))
    t["CTkSegmentedButton"].update(corner_radius=RADIUS, fg_color=p(BG_CARD_HOVER),
                                   selected_color=p(ACCENT), selected_hover_color=p(ACCENT_HOVER),
                                   unselected_color=p(BTN_SECONDARY),
                                   unselected_hover_color=p(BTN_SECONDARY_HOVER),
                                   text_color=p(ON_FILL), text_color_disabled=p(TEXT_FAINT))

    t["CTkFont"]["family"] = FONT_FAMILY   # load_theme() ยุบเหลือเฉพาะ OS ปัจจุบันแล้ว


def apply_matplotlib():
    """ตั้ง style ของ matplotlib ให้ตรงกับโหมดปัจจุบัน — เรียกตอนเริ่มโปรแกรม
    และทุกครั้งที่สลับ Light/Dark (ก่อนวาดกราฟใหม่)"""
    import matplotlib.pyplot as plt
    plt.style.use('dark_background' if is_dark() else 'default')
    plt.rcParams.update({
        "figure.facecolor":  c(PLOT_FIG),
        "axes.facecolor":    c(PLOT_AX),
        "axes.edgecolor":    c(TEXT_FAINT),
        "axes.labelcolor":   c(TEXT),
        "axes.titlecolor":   c(TEXT),
        "text.color":        c(TEXT),
        "xtick.color":       c(TEXT_MUTED),
        "ytick.color":       c(TEXT_MUTED),
        "grid.color":        c(PLOT_GRID),
        "legend.facecolor":  c(BG_PANEL),
        "legend.edgecolor":  c(BORDER),
        "savefig.facecolor": c(PLOT_FIG),
    })
