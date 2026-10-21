# ==============================================================================
# ui/centre_check_dialog.py — ถามก่อนรันตรวจรูจากแท็บ Evaluation ว่าตั้ง X0 Y0 Z0
# (Find centre) ให้ชิ้นงานนี้แล้วหรือยัง
# ==============================================================================
# VERSION: 01
# ขึ้นทุกครั้งที่กด Run จนกว่าผู้ใช้จะติ๊ก "ไม่ต้องแสดงหน้านี้อีก" (จำใน settings.json
# section "prompts" → skip_centre_check) — ข้อความบอกด้วยว่าไฟล์ CAD นี้เพิ่งโหลดเข้ามา
# และยังไม่ได้รัน Find centre (app.centre_done ไม่ตรงกับไฟล์ที่โหลดอยู่) หรือรันไปแล้วเมื่อไหร่
#
# ask_centre_ready(app) คืน "run" / "find_centre" / None (ยกเลิก)
# ==============================================================================
import customtkinter as ctk

from core import user_settings
from ui import theme

_SECTION = "prompts"
_KEY = "skip_centre_check"


def centre_done_for_current(app):
    """เวลา (datetime) ที่ Find centre สำเร็จกับไฟล์ CAD ที่โหลดอยู่ตอนนี้ หรือ None"""
    done = getattr(app, 'centre_done', None) or {}
    if done.get('model') and done.get('model') == getattr(app, 'loaded_step_filepath', None):
        return done.get('time')
    return None


def ask_centre_ready(app):
    if (user_settings.get(_SECTION, {}) or {}).get(_KEY):
        return "run"
    when = centre_done_for_current(app)
    name = getattr(app, 'loaded_step_filename', None) or "this part"
    if when is None:
        head = "⚠ Find centre has not been run for this CAD file yet"
        body = (f"{name} was just loaded and X0 Y0 Z0 have not been set with Find centre "
                f"(Hardware Setting → Work Zero) since then.\n\n"
                f"The G-code assumes the work zero is exactly at the point it was exported for. "
                f"A wrong zero sends the probe into the part.")
        color = theme.WARN_TEXT
    else:
        head = f"Find centre was run for this CAD file at {when:%H:%M}"
        body = ("Is the part still in the same place and the zero unchanged "
                "(no re-clamping, no Set Zero since)?")
        color = theme.TEXT

    top = ctk.CTkToplevel(app.root)
    top.title("Work zero check")
    top.resizable(False, False)
    top.transient(app.root)
    result = {"value": None}

    ctk.CTkLabel(top, text=head, font=ctk.CTkFont(size=14, weight="bold"), text_color=color,
                 wraplength=420, justify="left").pack(anchor="w", padx=20, pady=(18, 6))
    ctk.CTkLabel(top, text=body, font=ctk.CTkFont(size=12), wraplength=420,
                 justify="left").pack(anchor="w", padx=20, pady=(0, 12))
    skip_var = ctk.BooleanVar(value=False)
    ctk.CTkCheckBox(top, text="ไม่ต้องแสดงหน้านี้อีก (Don't show this again)", variable=skip_var,
                    font=ctk.CTkFont(size=12)).pack(anchor="w", padx=20, pady=(0, 14))

    def close(value):
        result["value"] = value
        if skip_var.get() and value is not None:
            saved = user_settings.get(_SECTION, {}) or {}
            saved[_KEY] = True
            user_settings.save_section(_SECTION, saved)
        top.grab_release()
        top.destroy()

    row = ctk.CTkFrame(top, fg_color="transparent")
    row.pack(fill="x", padx=20, pady=(0, 18))
    ctk.CTkButton(row, text="Run Find centre first", fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
                  command=lambda: close("find_centre")).pack(side="left", padx=(0, 8))
    ctk.CTkButton(row, text="Zero is set — Run", fg_color=theme.BTN_SECONDARY,
                  hover_color=theme.BTN_SECONDARY_HOVER,
                  command=lambda: close("run")).pack(side="left", padx=(0, 8))
    ctk.CTkButton(row, text="Cancel", width=80, fg_color="transparent", border_width=1,
                  text_color=theme.TEXT, command=lambda: close(None)).pack(side="right")
    top.protocol("WM_DELETE_WINDOW", lambda: close(None))

    top.update_idletasks()
    x = app.root.winfo_rootx() + (app.root.winfo_width() - top.winfo_width()) // 2
    y = app.root.winfo_rooty() + (app.root.winfo_height() - top.winfo_height()) // 3
    top.geometry(f"+{max(0, x)}+{max(0, y)}")
    top.lift()
    top.focus_force()
    top.grab_set()
    app.root.wait_window(top)
    return result["value"]
