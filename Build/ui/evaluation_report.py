# ==============================================================================
# ui/evaluation_report.py — สร้างรายงาน PDF
# ==============================================================================
# สรุปหน้าที่:
#   สร้างรายงานผลตรวจเป็น PDF (A4) ด้วย Matplotlib PdfPages
#
# ไฟล์ที่เกี่ยวข้อง:
#   ใช้งานไฟล์เหล่านี้:
#     - core/evaluation_engine.py — ประเมินจุดวัดเทียบจุดคาดหวัง (ระยะเบี่ยง ⌀ ความกลม PASS/FAIL) (hole_metrics)
#     - core/projector.py — ฉายโมเดล 3D เป็นภาพ 2D ตามมุมมอง (view_rotation_matrix)
#     - core/work_zero.py — ตำแหน่ง Work Zero ของ G-code (machining_origin)
#     - ui/evaluation_left_panel.py — แผงซ้ายแท็บ Evaluation (โหลด log/Schema, Run inspection) (corrections_status)
#     - ui/evaluation_sidebar_panel.py — แผงขวาแท็บ Evaluation (ผลรายรู/ชั้น/จุด) (EvaluationSidebarPanel, _dir_label)
#     - ui/tabs/evaluation_tab.py — แท็บ Evaluation (กราฟผล) (EvaluationTab)
#   ถูกใช้งานโดย:
#     - ui/evaluation_sidebar_panel.py — แผงขวาแท็บ Evaluation (ผลรายรู/ชั้น/จุด) (export_pdf_dialog)
#   ไลบรารีภายนอก: copy, customtkinter, datetime, matplotlib, numpy, os, threading, tkinter, traceback
#
# รายละเอียด:
#   รายงานผลตรวจเป็น PDF (Feature 2 ข้อ 5)
#
#   หน้าที่: สรุป app.evaluation_result เป็นไฟล์ PDF (A4 แนวตั้ง, matplotlib — ไม่ต้องติดตั้งเพิ่ม)
#     หน้า 1  : ข้อมูลการตรวจ (STEP / log / tolerance / การชดเชย) + ผลรวม PASS/FAIL + ตารางสรุปทุกรู
#     ต่อรู   : ตารางทุกจุด (แถวเขียว/แดง, dev มีเครื่องหมาย) + ภาพตัดมองจากบน 1 ภาพต่อ 1 ชั้นที่ตรวจ:
#               หน้าตัด CAD ที่ความลึกของชั้น (ตัด mesh), วงผนัง CAD, จุดที่วัด (ระยะเบี่ยง × k) พร้อมลูกศร
#   สร้างใน thread แยก — ข้อมูลถูกคัดลอกจากแอปก่อนเริ่ม (หน้าจอใช้งานต่อได้ระหว่างสร้าง)
#
#   ตัวแปรที่ปรับได้:
#     ROWS_PER_PAGE   = แถวตารางจุดต่อหน้า
#     SECTIONS_PER_PAGE = ภาพตัดต่อหน้า (2 คอลัมน์)
# ==============================================================================

import datetime
import os
import threading
import tkinter.messagebox as _mb

import numpy as np
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
from matplotlib.patches import Circle

from core.evaluation_engine import hole_metrics

ROWS_PER_PAGE = 34
SECTIONS_PER_PAGE = 4
A4 = (8.27, 11.69)
OK, BAD, CAD, INK, MUTED = "#1a7f4b", "#c62828", "#7a8794", "#111111", "#555555"
OK_BG, BAD_BG = "#e3f4ea", "#fbe3e1"
WARN = "#b26a00"   # คำเตือนการแก้ค่า


def _dir_label(d):
    from ui.evaluation_sidebar_panel import _dir_label as f
    return f(d)


def _snapshot(app):
    """คัดลอกทุกอย่างที่รายงานต้องใช้ (ทำบน main thread)"""
    import copy
    from core.projector import view_rotation_matrix
    from core.work_zero import machining_origin
    from ui.evaluation_sidebar_panel import EvaluationSidebarPanel
    res = getattr(app, 'evaluation_result', None) or {}
    keep = {k: v for k, v in res.items() if not k.startswith('_')}
    res = copy.deepcopy(keep)
    rot = view_rotation_matrix(app.current_view, app.screen_rotation)
    org = machining_origin(app, app.current_view, app.screen_rotation)
    v = np.asarray(app.geo.mesh.vertices, dtype=float) @ rot.T - org
    f = np.asarray(app.geo.mesh.faces).copy()
    tol = float(res.get('tolerance_mm', 0.5) or 0.5)
    holes = []
    for gi, h in enumerate(app.current_holes):
        info = (res.get('holes') or {}).get(gi)
        if info is None or not getattr(h, 'selected_for_inspection', False):
            continue
        floor = EvaluationSidebarPanel._depth_info(h)[0]
        holes.append(dict(gi=gi, name=str(h.display_id), info=info, metrics=hole_metrics(info, tol, floor)))
    pp = app.probe_profile
    from ui.evaluation_left_panel import corrections_status
    corr = corrections_status(app, res)
    return dict(res=res, v=v, f=f, tol=tol, holes=holes, corrections=corr, step=getattr(app, 'loaded_step_filename', None) or "—",
                view=app.current_view, tip=pp.effective_tip_diameter, when=datetime.datetime.now())


def _page(pdf, title=None):
    fig = Figure(figsize=A4, facecolor="white")
    if title:
        fig.text(0.06, 0.965, title, fontsize=14, weight="bold", color=INK, va="top")
    return fig


def _footer(fig, snap, n):
    fig.text(0.06, 0.02, f"3D ProbeCode inspection report · {snap['step']} · {snap['res'].get('log_filename', '')}",
             fontsize=7, color=MUTED)
    fig.text(0.94, 0.02, f"page {n}", fontsize=7, color=MUTED, ha="right")


def _table(ax, header, rows, colors=None, widths=None, fs=7.5):
    ax.set_axis_off()
    t = ax.table(cellText=rows, colLabels=header, loc="upper center", cellLoc="center", colLoc="center",
                 colWidths=widths)
    t.auto_set_font_size(False)
    t.set_fontsize(fs)
    t.scale(1, 1.25)
    for (r, c), cell in t.get_celld().items():
        cell.set_edgecolor("#c9ced4")
        cell.set_text_props(color=INK)
        if r > 0 and colors is None:
            cell.set_facecolor("white")
        if r == 0:
            cell.set_facecolor("#e8eef6"); cell.set_text_props(weight="bold")
        elif colors is not None:
            cell.set_facecolor(colors[r - 1])
    return t


def _nice_scale(max_dev, size):
    from ui.tabs.evaluation_tab import EvaluationTab
    return EvaluationTab._nice_scale(max_dev, size)


def _section_segments(v, f, z):
    """หน้าตัด mesh ที่ระนาบ z = const → ส่วนของเส้น (n, 2, 2) ใน XY (ไม่ต้องใช้ scipy/trimesh.section)"""
    tri = v[f]                                  # (m, 3, 3)
    d = tri[:, :, 2] - z
    cross = (d.min(axis=1) < 0) & (d.max(axis=1) > 0)
    tri, d = tri[cross], d[cross]
    segs = []
    for (a, b) in ((0, 1), (1, 2), (2, 0)):
        da, db = d[:, a], d[:, b]
        hit = (da * db) < 0
        t = np.where(hit, da / np.where(hit, da - db, 1.0), 0.0)
        p = tri[:, a, :2] + t[:, None] * (tri[:, b, :2] - tri[:, a, :2])
        segs.append((hit, p))
    out = []
    for i in range(len(tri)):
        pts = [p[i] for hit, p in segs if hit[i]]
        if len(pts) == 2:
            out.append(pts)
    return np.asarray(out, dtype=float).reshape(-1, 2, 2)


def _style(ax):
    """แกนสีอ่อนเสมอ (ไม่ตามธีมมืดของแอป ที่ตั้ง rcParams ไว้)"""
    ax.set_facecolor("white")
    for sp in ax.spines.values():
        sp.set_color("#9aa3ad")
    ax.tick_params(colors=MUTED, labelsize=6)
    ax.grid(True, color="#d5dae0", alpha=0.8, lw=0.5)


def _draw_section(ax, mesh, lyr, k, tol, lm, name):
    from matplotlib.collections import LineCollection
    _style(ax)
    pts = lyr.get('points', [])
    E = np.array([p['expected'] for p in pts], dtype=float)
    A = np.array([p['actual'] for p in pts], dtype=float)
    M = E + k * (A - E)
    z = float(E[:, 2].mean())
    c = lyr.get('circle')
    cen = np.asarray(c['nominal_center'], dtype=float)[:2] if c else E[:, :2].mean(axis=0)
    rad = (c['nominal_diameter'] / 2) if c else float(np.max(np.linalg.norm(E[:, :2] - cen, axis=1)))
    segs = _section_segments(mesh[0], mesh[1], z)
    if len(segs):
        ax.add_collection(LineCollection(segs, colors=CAD, linewidths=1.2))
    if c:
        ax.add_patch(Circle(cen, rad, fill=False, ec=CAD, lw=0.8, ls=":"))
        mc = np.asarray(c['measured_center'], dtype=float)[:2]
        r_m = c['measured_diameter'] / 2
        t = np.linspace(0, 2 * np.pi, 145)
        ax.plot(cen[0] + (mc[0] - cen[0]) * k + (rad + k * (r_m - rad)) * np.cos(t),
                cen[1] + (mc[1] - cen[1]) * k + (rad + k * (r_m - rad)) * np.sin(t),
                color=OK if lyr.get('passed') else BAD, lw=1.0, ls="--")
    for p, e, m in zip(pts, E, M):
        col = OK if p.get('passed') else BAD
        ax.annotate("", xy=m[:2], xytext=e[:2], arrowprops=dict(arrowstyle="->", color=col, lw=1.0))
        ax.plot(*e[:2], "o", ms=3, color=CAD)
        ax.plot(*m[:2], "o", ms=6, color=col, mec="white", mew=0.6)
        dv = p.get('dev')
        lab = f"{p.get('point_idx', '?')}: {dv:+.3f}" if dv is not None else str(p.get('point_idx', '?'))
        far = m[:2] if np.linalg.norm(m[:2] - cen) >= np.linalg.norm(e[:2] - cen) else e[:2]
        off = far - cen
        off = off / (np.linalg.norm(off) or 1.0)
        ax.annotate(lab, xy=far, xytext=(off[0] * 22, off[1] * 14), textcoords="offset points",
                    fontsize=6.5, color=col, ha="center", va="center", weight="bold")
    span = rad * 1.45 + 1.5
    ax.set_xlim(cen[0] - span, cen[0] + span); ax.set_ylim(cen[1] - span, cen[1] + span)
    ax.set_aspect("equal")
    nf = sum(1 for p in pts if not p.get('passed', True))
    verdict = "PASS" if lyr.get('passed') else f"FAIL {nf} of {len(pts)}"
    circ = (f"\nroundness {lm['roundness']:.3f} mm · margin {lm['circularity']:.0f}%"
            if lm and lm.get('circularity') is not None else "")
    ax.set_title(f"Hole {name} · Layer {lyr.get('layer_idx', 0) + 1} · z {z:.2f} · {verdict}{circ}",
                 fontsize=8, color=OK if lyr.get('passed') else BAD, weight="bold")
    if c:
        ax.text(0.02, 0.02, f"⌀ {c['measured_diameter']:.3f} (CAD {c['nominal_diameter']:.3f}, {c['diameter_error']:+.3f})\n"
                f"centre offset {c['center_offset']:.3f} · roundness {c['roundness']:.3f}" if c.get('roundness') is not None
                else f"⌀ {c['measured_diameter']:.3f} (CAD {c['nominal_diameter']:.3f})",
                transform=ax.transAxes, fontsize=6.5, color=MUTED, va="bottom")


def build_pdf(snap, path):
    mesh = (snap['v'], snap['f'])
    res, tol, holes = snap['res'], snap['tol'], snap['holes']
    n_page = 0
    with PdfPages(path) as pdf:
        # ---------------- page 1: summary
        fig = _page(pdf, "Inspection Report")
        n_fail = sum(1 for h in holes if not h['metrics']['passed'])
        ok = n_fail == 0 and bool(holes)
        fig.text(0.06, 0.925, ("PART PASSES" if ok else "PART FAILS") +
                 f" — {len(holes) - n_fail} of {len(holes)} hole(s) passed · "
                 f"{res.get('total_points', 0) - res.get('passed_points', 0)} of {res.get('total_points', 0)} points outside ±{tol:g} mm",
                 fontsize=12, weight="bold", color=OK if ok else BAD, va="top")
        fig.text(0.06, 0.895, "Rule: a hole fails if any one of its points is outside the tolerance.", fontsize=8,
                 color=MUTED, va="top")
        items, warns = snap.get('corrections') or ([], [])
        meta = [("STEP model", snap['step']), ("View / work zero", snap['view']),
                ("Probe log", res.get('log_filename', '—')),
                ("Expected points", f"{res.get('expected_source_name') or res.get('expected_source', '—')}"),
                ("Tolerance", f"±{tol:g} mm")] + list(items) + [
                ("Report created", snap['when'].strftime("%Y-%m-%d %H:%M"))]
        zo = (res.get('z_offset') or {})
        if zo.get('dz') is not None:
            meta.append(("Z offset estimate", f"{zo['dz']:+.3f} mm" + ("" if zo.get('separable') else
                                                                         " (only if the hole is CAD size)")))
        for i, (a, b) in enumerate(meta):
            fig.text(0.06, 0.86 - i * 0.022, a, fontsize=8.5, color=MUTED, va="top")
            fig.text(0.32, 0.86 - i * 0.022, b, fontsize=8.5, color=INK, va="top")
        yw = 0.86 - len(meta) * 0.022 - 0.008
        for i, w in enumerate(warns):   # การแก้ที่ไม่ได้ใช้ / Best-fit centre
            fig.text(0.06, yw - i * 0.02, "⚠ " + w, fontsize=8.5, color=WARN, weight="bold", va="top")
        y0 = yw - len(warns) * 0.02 - 0.025
        ax = fig.add_axes([0.06, 0.08, 0.88, y0 - 0.08])
        rows, cols = [], []
        for h in holes:
            m = h['metrics']; dp = m['deepest']
            if dp['method'] == 'sphere':
                deep = f"{dp['depth']:.3f} (CAD {dp['cad']:.3f})"
            elif dp['method'] == 'floor':
                deep = f"{dp['depth']:.3f} floor (CAD {dp['cad']:.3f})"
            else:
                deep = f"≥ {dp['depth']:.2f} (CAD {dp['cad']:.2f})" if dp.get('depth') is not None and dp.get('cad') is not None \
                    else "—"
            rows.append([h['name'], "PASS" if m['passed'] else "FAIL", f"{m['failed']} / {m['n']}",
                         f"{m['max_abs']:.3f}" if m['max_abs'] is not None else "—", str(len(m['layers'])),
                         f"{m['roundness_max']:.3f} ({m['circularity_min']:.0f}%)" if m['circularity_min'] is not None
                         else "—", deep])
            cols.append([OK_BG if m['passed'] else BAD_BG] * 7)
        if rows:
            t = _table(ax, ["Hole", "Result", "Points failed", "Max |dev| (mm)", "Layers", "Roundness max",
                            "Deepest point (mm)"], rows, widths=[0.08, 0.1, 0.14, 0.14, 0.09, 0.16, 0.29], fs=8)
            for r in range(1, len(rows) + 1):
                t[r, 0].set_facecolor(cols[r - 1][0]); t[r, 1].set_text_props(weight="bold",
                                                                                color=OK if rows[r - 1][1] == "PASS" else BAD)
                for c in range(7):
                    t[r, c].set_facecolor(cols[r - 1][c])
        fig.text(0.06, 0.06, "Roundness = max − min radius about the least-squares circle (mm). "
                 "Margin = 100 × (1 − roundness / tolerance), worst layer.  Deepest point: sphere fit of the "
                 "measured wall (spherical holes) or the floor touch; '≥' = deepest probed layer when the floor cannot be "
                 "reached from the walls.", fontsize=6.5, color=MUTED, wrap=True)
        n_page += 1; _footer(fig, snap, n_page); pdf.savefig(fig, facecolor="white")

        # ---------------- per hole
        for h in holes:
            info, m = h['info'], h['metrics']
            layers = [l for s in info.get('segments', []) for l in s.get('layers', [])]
            rows, colors = [], []
            for s in info.get('segments', []):
                for lyr in s.get('layers', []):
                    for p in lyr.get('points', []):
                        e, a = p['expected'], p['actual']
                        dv = p.get('dev')
                        rows.append([str(lyr.get('layer_idx', 0) + 1), str(p.get('point_idx', '?')), _dir_label(p.get('dir')),
                                     f"{e[0]:.3f}, {e[1]:.3f}, {e[2]:.3f}", f"{a[0]:.3f}, {a[1]:.3f}, {a[2]:.3f}",
                                     f"{dv:+.3f}" if dv is not None else f"{p.get('distance_mm', 0):.3f}",
                                     "PASS" if p.get('passed') else "FAIL"])
                        colors.append(OK_BG if p.get('passed') else BAD_BG)
            for start in range(0, max(1, len(rows)), ROWS_PER_PAGE):
                fig = _page(pdf, f"Hole {h['name']} — points" + (" (cont.)" if start else ""))
                fig.text(0.06, 0.93, ("PASS" if m['passed'] else "FAIL") +
                         f" — {m['n'] - m['failed']} of {m['n']} points within ±{tol:g} mm · max |dev| "
                         + (f"{m['max_abs']:.3f} mm" if m['max_abs'] is not None else "—"),
                         fontsize=11, weight="bold", color=OK if m['passed'] else BAD, va="top")
                chunk = rows[start:start + ROWS_PER_PAGE]
                ax = fig.add_axes([0.06, 0.08, 0.88, 0.82])
                if chunk:
                    _table(ax, ["Layer", "#", "Dir", "CAD point x, y, z (mm)", "Measured x, y, z (mm)", "Dev (mm)", "Result"],
                           chunk, colors[start:start + ROWS_PER_PAGE], widths=[0.07, 0.05, 0.07, 0.29, 0.29, 0.11, 0.1])
                fig.text(0.06, 0.05, "Dev = signed distance along the surface normal: − = material where the hole should "
                         "be (hole small), + = material missing (hole large).", fontsize=6.5, color=MUTED)
                n_page += 1; _footer(fig, snap, n_page); pdf.savefig(fig, facecolor="white")
            # top-down sections, one per layer
            pts = [p for l in layers for p in l.get('points', [])]
            mx = max((abs(float(p.get('dev') or 0.0)) for p in pts), default=0.0)
            size = np.median([l['circle']['nominal_diameter'] / 2 for l in layers if l.get('circle')] or [5.0])
            k = _nice_scale(mx, float(size))
            lm_of = {(l['seg'], l['layer']): l for l in m['layers']}
            seg_of = {id(l): s.get('seg_idx', 0) for s in info.get('segments', []) for l in s.get('layers', [])}
            for start in range(0, len(layers), SECTIONS_PER_PAGE):
                fig = _page(pdf, f"Hole {h['name']} — top-down section of each layer")
                fig.text(0.06, 0.94, f"Grey = CAD section at the layer depth · dotted = CAD wall circle · small grey dot = "
                         f"CAD point\nbig dot = measured point, arrow = its offset from the CAD point in this plane × {k} "
                         f"(green pass / red fail)\ndashed = measured circle × {k} · label = point #: dev along the "
                         f"surface normal (mm)",
                         fontsize=7.5, color=MUTED, va="top", linespacing=1.5)
                for j, lyr in enumerate(layers[start:start + SECTIONS_PER_PAGE]):
                    r_, c_ = divmod(j, 2)
                    ax = fig.add_axes([0.07 + c_ * 0.47, 0.52 - r_ * 0.44, 0.40, 0.38])
                    if lyr.get('points'):
                        _draw_section(ax, mesh, lyr, k, tol, lm_of.get((seg_of.get(id(lyr), 0), lyr.get('layer_idx', 0))),
                                      h['name'])
                n_page += 1; _footer(fig, snap, n_page); pdf.savefig(fig, facecolor="white")
    return n_page


def export_pdf_dialog(app, button=None):
    """ปุ่ม Export PDF ในแผงผลตรวจ — เลือกที่บันทึก แล้วสร้างใน thread แยก"""
    import customtkinter as ctk
    res = getattr(app, 'evaluation_result', None)
    if not res:
        _mb.showinfo("Export PDF", "No evaluation result yet — load or record a .log first.")
        return
    log_path = res.get('log_path') or ""
    init_dir = os.path.dirname(log_path) if log_path else os.path.expanduser("~")
    stem = os.path.splitext(res.get('log_filename') or "inspection")[0]
    path = ctk.filedialog.asksaveasfilename(title="Save inspection report", initialdir=init_dir,
                                            initialfile=f"{stem}_report.pdf", defaultextension=".pdf",
                                            filetypes=[("PDF", "*.pdf")])
    if not path:
        return
    try:
        snap = _snapshot(app)
    except Exception as e:
        _mb.showerror("Export PDF", f"Could not read the results: {e!r}")
        return
    if button is not None:
        button.configure(state="disabled", text="Exporting…")

    def done(msg, ok):
        if button is not None:
            button.configure(state="normal", text="Export PDF")
        (_mb.showinfo if ok else _mb.showerror)("Export PDF", msg)

    def work():
        try:
            n = build_pdf(snap, path)
            app.root.after(0, lambda: done(f"Saved {n} page(s):\n{path}", True))
        except Exception as e:
            import traceback
            traceback.print_exc()
            err = repr(e)
            app.root.after(0, lambda: done(f"PDF export failed: {err}", False))

    threading.Thread(target=work, daemon=True).start()
