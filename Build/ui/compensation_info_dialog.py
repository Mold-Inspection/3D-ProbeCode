# ==============================================================================
# ui/compensation_info_dialog.py — หน้าต่าง "ค่าชดเชยมาจากไหน" (ปุ่ม ⓘ Details ในแผงขวาของแท็บ Evaluation)
# ==============================================================================
# VERSION: 01
# หน้าที่: แสดงแบบอ่านอย่างเดียว ในกรอบเดียวกับ Hardware Setting (ui/settings_dialog_base.py):
#   Summary       — ชดเชยหรือไม่, r ที่ใช้, มาจากไหน, แบบจำลองระยะทริก, จุดที่คิดจาก B-Rep
#   Effective Tip — ค่าใน Hardware Setting, ผล Set up (Find centre + เวอร์เนียร์), คาลิเบรตผนังนอกของรอบนี้
#   Repeatability — ผลแตะซ้ำต่อผนังจาก Set up ล่าสุด
#   Equations     — สมการที่ใช้กับตัวเลขในหน้า Evaluation (core/evaluation_engine.py v12)
# ข้อมูลมาจาก app.evaluation_result, app.probe_profile และ app.setup_info (ui/hardware_setting_dialog.py v16)
# ==============================================================================
import customtkinter as ctk

from ui import theme
from ui.settings_dialog_base import SettingsDialogBase


def _title(parent, text):
    ctk.CTkLabel(parent, text=text, anchor="w", font=ctk.CTkFont(size=13, weight="bold")).pack(
        fill="x", pady=(10, 4))


def _note(parent, text, color=None):
    ctk.CTkLabel(parent, text=text, anchor="w", justify="left", wraplength=400,
                 font=ctk.CTkFont(size=11), text_color=color or theme.TEXT_MUTED).pack(fill="x", pady=(0, 4))


def _rows(parent, rows):
    """ตาราง 2 คอลัมน์ (หัวข้อ, ค่า)"""
    grid = ctk.CTkFrame(parent, fg_color=theme.BG_CARD, corner_radius=6)
    grid.pack(fill="x", pady=(0, 6))
    for i, (k, v) in enumerate(rows):
        ctk.CTkLabel(grid, text=k, anchor="w", font=ctk.CTkFont(size=11),
                     text_color=theme.TEXT_SECONDARY).grid(row=i, column=0, sticky="w", padx=(10, 12), pady=2)
        ctk.CTkLabel(grid, text=v, anchor="w", justify="left", wraplength=250,
                     font=ctk.CTkFont(family=theme.FONT_MONO, size=11)).grid(row=i, column=1, sticky="w",
                                                                             padx=(0, 10), pady=2)


class CompensationInfoDialog:
    def __init__(self, app):
        self.app = app
        self.dialog = SettingsDialogBase(app.root, title="Tip compensation — where the numbers come from")
        self.dialog.add_category("summary", "Summary", self._build_summary)
        self.dialog.add_category("tip", "Effective Tip", self._build_tip)
        self.dialog.add_category("repeat", "Repeatability", self._build_repeat)
        self.dialog.add_category("eq", "Equations", self._build_equations)

    def show(self):
        self.dialog.show()

    # ------------------------------------------------------------------
    def _result(self):
        return getattr(self.app, 'evaluation_result', None) or {}

    def _build_summary(self, parent):
        res, pp = self._result(), self.app.probe_profile
        R = pp.tip_diameter / 2.0
        if not res:
            _note(parent, "No evaluation result yet — run or load a .log first.", theme.WARN_TEXT)
        comp = res.get('compensation', 'off' if not getattr(self.app, 'evaluation_compensate', True) else '—')
        r = res.get('tip_radius_mm', 0.0) if comp == 'on' else 0.0
        src = {'run': "this run's outer-wall touches", 'setting': "Effective Tip ⌀ in Hardware Setting"}.get(
            res.get('tip_source'), "—")
        pts = res.get('_expected_points') or []
        wall = [p for p in pts if p.get('shape') != 'calib']
        exact = sum(1 for p in wall if p.get('trig'))
        _title(parent, "Compensation used for the numbers on screen")
        _rows(parent, [
            ("Tip compensation", {"on": "ON", "off": "OFF — raw ball centre vs CAD",
                                  "unavailable": "unavailable (old schema without probe directions)"}.get(comp, comp)),
            ("Radius used  r", f"{r:.4f} mm" + (f"   (⌀ {2 * r:.4f})" if r else "")),
            ("Taken from", src if comp == 'on' else "—"),
            ("Real ball  R", f"{R:.4f} mm   (Tip ⌀ {pp.tip_diameter:g})"),
            ("Pre-travel  p = R − r", f"{R - r:.4f} mm" if comp == 'on' else "—"),
            ("Pre-travel model", {"travel": "along the probing direction",
                                  "normal": "along the surface normal (constant r)"}.get(res.get('pretravel'), "—")),
            ("Points from the STEP B-Rep", f"{exact} / {len(wall)}" if wall else "—"),
            ("Best-fit centre", "ON (hole position not checked)" if res.get('best_fit') else "off"),
            ("Tolerance", f"{res.get('tolerance_mm', 0):g} mm" if res else "—"),
        ])
        _note(parent, "Deviation on screen = how far the real surface lies from the CAD surface, measured along "
                      "the surface normal: + = deeper into the material (hole larger / outer wall smaller).")
        _note(parent, "Not compensated (yet): machine squareness, holder stiffness, part clamping, Z0 error "
                      "(on a 15° taper a Z0 error Δz shows as 0.26·Δz).")

    def _build_tip(self, parent):
        res, pp = self._result(), self.app.probe_profile
        info = getattr(self.app, 'setup_info', None)
        _title(parent, "Hardware Setting (used when the run has no outer-wall touches)")
        _rows(parent, [("Tip ⌀ (real ball)", f"{pp.tip_diameter:g} mm"),
                       ("Effective Tip ⌀", f"{pp.effective_tip_diameter:.4f} mm"),
                       ("Double touch", f"F{pp.retouch_feed:g} slow re-touch, back-off {pp.retouch_distance:g} mm"
                        if pp.double_touch else "off")])
        _title(parent, "Set up (Find centre + caliper)")
        if not info:
            _note(parent, "No Set up in this session yet.")
        else:
            rows = [("Time", f"{info['time']:%H:%M:%S}  ({info.get('model') or '?'})" +
                     ("  — re-run, Z0 kept" if info.get('keep_zero') else ""))]
            for a in ("X", "Y"):
                span = info['spans'].get(a)
                true = info['true'].get(a)
                d = info['deff'].get(a)
                rows.append((f"{a}: span − caliper",
                             (f"{span:.4f} − {true:.4f} = {d:.4f} mm" if d is not None else
                              f"span {span:.4f} mm (no caliper size)") if span is not None else "—"))
            after = info.get('eff_after')
            rows.append(("Effective Tip ⌀", f"{info['eff_before']:.4f} → {after:.4f} mm" if after is not None
                         else f"{info['eff_before']:.4f} mm (unchanged)"))
            if info.get('zero'):
                mode, zx, zy = info['zero']
                rows.append(("Work zero set at", f"{mode}  (centre = X{zx:+.3f} Y{zy:+.3f})"))
            _rows(parent, rows)
            _note(parent, "span = distance between ball centres on the two outer walls (mean of the slow "
                          "re-touches). Effective Tip ⌀ = span − caliper size. Assumes steps/mm are right.")
        _title(parent, "This run: outer-wall touches in the G-code")
        axes = (res.get('calibration') or {}).get('axes') or {}
        if not axes:
            _note(parent, "Not in this G-code (tick \"Calibrate tip on outer walls first\" when exporting).")
        else:
            _rows(parent, [(f"{a}: span − size", f"{v['span']:.4f} − {v['width_true'] or v['width_cad']:.4f} "
                                                 f"({'caliper' if v['width_true'] else 'CAD'}) = {v['d_eff']:.4f}"
                            + ("" if v['ok'] else "  ⚠ out of range")) for a, v in axes.items()])

    def _build_repeat(self, parent):
        info = getattr(self.app, 'setup_info', None) or {}
        rep = info.get('rep') or {}
        _title(parent, "Repeatability from the last Set up")
        if not rep:
            _note(parent, "No repeatability data — run Set up (Find centre) with Repeat touches / wall > 0.")
            return
        _note(parent, f"{info.get('repeats')} slow touches per wall at F{info.get('rep_feed', 0):g}. "
                      f"Pass if the range ≤ 0.02 mm.")
        _rows(parent, [(f"wall {k}", f"range {v['range']:.4f}  SD {v['sd']:.4f}  fast overshoot "
                                     f"{v['fast_minus_slow']:+.4f}  {'✔' if v['ok'] else '⚠'}") for k, v in rep.items()])
        _note(parent, "fast overshoot = how much further the first (fast) touch went than the slow ones. "
                      "The inspection uses the slow touch only (double touch).")

    def _build_equations(self, parent):
        _title(parent, "Per point (core/evaluation_engine.py v12)")
        _rows(parent, [
            ("P", "PRB − WCO = ball centre when the probe triggered"),
            ("S, n", "start point and direction of the G38.2 move"),
            ("s(ρ)", "travel at which a ball of radius ρ touches the CAD (from the STEP B-Rep)"),
            ("s_m", "(P − S)·n = travel actually measured"),
            ("d*", "ball-centre distance to CAD: s(d*) = s_m"),
            ("Compensated", "dev = r − d*"),
            ("Not compensated", "dev = − d*   (≈ −r on a perfect part)"),
            ("Travel model", "dev = R − d*(s_m − (R − r))"),
            ("Point shown", "A = P + r·m   (m = surface normal at the touch)"),
        ])
        _note(parent, "Vertical walls: s(ρ) = wall radius − ρ, so dev = (P − E)·n + r — the classic CMM formula. "
                      "Sloped/curved walls are exact because s(ρ) and m come from the real surface.")
        _title(parent, "Effective Tip")
        _rows(parent, [("Per axis", "D_eff = (P₊ − P₋) − W   (W = caliper size)"),
                       ("Used", "r = mean(D_eff) / 2")])


def show_compensation_info(app):
    CompensationInfoDialog(app).show()
