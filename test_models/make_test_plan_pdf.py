# สร้างเอกสาร PDF: แบบชิ้นงานทดสอบ PTB-01 + ขั้นตอนการวัดจริงบนเครื่อง + ตารางบันทึกผล
# ค่าขนาดดึงมาจาก make_probe_test_block.py (แก้ที่นั่นแล้วรันสคริปต์นี้ใหม่)
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Circle, FancyBboxPatch, Rectangle

import make_probe_test_block as blk

OUT = "PTB-01_Real_Measurement_Test.pdf"
PW, PH = 8.27, 11.69                  # A4 (inch)
ML, MR, MT, MB = 0.75, 0.75, 0.8, 0.7
TW = PW - ML - MR
FS = 9.0                              # ขนาดตัวอักษรเนื้อหา
LH = FS * 1.38 / 72                   # ความสูงบรรทัด (inch)
WRAP = 96                             # ตัวอักษรต่อบรรทัดโดยประมาณ
ACCENT = "#1f4e79"


class Doc:
    def __init__(self, pdf):
        self.pdf, self.fig, self.y, self.page = pdf, None, 0.0, 0
        self.new_page()

    # ---------- page handling ----------
    def new_page(self):
        if self.fig is not None:
            self._footer()
            self.pdf.savefig(self.fig)
            plt.close(self.fig)
        self.fig = plt.figure(figsize=(PW, PH))
        self.page += 1
        self.y = PH - MT

    def _footer(self):
        self.fig.text(ML / PW, 0.35 / PH, "PTB-01 Probe Test Block — Real Measurement Test Kit",
                      fontsize=7, color="#777")
        self.fig.text((PW - MR) / PW, 0.35 / PH, f"page {self.page}", fontsize=7,
                      color="#777", ha="right")

    def finish(self):
        self._footer()
        self.pdf.savefig(self.fig)
        plt.close(self.fig)

    def need(self, h):
        if self.y - h < MB:
            self.new_page()

    def text(self, x, y, s, **kw):
        kw.setdefault("fontsize", FS)
        kw.setdefault("va", "top")
        self.fig.text(x / PW, y / PH, s, **kw)

    # ---------- flow elements ----------
    def title(self, s, sub=None):
        self.text(ML, self.y, s, fontsize=18, weight="bold", color=ACCENT)
        self.y -= 0.36
        if sub:
            for ln in textwrap.wrap(sub, 92):
                self.text(ML, self.y, ln, fontsize=10.5, color="#444")
                self.y -= 0.2
            self.y -= 0.08
        self.fig.add_artist(plt.Line2D([ML / PW, (PW - MR) / PW], [self.y / PH] * 2,
                                       color=ACCENT, lw=1.2))
        self.y -= 0.18

    def h1(self, s):
        self.need(0.6)
        self.y -= 0.08
        self.text(ML, self.y, s, fontsize=12.5, weight="bold", color=ACCENT)
        self.y -= 0.3

    def h2(self, s):
        self.need(0.45)
        self.y -= 0.04
        self.text(ML, self.y, s, fontsize=10, weight="bold")
        self.y -= 0.22

    def para(self, s, indent=0.0, prefix="", wrap=WRAP, **kw):
        width = wrap - int(indent * 13)
        lines = textwrap.wrap(s, width - len(prefix)) or [""]
        for i, ln in enumerate(lines):
            self.need(LH)
            if i == 0 and prefix:
                self.text(ML + indent, self.y, prefix, **kw)
            self.text(ML + indent + (0.2 if prefix else 0), self.y, ln, **kw)
            self.y -= LH
        self.y -= 0.04

    def bullets(self, items, indent=0.1, numbered=False):
        for i, it in enumerate(items, 1):
            self.para(it, indent=indent, prefix=f"{i}." if numbered else "•")

    def code(self, lines):
        h = LH * len(lines) + 0.12
        self.need(h)
        self.fig.add_artist(FancyBboxPatch(((ML + 0.1) / PW, (self.y - h + 0.04) / PH),
                                           (TW - 0.2) / PW, h / PH, boxstyle="round,pad=0.003",
                                           fc="#f2f4f7", ec="#c9ced6", lw=0.6,
                                           transform=self.fig.transFigure))
        self.y -= 0.04
        for ln in lines:
            self.text(ML + 0.2, self.y, ln, family="monospace", fontsize=8.3)
            self.y -= LH
        self.y -= 0.12

    def note(self, s, color="#8a4b00", fc="#fff6e5"):
        lines = textwrap.wrap(s, WRAP - 6)
        h = LH * len(lines) + 0.14
        self.need(h)
        self.fig.add_artist(FancyBboxPatch(((ML + 0.05) / PW, (self.y - h + 0.05) / PH),
                                           (TW - 0.1) / PW, h / PH, boxstyle="round,pad=0.003",
                                           fc=fc, ec=color, lw=0.7,
                                           transform=self.fig.transFigure))
        self.y -= 0.04
        for ln in lines:
            self.text(ML + 0.15, self.y, ln, color=color)
            self.y -= LH
        self.y -= 0.12

    def table(self, header, rows, widths, row_h=0.24, fs=8.3, blank_rows=0, head_fc="#dfe8f2"):
        """ตาราง — widths เป็นสัดส่วนของความกว้างหน้า; blank_rows = แถวว่างสำหรับกรอก"""
        total = sum(widths)
        ws = [w / total * TW for w in widths]
        all_rows = [header] + rows + [[""] * len(header)] * blank_rows
        hdr_lines = max(len(str(c).split("\n")) for c in header)
        for r_i, row in enumerate(all_rows):
            n_lines = max(len(str(c).split("\n")) for c in row)
            h = max(row_h, n_lines * fs * 1.3 / 72 + 0.08)
            if r_i == 0:
                h = max(row_h, hdr_lines * fs * 1.3 / 72 + 0.08)
            if self.y - h < MB:
                self.new_page()
                if r_i > 0:                          # หัวตารางซ้ำบนหน้าใหม่
                    self._row(header, ws, max(row_h, hdr_lines * fs * 1.3 / 72 + 0.08), fs, head_fc, True)
            self._row(row, ws, h, fs, head_fc if r_i == 0 else None, r_i == 0)
        self.y -= 0.14

    def _row(self, row, ws, h, fs, fc, bold):
        x = ML
        for w, c in zip(ws, row):
            self.fig.add_artist(Rectangle((x / PW, (self.y - h) / PH), w / PW, h / PH,
                                          fc=fc or "white", ec="#555", lw=0.5,
                                          transform=self.fig.transFigure))
            self.text(x + 0.05, self.y - 0.05, str(c), fontsize=fs,
                      weight="bold" if bold else "normal")
            x += w
        self.y -= h


# ============================================================================
# Drawing page
# ============================================================================
def drawing_page(doc):
    doc.title("Sheet 1 — Part Drawing: PTB-01", "All dimensions in mm. Datum: lower-left-top corner "
              "(X0 Y0 at front-left edge, Z0 = top face).")
    L, W, T = blk.L, blk.W, blk.T
    ax = doc.fig.add_axes([0.10, 0.40, 0.80, 0.44])
    ax.set_aspect("equal")
    ax.axis("off")
    ax.add_patch(Rectangle((0, 0), L, W, fc="#eef2f7", ec="k", lw=1.4))

    def centre_mark(x, y, r):
        ax.plot([x - r - 2, x + r + 2], [y, y], color="#999", lw=0.5, ls=(0, (8, 2, 1, 2)))
        ax.plot([x, x], [y - r - 2, y + r + 2], color="#999", lw=0.5, ls=(0, (8, 2, 1, 2)))

    for name, x, y, d, depth in blk.HOLES:
        ax.add_patch(Circle((x, y), d / 2, fc="white", ec="k", lw=1.1))
        centre_mark(x, y, d / 2)
        ax.annotate(f"{name}  Ø{d:g} H7\n↧ {depth:g}", (x - d / 2 * 0.7, y + d / 2 * 0.7),
                    (x - d / 2 - 4, y + d / 2 + 5), fontsize=7.5, ha="right",
                    arrowprops=dict(arrowstyle="-", lw=0.6))
    name, x, y, d_top, depth_top, d_bot, depth_all = blk.CBORE
    ax.add_patch(Circle((x, y), d_top / 2, fc="white", ec="k", lw=1.1))
    ax.add_patch(Circle((x, y), d_bot / 2, fc="#dde3ea", ec="k", lw=1.0))
    centre_mark(x, y, d_top / 2)
    ax.annotate(f"{name}  Ø{d_top:g} ↧ {depth_top:g}\n      Ø{d_bot:g} H7 ↧ {depth_all:g}",
                (x + 6, y - 6), (x + 12, y - 15), fontsize=7.5,
                arrowprops=dict(arrowstyle="-", lw=0.6))
    name, x, y, lx, wy, r, depth = blk.POCKET
    ax.add_patch(FancyBboxPatch((x - lx / 2 + r, y - wy / 2 + r), lx - 2 * r, wy - 2 * r,
                                boxstyle=f"round,pad={r}", fc="white", ec="k", lw=1.1))
    centre_mark(x, y, 0)
    ax.text(x, y + 1.5, f"{name}  {lx:g} × {wy:g}", ha="center", fontsize=7.5)
    ax.text(x, y - 3.5, f"R{r:g} corners  ↧ {depth:g}", ha="center", fontsize=7.5)

    # ordinate dimensions from datum
    xs = sorted({h[1] for h in blk.HOLES} | {blk.CBORE[1], blk.POCKET[1]} | {L})
    ys = sorted({h[2] for h in blk.HOLES} | {blk.CBORE[2], blk.POCKET[2]} | {W})
    for xv in xs:
        ax.plot([xv, xv], [-2, -9], color="k", lw=0.5)
        ax.text(xv, -12, f"{xv:g}", ha="center", va="top", fontsize=7.5)
    ax.text(0, -12, "0", ha="center", va="top", fontsize=7.5, weight="bold")
    ax.plot([0, 0], [-2, -9], color="k", lw=0.8)
    for yv in ys:
        ax.plot([-2, -9], [yv, yv], color="k", lw=0.5)
        ax.text(-11, yv, f"{yv:g}", ha="right", va="center", fontsize=7.5)
    ax.text(-11, 0, "0", ha="right", va="center", fontsize=7.5, weight="bold")
    ax.plot([-2, -9], [0, 0], color="k", lw=0.8)
    ax.annotate("", (0, W + 7), (L, W + 7), arrowprops=dict(arrowstyle="<->", lw=0.6))
    ax.text(L / 2, W + 8.5, f"{L:g}", ha="center", fontsize=8)
    ax.annotate("", (L + 7, 0), (L + 7, W), arrowprops=dict(arrowstyle="<->", lw=0.6))
    ax.text(L + 8.5, W / 2, f"{W:g}", va="center", rotation=90, fontsize=8)
    ax.text(L / 2, W + 16, f"TOP VIEW   (block thickness {T:g})", ha="center", fontsize=9,
            weight="bold")
    ax.annotate("X+", (14, -26), (0, -26), arrowprops=dict(arrowstyle="->", lw=1), fontsize=8,
                va="center")
    ax.annotate("Y+", (-26, 14), (-26, 0), arrowprops=dict(arrowstyle="->", lw=1), fontsize=8,
                ha="center")
    ax.plot(0, 0, "o", color="red", ms=4)
    ax.text(2, 2, "datum", color="red", fontsize=7)
    ax.plot(L / 2, W / 2, "+", color="#c00", ms=10, mew=1.2)
    ax.text(L / 2 + 2, W / 2 - 4, "work zero for testing\n(Center of object)", color="#c00",
            fontsize=6.5)
    ax.set_xlim(-32, L + 14)
    ax.set_ylim(-32, W + 20)

    doc.y = PH * 0.40 - 0.1
    doc.h2("Feature table")
    rows = [[n, f"{x:g}", f"{y:g}", f"Ø{d:g} H7", f"{dp:g}", "round hole, blind"]
            for n, x, y, d, dp in blk.HOLES]
    n, x, y, d1, dp1, d2, dp2 = blk.CBORE
    rows.append([n, f"{x:g}", f"{y:g}", f"Ø{d1:g} / Ø{d2:g} H7", f"{dp1:g} / {dp2:g}",
                 "counterbore (2 segments)"])
    n, x, y, lx, wy, r, dp = blk.POCKET
    rows.append([n, f"{x:g}", f"{y:g}", f"{lx:g} × {wy:g}, R{r:g}", f"{dp:g}",
                 "rectangular pocket, blind"])
    doc.table(["ID", "X", "Y", "Size", "Depth", "Type"], rows, [0.6, 0.7, 0.7, 2.0, 1.0, 2.6])
    doc.h2("General notes")
    doc.bullets([
        "Material: aluminium 6061-T6 (or 7075 / tool steel). Stock squared on all 6 faces, flatness and "
        "squareness ≤ 0.02. Outside size tolerance ±0.05.",
        "H1–H3 and H4 lower bore: drill, then bore or ream to finish (target H7, roundness ≤ 0.01). The "
        "exact diameters do NOT need to hit nominal — the true size comes from the reference "
        "measurement (section 5).",
        "Break all edges with a chamfer ≤ 0.3 × 45°. No burrs inside the holes. Wash off coolant/oil.",
        f"Pocket corner R{blk.POCKET[5]:g}: finish with an end mill ≤ Ø{2 * blk.POCKET[5] - 2:g}. "
        "Holes and pocket depths ±0.1.",
        "CAD file: test_models/probe_test_block_PTB01.step (generated by make_probe_test_block.py).",
    ])


# ============================================================================
# Content
# ============================================================================
def build():
    with PdfPages(OUT) as pdf:
        d = Doc(pdf)
        info = d.pdf.infodict()
        info["Title"] = "PTB-01 Probe Test Block — Real Measurement Test Kit"

        # ---------------- page 1: overview ----------------
        d.title("PTB-01 Real Measurement Test Kit",
                "Probe test block, calibration and test procedure — Mold Dimensional Deviation "
                "Assessment System, thesis Chapter 4.6")
        d.h1("1. Purpose")
        d.para("This kit gives you a part to machine, a calibration method, and a step-by-step test "
               "procedure to produce the real-machine results the thesis still needs: probe tip "
               "calibration, repeatability, accuracy against a reference instrument, reproducibility "
               "after re-clamping, and measuring time. Every test uses the normal app workflow "
               "(STEP → G-code + Schema → OpenBuilds Control → Log → Evaluation), so the results also "
               "prove the whole system works end to end.")
        d.h1("2. What is in the kit")
        d.table(["Item", "File / location", "Use"], [
            ["Test block PTB-01", "probe_test_block_PTB01.step", "Part to machine and measure (Sheet 1)"],
            ["Ring gauge model", "ring_gauge_D20.step\n(from make_ring_gauge.py)",
             "Load in the app to calibrate the\nEffective Tip Ø"],
            ["Test procedure", "this document, sections 4–8", "What to run and in what order"],
            ["Data sheets", "this document, section 9", "Print and fill in during the tests"],
        ], [1.6, 2.6, 2.4])
        d.h1("3. Equipment needed")
        d.table(["Equipment", "Requirement", "Why"], [
            ["CNC + V6 touch probe", "Stylus 22 mm, ball Ø2 (record actual)", "System under test"],
            ["Ring gauge Ø20", "Class X or better, with certificate\n(any size Ø10–Ø30 works)",
             "Calibrate Effective Tip Ø"],
            ["Reference instrument for holes", "Bore gauge / 3-point internal micrometer\n"
             "(resolution ≤ 0.002), or university CMM", "True diameters of H1–H4"],
            ["Pin gauge set", "Ø7.9–Ø8.1 in 0.01 steps", "True Ø of H3 (small hole)"],
            ["Caliper / height gauge", "Resolution 0.01", "Pocket size, depths, block size"],
            ["Thermometer", "±0.5 °C", "Record room temperature"],
            ["Vise or clamps + parallels", "—", "Hold part and ring gauge rigidly"],
        ], [1.9, 2.6, 2.1])
        d.note("Golden rule: never rotate the probe in the spindle and never change the probe feed rate "
               "between calibration and the tests. Both change the trigger point (pre-travel), so the "
               "calibrated Effective Tip Ø becomes invalid and you must calibrate again.")

        # ---------------- page 2: drawing ----------------
        d.new_page()
        drawing_page(d)

        # ---------------- machining & reference ----------------
        d.new_page()
        d.title("Making and Reference-Measuring the Block")
        d.h1("4. Machining")
        d.bullets([
            "Face and square the stock to 100 × 80 × 25. The outside faces are used to find the work "
            "zero, so they must be flat and square.",
            "Machine all features from the top in one setup. Use a fresh finishing tool for the last pass "
            "in each bore (0.1–0.2 mm radial stock) so walls are smooth and round.",
            "Deburr, wash, and let the part reach room temperature (≥ 1 h) before any measurement.",
            "You may machine it on your own CNC or outsource it. Either way, the reference measurement "
            "below — not the drawing — defines the true size.",
        ], numbered=True)
        d.h1("5. Reference measurement (do this BEFORE probing)")
        d.para("The app compares against CAD nominal, so its deviation = machining error + measuring "
               "error. To judge the measuring system alone you need the true size of each feature, "
               "measured with an instrument that is at least ~4× more accurate than the target "
               "accuracy (0.01–0.02 mm).")
        d.bullets([
            "Measure each round diameter (H1, H2, H3, H4 upper Ø18 and lower Ø10) at the SAME three depths "
            "the app will probe (read them from the Customization tab after section 6.3), in two "
            "directions: along X (0°) and along Y (90°). Record on Data Sheet B.",
            "H3 Ø8: use pin gauges — the largest pin that enters freely = diameter (±0.005).",
            "Pocket P1: length and width with caliper inside jaws or gauge blocks at mid-depth; depth "
            "with depth gauge.",
            "Depths of all features with a depth micrometer or caliper depth rod.",
            "Write down room temperature. Aluminium grows 0.023 µm per mm per °C: a Ø20 hole changes "
            "~0.5 µm per °C, so keep reference and probe measurements within ±2 °C.",
            "If a CMM is available at the university, measure the whole block there — it gives "
            "diameters, centre positions and roundness, which allows the full comparison in section 8.",
        ])
        d.h1("6. Machine and app setup")
        d.h2("6.1 Machine preparation")
        d.bullets([
            "Check backlash compensation in OpenBuilds Control and the anti-backlash nuts. Run the axes "
            "for 10 minutes to warm up before the first test of the day.",
            "Mount the probe and do not rotate it again for the whole test series. Check the stylus is "
            "tight and the ball is clean.",
            "Confirm the probe input works: in the console send  ?  while touching the ball — the status "
            "must show Pn:P.",
        ])
        d.h2("6.2 Probe profile in the app (Hardware Setting → Probe)")
        d.table(["Field", "Value"], [
            ["Tip Diameter Ø", "actual ball size (e.g. 2.0)"],
            ["Stylus Length", "22"],
            ["Min. Wall Clearance", "0.5"],
            ["Effective Tip Ø — calibrated", "0  (until section 7 is done)"],
        ], [2.5, 4.1])
        d.h2("6.3 Probing strategy (use the same for every run)")
        d.table(["Feature", "Layers", "Points / layer", "Zigzag"], [
            ["Ring gauge, H1, H2, H3", "3", "8", "off"],
            ["H4 (each segment)", "3", "8", "off"],
            ["P1", "3", "12", "off"],
        ], [2.6, 1.2, 1.6, 1.2])
        d.bullets([
            "View: Top, screen rotation 0°. Work zero: Center of object (Export Settings).",
            "Probe feed: 100 mm/min, overtravel 0.8, backoff 1.2 (defaults). Keep them for ALL runs.",
            "In the Customization tab check the top layer is ≥ 1.5 mm below the top face (clear of the "
            "chamfer) and the bottom layer ≥ 1.5 mm above the floor.",
            "Evaluation tolerance: 0.05 mm (also re-evaluate at 0.02 and 0.10 for discussion).",
        ])

        # ---------------- zero setting ----------------
        d.new_page()
        d.title("Setting the Work Zero with the Probe")
        d.para("Use 'Center of object' as work zero. Finding a centre by touching two opposite faces "
               "cancels the ball radius and the pre-travel, so X/Y zero does not depend on the probe "
               "calibration. The G-code expects Z0 = top face at the BALL CENTRE.")
        d.h2("A. Square the part to the machine X axis")
        d.bullets([
            "Jog the ball in front of the front face (Y−), about 5 mm below the top, near X = 20 of the "
            "part. Probe toward +Y and note the Y value of the [PRB:...] line.",
            "Repeat near X = 80 (60 mm away). If the two Y values differ by more than 0.02 mm, tap the "
            "part and repeat. (0.02 over 60 mm = 0.02° rotation.)",
        ], numbered=True)
        d.h2("B. X centre — probe the left and right faces")
        d.code([
            "; ball ~5 mm left of the left face, ~5 mm below the top, Y near mid-part",
            "G91 G38.2 X10 F100        ; touch left face  -> note PRB X = X1 (machine coords)",
            "G0 X-2                    ; back off",
            "; lift above the part, jog to ~5 mm right of the right face, lower again",
            "G91 G38.2 X-10 F100       ; touch right face -> note PRB X = X2",
            "G0 X2",
            "; lift, then go to the centre in machine coordinates and set X0",
            "G90 G53 G0 X[(X1+X2)/2]   ; type the computed number",
            "G10 L20 P1 X0",
        ])
        d.para("Bonus cross-check: (X2 − X1) − (block length measured with caliper) = Effective Tip Ø "
               "seen from the outside. It should agree with section 7 within ~0.01 mm.", indent=0.1)
        d.h2("C. Y centre — same with the front and back faces")
        d.code([
            "G91 G38.2 Y10 F100   ; front face -> Y1      ...   G91 G38.2 Y-10 F100   ; back face -> Y2",
            "G90 G53 G0 Y[(Y1+Y2)/2]",
            "G10 L20 P1 Y0",
        ])
        d.h2("D. Z zero — top face, ball centre")
        d.code([
            "; ball above the block centre (solid material at X0 Y0), ~3 mm above the top face",
            "G91 G38.2 Z-10 F100",
            "G10 L20 P1 Z1.000        ; = ball radius (Ø2 ball). Now Z0 = top face at the ball centre",
            "G91 G0 Z10               ; retract",
        ])
        d.note("Always lift Z before moving across the part. The G38.2 distances above are short on "
               "purpose — if the probe does not trigger, GRBL raises an alarm instead of crashing. "
               "Clear it with $X and check the probe input.", color="#7a1010", fc="#fdecec")
        d.para("The same procedure is used for the ring gauge, but the X/Y centre is found from the "
               "INSIDE: touch −X and +X inside the bore, go to the midpoint, touch −Y and +Y, go to the "
               "midpoint, then repeat X once more (the first X chord was not through the centre). "
               "Z0 = top face of the ring.")

        # ---------------- calibration + tests ----------------
        d.new_page()
        d.title("Test Procedure")
        d.h1("7. Calibration — Effective Tip Ø (Data Sheet A)")
        d.bullets([
            "Generate the ring model with the certificate size:  python make_ring_gauge.py 20.003 50 15  "
            "(bore, outer Ø, height of YOUR gauge).",
            "Clamp the ring gauge on parallels, set the work zero at its centre (section 'Setting the "
            "Work Zero', last paragraph).",
            "In the app load ring_gauge_D20.003.step, Top view, select the hole, 3 layers × 8 points, "
            "work zero Center of object, Effective Tip Ø = 0. Export G-code + Schema.",
            "Run it in OpenBuilds Control. Save the log. Repeat the run 3 times without touching anything.",
            "In the Evaluation tab load Schema + each log. For every layer read 'Ball-centre Ø'. Write "
            "the 9 values on Data Sheet A.",
            "Effective Tip Ø = Ring Ø − mean(Ball-centre Ø). Enter it in Hardware Setting → Probe → "
            "Effective Tip Ø and Apply.",
            "Check: re-evaluate the logs — the measured Ø of every layer should now equal the ring Ø "
            "within ±0.005. If one direction is always worse, note the lobing (see Roundness).",
        ], numbered=True)
        d.h1("8. Tests on PTB-01")
        d.h2("Test 1 — Repeatability (Data Sheet C)")
        d.bullets([
            "Clamp PTB-01, set work zero (Center of object). Select only H1. Export.",
            "Run the same program 10 times in a row without touching the part or the machine. Save 10 logs.",
            "Evaluate each log (same Schema). Record measured Ø, centre offset and roundness of each "
            "layer.",
            "Result: standard deviation s of each quantity. Repeatability = 2s (≈95 %). "
            "Target: 2s ≤ 0.02 mm (probe spec 0.01 + machine).",
        ], numbered=True)
        d.h2("Test 2 — Accuracy vs reference (Data Sheet D)")
        d.bullets([
            "Select all 5 features (H1–H4, P1). Export one program. Run it 5 times. Save 5 logs.",
            "For each round feature/segment and layer: mean measured Ø over the 5 runs.",
            "Error = mean measured Ø − reference Ø (Data Sheet B, same depth). "
            "Target after calibration: |error| ≤ 0.03 mm.",
            "Also record the app's per-point max offset vs CAD and the pass/fail verdict at tolerance "
            "0.05 — then check whether the verdict agrees with the reference (if the reference itself is "
            "> 0.05 from nominal, the app SHOULD fail that feature).",
            "P1 pocket: record max offset per layer; compare the measured walls with the caliper width "
            "(qualitative — the app has no pocket size fit yet).",
        ], numbered=True)
        d.h2("Test 3 — Reproducibility / re-setup (Data Sheet E)")
        d.bullets([
            "Unclamp the part, re-clamp it in a slightly different place, square it, set the work zero "
            "again from scratch. Run the full program once. Do this 3 times.",
            "Compare the diameters with Test 2 (diameter should not change much) and the centre positions "
            "(these show the work-zero setting error).",
        ], numbered=True)
        d.h2("Test 4 — Measuring time (Data Sheet F)")
        d.bullets([
            "Time each stage: app setup → export, work-zero setting, machine run, evaluation. "
            "Compare with measuring the same features by hand (bore gauge + caliper).",
        ])
        d.h2("Optional Test 5 — Deliberate error")
        d.bullets([
            "Shift the work zero by +0.10 mm in X (G10 L20 P1 X-0.1 at the zero point) and run H1 once. "
            "The centre offset must show ≈0.10 mm and the diameter must stay the same — proves the "
            "evaluation separates position error from size error.",
        ])

        # ---------------- analysis ----------------
        d.h1("Analysis and reporting")
        d.code([
            "mean        x_mean = Σ xi / n",
            "std. dev.   s  = sqrt( Σ (xi − x_mean)² / (n − 1) )",
            "repeatability  = 2·s                       (Test 1, ~95 % of repeated readings)",
            "bias / error   = x_mean − x_ref                 (Test 2)",
            "expanded uncertainty (simple)  U ≈ 2·sqrt( s1² + s3² + u_ref² )",
            "      s1 = Test 1 std. dev., s3 = Test 3 std. dev., u_ref = reference instrument std. unc.",
        ])
        d.bullets([
            "Thesis Ch. 4.6 tables = Data Sheets A, C, D, E, F (mean ± s). Plot measured − reference "
            "per feature as a bar chart with ±U error bars.",
            "Ch. 4.7 discussion: compare bias of the large (Ø20) vs small (Ø8) hole — a size-dependent "
            "error points to tip calibration; a constant centre shift points to work zero; high "
            "roundness on a gauge points to probe lobing or backlash.",
            "Agree the target values (0.02 / 0.03 mm) with the advisor before testing.",
        ])

        # ---------------- data sheets ----------------
        d.new_page()
        d.title("9. Data Sheets", "Date: ____________   Operator: ________________   Room temp: ______ °C   "
                "Probe feed: ______ mm/min")
        d.h2("A. Tip calibration — ring gauge   (Ring Ø cert: ____________   Ball Ø nominal: ______)")
        d.table(["Run", "Layer 1\nBall-centre Ø", "Layer 2\nBall-centre Ø", "Layer 3\nBall-centre Ø",
                 "Run mean"], [["1", "", "", "", ""], ["2", "", "", "", ""], ["3", "", "", "", ""],
                               ["Mean", "", "", "", ""]],
                [0.8, 1.5, 1.5, 1.5, 1.3])
        d.para("Effective Tip Ø = Ring Ø − mean = ____________")
        d.para("Check after entering: measured Ø   L1 _______   L2 _______   L3 _______")
        d.h2("B. Reference measurements   (instrument: ________________________)")
        d.table(["Feature", "Nominal", "Depth\nlayer", "Ø at 0°", "Ø at 90°", "Mean Ø (ref)"],
                [[f, n, l, "", "", ""] for f, n in
                 [("H1", "Ø20"), ("H2", "Ø12"), ("H3", "Ø8"), ("H4 top", "Ø18"), ("H4 bottom", "Ø10")]
                 for l in ("L1", "L2", "L3")] +
                [["P1 length", "34", "mid", "", "—", ""], ["P1 width", "18", "mid", "", "—", ""]],
                [1.2, 0.9, 0.8, 1.2, 1.2, 1.3], row_h=0.22)

        d.new_page()
        d.h2("C. Test 1 — Repeatability, H1 (10 runs, part not touched)")
        d.table(["Run", "Ø L1", "Ø L2", "Ø L3", "Centre off. L2", "Roundness L2", "Max offset"],
                [[str(i), "", "", "", "", "", ""] for i in range(1, 11)] +
                [["Mean", "", "", "", "", "", ""], ["s", "", "", "", "", "", ""],
                 ["2s", "", "", "", "", "", ""]],
                [0.7, 1.0, 1.0, 1.0, 1.3, 1.3, 1.1], row_h=0.22)
        d.h2("D. Test 2 — Accuracy (5 runs, all features)   tolerance used: ______")
        d.table(["Feature / layer", "Run 1", "Run 2", "Run 3", "Run 4", "Run 5", "Mean", "s",
                 "Ref Ø", "Error"],
                [[f"{f} {l}"] + [""] * 9 for f in ("H1", "H2", "H3", "H4 top", "H4 bot")
                 for l in ("L1", "L2", "L3")] +
                [["P1 max off."] + [""] * 9, ["Verdict (P/F)"] + [""] * 9],
                [1.35, 0.7, 0.7, 0.7, 0.7, 0.7, 0.7, 0.6, 0.7, 0.7], row_h=0.21, fs=7.8)

        d.new_page()
        d.h2("E. Test 3 — Reproducibility (re-clamp + new work zero each time)")
        d.table(["Feature (L2)", "Setup 1 Ø", "Setup 2 Ø", "Setup 3 Ø", "s (Ø)", "Centre X,Y\nsetup 1",
                 "Centre X,Y\nsetup 2", "Centre X,Y\nsetup 3"],
                [[f, "", "", "", "", "", "", ""] for f in ("H1", "H2", "H3", "H4 top", "H4 bot")],
                [1.1, 0.85, 0.85, 0.85, 0.7, 1.05, 1.05, 1.05], row_h=0.3)
        d.h2("F. Test 4 — Time")
        d.table(["Stage", "Run 1 (min)", "Run 2 (min)", "Run 3 (min)", "Mean"],
                [["App: load STEP → export", "", "", "", ""], ["Set work zero", "", "", "", ""],
                 ["Machine run (all features)", "", "", "", ""], ["Evaluation", "", "", "", ""],
                 ["TOTAL (system)", "", "", "", ""],
                 ["Manual (bore gauge + caliper)", "", "", "", ""]],
                [2.6, 1.0, 1.0, 1.0, 1.0], row_h=0.26)
        d.h2("G. Notes / problems")
        for _ in range(8):
            d.need(0.3)
            d.fig.add_artist(plt.Line2D([ML / PW, (PW - MR) / PW], [(d.y - 0.25) / PH] * 2,
                                        color="#aaa", lw=0.5))
            d.y -= 0.3
        d.finish()
    print("saved", OUT)


if __name__ == "__main__":
    build()
