# ==============================================================================
# core/evaluation_engine.py — เปรียบเทียบจุดที่คาดหวัง (จาก STEP หรือจากไฟล์
# Schema .json ที่โหลดไว้) กับจุดที่ถูกโพรบจริง (จาก .log ของ OpenBuilds
# Control) + ตรวจจับ setting ที่เปลี่ยนไปตั้งแต่ export + คืนค่า settings
# snapshot กลับเข้ารู (full replace, เรียกอัตโนมัติตอนโหลด schema)
# ==============================================================================
# VERSION: 12
# CHANGE LOG (v11 -> v12):
#   FIX (ผนังเอียง/โค้ง): ใช้ตารางจุดแตะจาก B-Rep ('trig' — core/gcode_generator.py v17) ถ้ามี:
#   ศูนย์กลางลูกบอลที่คาด P(r) = S + s(r)·n, จุดแตะบน CAD = P(r) + r·m(r), จุดวัด = PRB−WCO + r·m(r)
#   (r = Effective Tip ⌀/2, m(r) = ทิศตั้งฉากผิวจริงตรงจุดที่ลูกบอลรัศมี r แตะ)
#   FIX (ระยะเบี่ยง): 'distance_mm' = |ระยะเบี่ยงตามทิศตั้งฉากผิว| (a − e)·m แบบ CMM แทนระยะ 3 มิติ
#   — ผนังตั้งตรงได้ค่าเท่าเดิม ผนังเอียง θ ค่าเดิมโตเกิน 1/cos θ (taper 15° +3.5%, ทรงกลม 45° +41%)
#   เก็บระยะ 3 มิติไว้ที่ 'euclid_mm' และค่ามีเครื่องหมายที่ 'dev' (+ = ผิวจริงลึกเข้าไปในเนื้อกว่า CAD)
#   FEATURE (คาลิเบรตผนังนอก): จุด shape='calib' → result['calibration'] = Effective Tip ⌀ ของรอบนี้
#   (span − ขนาดจริงต่อแกน) และใช้แทนค่าใน Hardware Setting ถ้า use_run_calib (ค่าเริ่มต้น)
#   FEATURE (pretravel='travel'): ทางเลือกแบบจำลองระยะทริก — เครื่องเดินต่อ p = R − r ตามทิศที่โพรบเดิน
#   หลังลูกบอลแตะ (แทนการกดเข้าผิวตามทิศตั้งฉาก) ผนังตรงได้ค่าเท่ากันทุกประการ ต่างกันเฉพาะผนังเอียง
#   (taper 15° ต่าง 0.03 มม., หลุมทรงกลมชั้นลึกต่างได้ 0.3 มม.) — ใช้ข้อมูลจริงตัดสินว่าแบบไหนตรง
#   FEATURE: compensate=False ประเมินแบบไม่ชดเชย (จุดดิบ = ศูนย์กลางลูกบอล เทียบผิว CAD ตรง ๆ)
#   ทุกจุดเก็บ raw_log / wco / cad / dev_nocomp / exp_center / normal — export_results_csv()
# CHANGE LOG (v10 -> v11):
#   FEATURE (Best-fit centre): evaluate_points(best_fit=True) — ต่อรู หาการเลื่อนในระนาบตั้งฉากแกนรู
#   (least squares ของระยะเบี่ยงตามทิศตั้งฉากผิว) ที่ทำให้จุดวัดเข้ากับ CAD ที่สุด แล้วเลื่อนจุดวัดทั้งรู
#   ก่อนประเมิน — แยก "ตำแหน่งรูเยื้อง / ตั้ง zero คลาด" ออกจาก "ขนาด + รูปทรง" แบบ CMM
#   holes[id]['best_fit_offset'] = (dx, dy, dz) ที่เลื่อนจุดวัด (ตำแหน่งรูจริง = CAD − offset)
#   ระยะเบี่ยงในโหมดนี้ = ระยะถึงผิว CAD (รูกลม: |ระยะถึงแกนวงกลม CAD − รัศมี|, อื่น ๆ: ตามทิศตั้งฉากผิว)
#   ไม่ใช่ระยะถึงจุด CAD จุดเดียว — จุดที่เลื่อนแล้วไถลไปตามผนังไม่ถูกนับเป็นความคลาด
# CHANGE LOG (v09 -> v10):
#   ก้านชน: แจ้งเตือนอย่างเดียว — จุดที่สงสัย (p['suspect']) ยังนับผ่าน/ไม่ผ่านและอยู่ใน circle fit
#   ตามปกติ (ผู้ใช้ขอ) result/hole['suspect_points'] = จำนวนจุดที่ค่าอาจคลาดเพราะก้านแตะผนัง
# CHANGE LOG (v08 -> v09):
#   FEATURE (ผนังเอียง): จุดที่มี mx/my/mz (ทิศตั้งฉากผิว — gcode_generator v13) ลูกบอลแตะผนัง
#   ด้วยด้านข้าง/ใต้ลูก: ศูนย์กลางลูกบอลที่คาด = E − r/(m·n)·n, จุดบนผิว = ศูนย์กลาง + r·m
#   (ผนังตรง m = n ได้ผลเท่าเดิม) — expected ที่แสดงเป็นจุดที่ลูกบอลแตะผิวจริง
#   FEATURE (ก้านชน): ต่อ segment เทียบ "ระยะผนังเฉลี่ย" (ค่าเบี่ยงตามทิศโพรบ) ของแต่ละชั้นกับชั้นบน
#   ชั้นที่แคบลงเกิน SHAFT_SHRINK_MM (CAD ไม่ได้แคบลง) → จุดที่แตะก่อนผนังเกินเกณฑ์ = 'suspect'
#   (ก้านโพรบแตะปากรู/ผนังก่อนลูกบอล) ตัดออกจากผ่าน/ไม่ผ่านและ circle fit — นับไว้ที่
#   result['suspect_points'] / hole['suspect_points'] / layer['shaft_suspect']
# CHANGE LOG (v07 -> v08):
#   FEATURE: จุดพื้นก้นรู (shape='floor', layer_idx=-1 — โพรบแนว Z) ประเมินเฉพาะ
#   ความลึก: ระยะ = |(actual - expected) · แกนรู| ไม่นับการเยื้องแนวราบ — เก็บแยกที่
#   holes[id]['floor'] = {expected, actual, depth_error (+ = ลึกกว่า CAD), passed}
#   ไม่อยู่ใน segments/layers (ไม่ปนกับ circle fit) แต่ยังนับรวมผ่าน/ไม่ผ่านของรู
#   build_settings_snapshot() บันทึก measure_floor + ความลึกสูงสุดของรู (CAD) และ
#   apply/diff รองรับ measure_floor (schema เก่าที่ไม่มี key = ปิด)
# CHANGE LOG (v06 -> v07):
#   FEATURE: ชดเชยรัศมีหัวโพรบ (Probe Radius Compensation) — เครื่องรายงานพิกัด
#   "จุดศูนย์กลางลูกบอล" ซึ่งห่างผิวจริงเท่ารัศมีลูกบอลเสมอ evaluate_points() รับ
#   tip_radius_mm แล้วเลื่อนจุดที่วัดได้เข้าหาผนังตามทิศที่โพรบเดิน (nx/ny/nz จาก
#   build_point_map) ก่อนเทียบ — schema เก่าที่ไม่มีทิศจะได้ compensation='unavailable'
#   FEATURE: Least-squares circle fit รายชั้นของรูกลม (core/circle_fit.py) — ได้
#   เส้นผ่าศูนย์กลาง, ระยะเยื้องศูนย์ และความกลม เทียบกับค่าจาก CAD (layer['circle'])
# CHANGE LOG (v05 -> v06):
#   build_settings_snapshot() บันทึก 'screen_rot' (การหมุนจอ) และ
#   diff_snapshots() ถือว่าการหมุนจอที่เปลี่ยนไปตั้งแต่ export = view เปลี่ยน
#   (พิกัด X/Y ของ G-code ตามการหมุนจอแล้ว — ดู gcode_generator.py v08)
# CHANGE LOG (v04 -> v05):
#   FEATURE: ช่องสี่เหลี่ยม (StepPocket) — _hole_fingerprint() ต่อท้ายขนาด
#   ช่อง (กว้าง×ยาว×รัศมีมุม) สำหรับรูทรง 'rect' เท่านั้น fingerprint ของรู
#   กลมเหมือน v04 ทุกตัวอักษร (schema เดิมยังจับคู่ได้) — evaluate_points()
#   ไม่ต้องแก้ เพราะเทียบจุดต่อจุดตาม point map ที่รองรับช่องแล้ว
# CHANGE LOG (v03 -> v04):
#   FIX (bug report — screenshot showed only 1/4 holes matched after
#   "Restore"): build_settings_snapshot()/apply_settings_snapshot() never
#   captured or restored the HOLE-LEVEL `selected_for_inspection` flag —
#   only per-hole layers/points/zigzag (and, for multi-segment holes,
#   each segment's own selected_for_inspection) were saved/restored. The
#   top-level "is this hole even selected for inspection at all" state
#   was completely absent from the snapshot. Combined with
#   core/gcode_export_panel.py only ever passing the currently-SELECTED
#   holes into build_settings_snapshot() (so un-selected holes never
#   appeared in the snapshot at all), a restore could never actually
#   reproduce "which holes were selected at export time" — it could only
#   tweak the layer/point settings of whatever selection happened to
#   already be active in the UI. That mismatch is exactly why the
#   screenshot showed 3 holes as "no data": those holes' selection state
#   (and therefore their presence/absence in the expected-points list)
#   never got restored.
#   FEATURE (user request — "should save ALL current settings, and
#   loading should directly replace the current settings with the new
#   ones"): 
#     - build_settings_snapshot(holes, view_name) now records
#       `selected_for_inspection` explicitly on every hole entry (both
#       single- and multi-segment shapes) — callers are now expected to
#       pass ALL current holes (not just the selected ones) so the
#       snapshot is a COMPLETE picture of "what was configured at export
#       time", not just a fragment of it. See
#       core/gcode_export_panel.py v09's changelog for the matching
#       caller-side change.
#     - apply_settings_snapshot(holes, snapshot, full_replace=True) now
#       also restores `hole.selected_for_inspection` (and, for
#       multi-segment holes, keeps restoring each segment's own
#       selected_for_inspection as before). NEW: when full_replace=True
#       (the default, and the only mode used anywhere in the app now),
#       any hole in `holes` that has NO match in the snapshot is
#       explicitly set to `selected_for_inspection = False` — the
#       loaded schema is treated as the complete, authoritative
#       configuration, so anything it doesn't mention is "not selected"
#       rather than "whatever it happened to be before". Pass
#       full_replace=False to keep the old v03 behavior (only touch
#       matched holes, leave everything else untouched) if ever needed.
#   No change to evaluate_points() or diff_snapshots() — both identical
#   to v03. _hole_fingerprint() matching rule is unchanged.
#
# NOTE เรื่อง key ของรูใน holes dict ที่ evaluate_points() คืนกลับมา:
# ฟังก์ชันนี้ (core/*) ไม่รู้จัก "global index เข้า app.current_holes" เพราะ
# เป็น concept ฝั่ง UI — จึง key ด้วย hole_id (str ของ hole.display_id) แทน
# ผู้เรียก (ui/evaluation_left_panel.py, ui/evaluation_sidebar_panel.py)
# เป็นฝ่าย remap เป็น global-index-keyed dict เองอีกที ก่อนส่งต่อให้
# ui/tabs/evaluation_tab.py วาดผล (ดู contract ในไฟล์นั้น)
#
# ตัวแปรสำคัญที่ปรับจูนได้: ไม่มี (ค่า tolerance ถูกส่งเข้ามาจากภายนอกเสมอ
# ไม่ hardcode ในไฟล์นี้)
# ==============================================================================
import math

import numpy as np

from core.circle_fit import fit_circle_3d
from core.models import clamp_layers, hole_floor_depth

# v09: ชั้นลึกที่ผนัง "เข้ามาใกล้" กว่าชั้นบนเกินนี้ (mm ต่อด้าน, เทียบกับ CAD) → สงสัยก้านโพรบชน
SHAFT_SHRINK_MM = 0.2


def _surface_dir(point):
    """v09: ทิศตั้งฉากผิวผนังเอียง (None = ผนังตรง/schema เก่า)"""
    try:
        return (float(point['mx']), float(point['my']), float(point['mz']))
    except (KeyError, TypeError, ValueError):
        return None


def _probe_dir(point):
    """ทิศที่โพรบเดินเข้าหาผนังของจุดที่คาดหวัง (None ถ้าเป็น schema รุ่นเก่า)"""
    try:
        return (float(point['nx']), float(point['ny']), float(point['nz']))
    except (KeyError, TypeError, ValueError):
        return None


def _layer_circle(points: list, tolerance_mm: float):
    """fit วงกลมให้จุดคาดหวังและจุดที่วัดได้ (ชดเชยแล้ว) ของ 1 layer แล้วเทียบกัน
    คืน None ถ้าไม่ใช่รูกลมหรือจุดไม่พอ — ใช้จุดดิบ (ศูนย์กลางลูกบอล) อีกชุดเพื่อให้
    ผู้ใช้คำนวณขนาดหัวโพรบจริงจาก Ring Gauge ได้ (raw_center_diameter)"""
    if len(points) < 3 or any(p.get('shape', 'circle') != 'circle' for p in points):
        return None
    nom = fit_circle_3d([p['expected'] for p in points])
    mea = fit_circle_3d([p['actual'] for p in points])
    raw = fit_circle_3d([p['actual_raw'] for p in points])
    if nom is None or mea is None:
        return None
    axis = np.asarray(nom['normal'])
    d = np.asarray(mea['center']) - np.asarray(nom['center'])
    d = d - float(np.dot(d, axis)) * axis          # เยื้องศูนย์ในระนาบของชั้นเท่านั้น
    d_err = mea['diameter'] - nom['diameter']
    off = float(np.linalg.norm(d))
    return {
        'n':                   mea['n'],
        'nominal_diameter':    nom['diameter'],
        'measured_diameter':   mea['diameter'],
        'diameter_error':      d_err,
        'nominal_center':      nom['center'],
        'measured_center':     mea['center'],
        'center_offset':       off,
        'roundness':           mea['roundness'],
        'raw_center_diameter': raw['diameter'] if raw else None,
        'passed':              abs(d_err) <= tolerance_mm and off <= tolerance_mm,
    }


def _trig_at(exp, r: float):
    """v12: (s, m) จากตารางจุดแตะ B-Rep ที่รัศมีลูกบอล r (interpolate เชิงเส้น) — None ถ้าไม่มีตาราง"""
    t = exp.get('trig')
    if not t:
        return None
    t = np.asarray(t, dtype=float)
    r = float(np.clip(r, t[0, 0], t[-1, 0]))
    s = float(np.interp(r, t[:, 0], t[:, 1]))
    m = np.array([np.interp(r, t[:, 0], t[:, k]) for k in (2, 3, 4)])
    return s, m / np.linalg.norm(m)


def _table_dist(exp, s_meas: float) -> float:
    """v12: ระยะจากศูนย์กลางลูกบอล (ที่ระยะเดิน s_meas) ถึงผิว CAD — ย้อนตาราง s(r) (s ลดลงเมื่อ r โต)
    นอกช่วงตาราง ต่อเส้นตรงจากปลาย (ค่าลบ = ศูนย์กลางลูกบอลเลยผิว CAD เข้าไปในเนื้อ)"""
    t = np.asarray(exp['trig'], dtype=float)
    r, sv = t[:, 0], t[:, 1]
    if s_meas > sv[0]:
        return float(r[0] + (s_meas - sv[0]) * (r[1] - r[0]) / (sv[1] - sv[0]))
    if s_meas < sv[-1]:
        return float(r[-1] + (s_meas - sv[-1]) * (r[-1] - r[-2]) / (sv[-1] - sv[-2]))
    return float(np.interp(s_meas, sv[::-1], r[::-1]))


def _table_dev(exp, raw, r_tip: float, comp_on) -> float:
    """v12: ระยะเบี่ยงตามทิศตั้งฉากผิวแบบแม่นตรง = รัศมีที่ชดเชย − ระยะจริงจากศูนย์กลางลูกบอลถึงผิว CAD
    ผิวจริงเลื่อนเข้าเนื้อ δ → ลูกบอลรัศมี r ทริกเมื่อห่างผิว CAD r − δ ⇒ δ = r − ระยะ (ถูกแม้ผิวโค้งมาก)
    'travel': ศูนย์กลางลูกบอลจริงตอนเริ่มแตะ = ดิบ − (R − r)·n แล้วเทียบกับ R"""
    n = np.asarray(_probe_dir(exp), dtype=float)
    s_meas = float(np.dot(np.asarray(raw, dtype=float)
                          - np.array([float(exp['sx']), float(exp['sy']), float(exp['sz'])]), n))
    if comp_on == 'travel':
        r_ball = float(exp['trig'][-1][0])
        return r_ball - _table_dist(exp, s_meas - max(0.0, r_ball - r_tip))
    return (r_tip if comp_on else 0.0) - _table_dist(exp, s_meas)


def _contact_pair(exp, raw, r_tip: float, comp_on: bool):
    """(จุดบนผิวตาม CAD, จุดที่วัดได้หลังชดเชยรัศมี, ทิศตั้งฉากผิวที่ใช้วัดระยะเบี่ยง) ของจุดเดียว
    v12: มีตาราง B-Rep → P(r) = S + s(r)·n คือศูนย์กลางลูกบอลที่คาด, e = P(r) + r·m, a = ดิบ + r·m
    ไม่ชดเชย (comp_on False) = ตารางที่ r = 0: e = จุดที่เส้นทางทะลุผิว CAD, a = ศูนย์กลางลูกบอลดิบ
    comp_on == 'travel': ลูกบอลจริง R แตะผิวแล้วเครื่องเดินต่อ p = R − r ตามทิศ n ก่อนทริก →
    e = S + s(R)·n + R·m(R), a = ดิบ − p·n + R·m(R) (ผนังตรงได้เท่ากับแบบปกติ)"""
    ex, ey, ez = float(exp['x']), float(exp['y']), float(exp['z'])
    r = r_tip if comp_on else 0.0
    g = _trig_at(exp, r)
    if g is not None and 'sx' in exp:
        s_, m = g
        n = np.asarray(_probe_dir(exp), dtype=float)
        start = np.array([float(exp['sx']), float(exp['sy']), float(exp['sz'])])
        if comp_on == 'travel':   # v12: ระยะทริกตามทิศที่เดิน
            r_ball = float(exp['trig'][-1][0])
            s_b, m_b = _trig_at(exp, r_ball)
            pre = max(0.0, r_ball - r)
            e = tuple(start + s_b * n + r_ball * m_b)
            a = tuple(np.asarray(raw, dtype=float) - pre * n + r_ball * m_b)
            return e, a, tuple(m_b)
        pexp = start + s_ * n
        e = tuple(pexp + r * m)
        a = tuple(np.asarray(raw, dtype=float) + r * m)
        return e, a, tuple(m)
    m = _surface_dir(exp)
    w = m or _probe_dir(exp) or (0.0, 0.0, 0.0)
    if m is not None and comp_on:   # v09: ผนังเอียง (schema ก่อน v12) — ลูกบอลแตะตามทิศตั้งฉากผิว m
        n = _probe_dir(exp)
        k = r_tip / max(1e-6, m[0] * n[0] + m[1] * n[1] + m[2] * n[2])
        e = (ex - k * n[0] + r_tip * m[0], ey - k * n[1] + r_tip * m[1],
             ez - k * n[2] + r_tip * m[2])                       # จุดที่ลูกบอลแตะผิวจริงตาม CAD
        a = (raw[0] + r_tip * m[0], raw[1] + r_tip * m[1], raw[2] + r_tip * m[2])
    elif comp_on:   # ศูนย์กลางลูกบอล + r × ทิศเข้าหาผนัง = จุดสัมผัสบนผิวงาน
        n = _probe_dir(exp)
        e = (ex, ey, ez)
        a = (raw[0] + r_tip * n[0], raw[1] + r_tip * n[1], raw[2] + r_tip * n[2])
    else:
        e, a = (ex, ey, ez), raw
    return e, a, w


def run_calibration(expected_points: list, actual_points: list, true_size: dict = None,
                    tip_d_max: float = None) -> dict:
    """v12: Effective Tip ⌀ จากจุดแตะผนังนอก (shape='calib') — ต่อแกน: span ระหว่างศูนย์กลาง
    ลูกบอลสองฝั่ง − ขนาดชิ้นงาน (เวอร์เนียร์ใน true_size ถ้ามี ไม่งั้นขนาด CAD ระหว่างจุดผิวสองฝั่ง)
    คืน {} ถ้าไม่มีจุดคาลิเบรต; {'axes': {...}, 'd_eff': ค่าเฉลี่ยแกนที่ใช้ได้ หรือ None}"""
    total = min(len(expected_points), len(actual_points))
    sides = {}
    for i in range(total):
        exp = expected_points[i]
        if exp.get('shape') != 'calib':
            continue
        act = actual_points[i]
        sides.setdefault(exp.get('cal_axis'), {})[int(exp.get('cal_side', 0))] = (
            np.array([float(exp['x']), float(exp['y']), float(exp['z'])]),
            np.array([float(act['x']), float(act['y']), float(act['z'])]))
    if not sides:
        return {}
    axes = {}
    for ax, pair in sorted(sides.items()):
        if -1 not in pair or +1 not in pair:
            continue
        k = 0 if ax == 'X' else 1
        span = float(pair[+1][1][k] - pair[-1][1][k])
        w_cad = float(pair[+1][0][k] - pair[-1][0][k])
        w_true = (true_size or {}).get(ax)
        width = float(w_true) if w_true else w_cad
        d = span - width
        ok = 0.0 < d <= (float(tip_d_max) if tip_d_max else 10.0) + 1e-9
        axes[ax] = {'span': span, 'width_cad': w_cad, 'width_true': float(w_true) if w_true else None,
                    'd_eff': d, 'ok': ok,
                    'centre': 0.5 * float(pair[+1][1][k] + pair[-1][1][k])}   # กึ่งกลางที่วัดได้ (ศูนย์เทียบ X0/Y0)
    good = [v['d_eff'] for v in axes.values() if v['ok']]
    return {'axes': axes, 'd_eff': (sum(good) / len(good)) if good else None}


def _best_fit_shifts(expected_points, actual_points, total: int, r_tip: float, comp_on: bool,
                     circles: dict = None) -> dict:
    """v11: {hole_id: np.array(3)} — การเลื่อนจุดวัดของแต่ละรูในระนาบตั้งฉากแกนรู ที่ทำให้ผลรวม
    (ระยะเบี่ยงตามทิศตั้งฉากผิว)² น้อยที่สุด  แกนรู = ทิศที่ตั้งฉากกับทิศโพรบทุกจุด (SVD)
    รูที่ทิศโพรบไม่ครบ 2 มิติ หรือมีจุดน้อยกว่า 3 จุด ไม่เลื่อน"""
    groups = {}
    for i in range(total):
        exp = expected_points[i]
        n = _probe_dir(exp)
        if n is None or exp.get('shape') in ('floor', 'calib'):
            continue
        groups.setdefault(str(exp.get('hole_id', '?')), []).append(i)
    shifts = {}
    for hid, idx in groups.items():
        if len(idx) < 3:
            continue
        N = np.array([_probe_dir(expected_points[i]) for i in idx], dtype=float)
        _u, sv, vt = np.linalg.svd(N)
        if len(sv) < 2 or sv[1] < 1e-3 * sv[0]:
            continue
        axis = vt[-1]
        rows, rhs = [], []
        for i in idx:
            exp, act = expected_points[i], actual_points[i]
            raw = (float(act['x']), float(act['y']), float(act['z']))
            e, a, w = _contact_pair(exp, raw, r_tip, comp_on)
            w = np.array(w, dtype=float)
            s = float(np.dot(np.subtract(a, e), w))       # ระยะเบี่ยงตามทิศตั้งฉากผิว
            w_lat = w - float(np.dot(w, axis)) * axis    # เลื่อนได้เฉพาะในระนาบตั้งฉากแกนรู
            rows.append(w_lat)
            rhs.append(-s)
        t = np.linalg.lstsq(np.array(rows), np.array(rhs), rcond=None)[0]
        t = t - float(np.dot(t, axis)) * axis
        # รูกลมทุกจุด: ปรับต่อด้วย Gauss-Newton บนระยะถึงวงกลม CAD (เยื้องมากจนเส้นตรงไม่พอ)
        keys = [(hid, int(expected_points[i].get('seg_idx', 0)), int(expected_points[i].get('layer_idx', 0)))
                for i in idx]
        if circles and all(k in circles for k in keys):
            pts = []
            for i in idx:
                act = actual_points[i]
                raw = (float(act['x']), float(act['y']), float(act['z']))
                pts.append(np.array(_contact_pair(expected_points[i], raw, r_tip, comp_on)[1]))
            for _ in range(10):
                J, r = [], []
                for p_, k in zip(pts, keys):
                    c, ax, R = circles[k]
                    v = p_ + t - c
                    v = v - float(np.dot(v, ax)) * ax
                    L = float(np.linalg.norm(v))
                    if L < 1e-9:
                        continue
                    g = v / L
                    J.append(g - float(np.dot(g, axis)) * axis)
                    r.append(L - R)
                if len(J) < 3:
                    break
                dt = np.linalg.lstsq(np.array(J), -np.array(r), rcond=None)[0]
                t = t + dt - float(np.dot(dt, axis)) * axis
                if np.linalg.norm(dt) < 1e-6:
                    break
        shifts[hid] = t
    return shifts


def _nominal_circles(expected_points, total: int, r_tip: float, comp_on: bool) -> dict:
    """v11: {(hole_id, seg_idx, layer_idx): (centre, axis, radius)} ของวงกลม CAD ที่จุดแตะผิว
    แต่ละชั้นของรูกลม (≥ 3 จุด) — ใช้วัดระยะถึงผิวในโหมด best-fit"""
    groups = {}
    for i in range(total):
        exp = expected_points[i]
        if exp.get('shape', 'circle') != 'circle' or _probe_dir(exp) is None:
            continue
        key = (str(exp.get('hole_id', '?')), int(exp.get('seg_idx', 0)), int(exp.get('layer_idx', 0)))
        e, _a, _w = _contact_pair(exp, (0.0, 0.0, 0.0), r_tip, comp_on)
        groups.setdefault(key, []).append(e)
    out = {}
    for key, pts in groups.items():
        if len(pts) < 3:
            continue
        f = fit_circle_3d(pts)
        if f is not None:
            out[key] = (np.asarray(f['center'], dtype=float), np.asarray(f['normal'], dtype=float),
                        f['diameter'] / 2.0)
    return out


def _signed_wall(p):
    """v09: ผนังอยู่ไกลกว่า CAD เท่าไหร่ตามทิศที่โพรบเดิน (− = แตะก่อนถึงผนัง)"""
    n = p.get('dir')
    if n is None:
        return None
    d = p['delta']
    return d[0] * n[0] + d[1] * n[1] + d[2] * n[2]


def _mark_shaft_contacts(layers: list) -> list:
    """v09: layers ของ segment เดียว เรียงบน→ล่าง — ชั้นแรกเป็นฐาน (ลูกบอลยังแตะก่อนก้าน)
    ชั้นลึกที่ค่าเฉลี่ย "ผนังเข้ามาใกล้" กว่าฐานเกิน SHAFT_SHRINK_MM = ก้านชน → จุดในชั้นนั้นที่
    แตะก่อนฐานเกินเกณฑ์ได้ p['suspect'] = True คืนรายการจุดที่ถูกตัด"""
    out = []
    if len(layers) < 2:
        return out
    base = [w for w in (_signed_wall(p) for p in layers[0]['points']) if w is not None]
    if not base:
        return out
    base_mean = sum(base) / len(base)
    for lyr in layers[1:]:
        ws = [(p, _signed_wall(p)) for p in lyr['points']]
        ws = [(p, w) for p, w in ws if w is not None]
        if not ws:
            continue
        mean = sum(w for _p, w in ws) / len(ws)
        lyr['wall_shift'] = mean - base_mean
        if base_mean - mean <= SHAFT_SHRINK_MM:
            continue
        lyr['shaft_suspect'] = True
        for p, w in ws:
            if base_mean - w > SHAFT_SHRINK_MM:
                p['suspect'] = True
                out.append(p)
    return out


# ==============================================================================
# 1) evaluate_points()
# ==============================================================================
def evaluate_points(expected_points: list, actual_points: list, tolerance_mm: float,
                    tip_radius_mm: float = 0.0, best_fit: bool = False, compensate: bool = True,
                    use_run_calib: bool = True, calib_true: dict = None,
                    tip_d_max: float = None, pretravel: str = 'normal') -> dict:
    """จับคู่ EXPECTED[i] กับ ACTUAL[i] ด้วย sequence index แล้วประเมินผลผ่าน/
    ไม่ผ่านของแต่ละจุดเทียบกับ tolerance (mm, ระยะ 3D Euclidean) จากนั้น
    รวมผลขึ้นเป็นโครงสร้าง layer -> segment -> hole -> รายการจุดที่ไม่ผ่านแบบ
    flat (ไม่มีตัวเลข accuracy % ใด ๆ ในผลลัพธ์นี้)

    Parameters
    ----------
    expected_points : list ที่ได้จาก core/gcode_generator.py::build_point_map()
                       หรือจาก core/expected_points_io.py::
                       load_schema_json()['points'] — รูปแบบเดียวกัน
                       แต่ละอันมี hole_id, seg_idx, layer_idx, point_idx, x, y, z
    actual_points   : list ที่ได้จาก core/log_parser.py::parse_openbuilds_log()
                       — แต่ละอันมี x, y, z (เรียงตามลำดับที่เครื่องทำงานจริง)
    tolerance_mm    : ระยะเบี่ยงเบนสูงสุดที่ยังถือว่า "ผ่าน" (mm)
    tip_radius_mm   : v07 — รัศมีหัวโพรบ (ใช้ค่าที่ calibrate แล้วถ้ามี) สำหรับชดเชย
                       จุดที่วัดได้ (ศูนย์กลางลูกบอล) ให้เป็นจุดบนผิวชิ้นงาน — 0 = ไม่ชดเชย
    compensate      : v12 — False = ไม่ชดเชยรัศมี (ดูผลดิบ)
    use_run_calib   : v12 — มีจุดแตะผนังนอก (shape='calib') → ใช้ Effective Tip ของรอบนี้แทน tip_radius_mm
    calib_true      : v12 — {'X': ขนาดจริงเวอร์เนียร์, 'Y': ...} (ไม่ใส่ = ขนาด CAD)
    tip_d_max       : v12 — ⌀ ลูกบอลจริง ใช้ตรวจว่า Effective Tip ⌀ ที่ได้อยู่ในช่วง 0 – ⌀ จริง
    pretravel       : v12 — 'normal' (ทริกเมื่อกดเข้าผิวตามทิศตั้งฉาก = รัศมี r คงที่ แบบ CMM ทั่วไป)
                       หรือ 'travel' (เครื่องเดินต่อ R − r ตามทิศที่โพรบเดิน) — ผนังตรงเท่ากัน

    Returns
    -------
    dict ตาม contract ที่ ui/tabs/evaluation_tab.py คาดหวัง ยกเว้น 'holes'
    ที่ key ด้วย hole_id (str) แทน global index — ผู้เรียกฝั่ง UI ต้อง remap
    เอง (ดู NOTE ด้านบนของไฟล์) key ระดับบนสุดที่มี:
      tolerance_mm, total_points, passed_points, failed_points,
      failed_point_refs, expected_count, actual_count,
      sequence_mismatch, settings_mismatch, holes
    """
    matched = min(len(expected_points), len(actual_points))
    idx_all = [i for i in range(matched) if expected_points[i].get('shape') != 'calib']   # v12
    total_points = len(idx_all)
    passed_points = 0

    # v12: Effective Tip จากผนังนอกของรอบนี้ (ถ้ามีจุดคาลิเบรตใน G-code)
    calibration = run_calibration(expected_points, actual_points, calib_true, tip_d_max)
    r_tip = max(0.0, float(tip_radius_mm or 0.0))
    tip_source = 'setting'
    if use_run_calib and calibration.get('d_eff'):
        r_tip, tip_source = calibration['d_eff'] / 2.0, 'run'

    # v07: ชดเชยรัศมีหัวโพรบ — ทำได้เมื่อ schema มีทิศที่โพรบเดินครบทุกจุด
    has_dirs = total_points > 0 and all(_probe_dir(expected_points[i]) is not None for i in idx_all)
    comp_on = bool(compensate) and r_tip > 0.0 and has_dirs
    if comp_on:   # v12: แบบจำลองระยะทริก ส่งต่อผ่าน comp_on ('normal' / 'travel')
        comp_on = 'travel' if pretravel == 'travel' else 'normal'
    compensation = 'on' if comp_on else ('unavailable' if compensate and r_tip > 0.0 else 'off')

    holes: dict = {}
    # v11: Best-fit centre — เลื่อนจุดวัดทั้งรูก่อนประเมิน (ไม่ตรวจตำแหน่งรู ตรวจขนาด + รูปทรง)
    circles = _nominal_circles(expected_points, matched, r_tip, comp_on) if best_fit else {}
    shifts = (_best_fit_shifts(expected_points, actual_points, matched, r_tip, comp_on, circles)
              if best_fit else {})

    for i in idx_all:
        exp = expected_points[i]
        act = actual_points[i]

        raw = (float(act['x']), float(act['y']), float(act['z']))
        raw_log = raw                                            # v12: ค่า PRB − WCO ก่อนเลื่อน best-fit
        e0, _a0, w0 = _contact_pair(exp, raw_log, 0.0, False)    # v12: ไม่ชดเชย — ศูนย์กลางลูกบอล vs ผิว CAD
        dev_nocomp = float(np.dot(np.subtract(raw_log, e0), w0))
        exact = bool(exp.get('trig')) and 'sx' in exp and _probe_dir(exp) is not None   # v12
        if exact:
            dev_nocomp = _table_dev(exp, raw_log, 0.0, False)
        sh_ = shifts.get(str(exp.get('hole_id', '?')))
        if sh_ is not None:
            raw = (raw[0] + sh_[0], raw[1] + sh_[1], raw[2] + sh_[2])
        (ex, ey, ez), (ax_, ay_, az_), w = _contact_pair(exp, raw, r_tip, comp_on)
        dx, dy, dz = ax_ - ex, ay_ - ey, az_ - ez
        dev = float(dx * w[0] + dy * w[1] + dz * w[2])   # v12: ระยะเบี่ยงตามทิศตั้งฉากผิว (มีเครื่องหมาย)
        if exact:   # v12: ย้อนตาราง B-Rep — แม่นแม้ผนังโค้งมาก/แตะแบบเฉียด (ผนังเรียบได้ค่าเดียวกัน)
            dev = _table_dev(exp, raw, r_tip, comp_on)
        euclid = math.sqrt(dx * dx + dy * dy + dz * dz)
        r_used = r_tip if comp_on else 0.0
        exp_center = (ex - r_used * w[0], ey - r_used * w[1], ez - r_used * w[2])
        if comp_on == 'travel' and exp.get('trig') and 'sx' in exp:   # ศูนย์กลางลูกบอลตอนทริก
            s_b = _trig_at(exp, float(exp['trig'][-1][0]))[0] + max(0.0, float(exp['trig'][-1][0]) - r_tip)
            exp_center = tuple(np.array([float(exp['sx']), float(exp['sy']), float(exp['sz'])])
                               + s_b * np.asarray(_probe_dir(exp), dtype=float))
        extra = {'raw_log': raw_log, 'wco': act.get('wco'), 'cad': e0, 'dev_nocomp': dev_nocomp,
                 'exp_center': exp_center, 'normal': tuple(float(c) for c in w), 'dev': dev,
                 'euclid_mm': euclid}
        is_floor = exp.get('shape') == 'floor'
        if is_floor:   # v08: พื้นก้นรู — เทียบความลึกตามแกนรูอย่างเดียว
            n = _probe_dir(exp) or (0.0, 0.0, -1.0)
            depth_err = dx * n[0] + dy * n[1] + dz * n[2]
            distance = abs(depth_err)
        elif sh_ is not None:   # v11: best-fit — ระยะถึงผิว CAD ไม่ใช่ถึงจุด CAD จุดเดียว
            key = (str(exp.get('hole_id', '?')), int(exp.get('seg_idx', 0)), int(exp.get('layer_idx', 0)))
            circ = circles.get(key)
            if circ is not None:
                v = np.array([ax_, ay_, az_]) - circ[0]
                v = v - float(np.dot(v, circ[1])) * circ[1]
                distance = abs(float(np.linalg.norm(v)) - circ[2])
            else:
                w = _surface_dir(exp) or _probe_dir(exp)
                distance = abs(float(dx * w[0] + dy * w[1] + dz * w[2]))
        else:
            distance = abs(dev)   # v12: ตามทิศตั้งฉากผิว (ผนังตรง = ค่าเดิม)
        passed = distance <= tolerance_mm
        if passed:
            passed_points += 1

        hole_id = str(exp.get('hole_id', '?'))
        seg_idx = int(exp.get('seg_idx', 0))
        lyr_idx = int(exp.get('layer_idx', 0))
        pt_idx  = int(exp.get('point_idx', i))

        hole_entry = holes.setdefault(hole_id, {
            'display_id':    exp.get('hole_id', '?'),
            'total_points':  0,
            'passed_points': 0,
            'max_deviation': 0.0,
            '_segments':     {},
        })
        hole_entry['total_points'] += 1
        if passed:
            hole_entry['passed_points'] += 1
        hole_entry['max_deviation'] = max(hole_entry['max_deviation'], distance)

        if is_floor:   # v08: แยกไว้ระดับรู — ไม่สร้าง layer ปลอม
            hole_entry['floor'] = {
                'expected':    (ex, ey, ez),
                'actual':      (ax_, ay_, az_),
                'actual_raw':  raw,
                'depth_error': depth_err,
                'distance_mm': distance,
                'passed':      passed,
                **extra,
            }
            if not passed:
                hole_entry['_floor_failed'] = True
            continue

        seg_entry = hole_entry['_segments'].setdefault(seg_idx, {
            'seg_idx': seg_idx, '_layers': {},
        })
        layer_entry = seg_entry['_layers'].setdefault(lyr_idx, {
            'layer_idx': lyr_idx, 'max_deviation': 0.0, 'points': [],
        })
        layer_entry['max_deviation'] = max(layer_entry['max_deviation'], distance)
        layer_entry['points'].append({
            'point_idx':   pt_idx,
            'expected':    (ex, ey, ez),
            'actual':      (ax_, ay_, az_),      # v07: หลังชดเชยรัศมีหัวโพรบแล้ว
            'actual_raw':  raw,                  # ค่าดิบจากเครื่อง (ศูนย์กลางลูกบอล)
            'shape':       exp.get('shape', 'circle' if 'nx' in exp else None),
            'delta':       (dx, dy, dz),
            'distance_mm': distance,   # "Offset (mm)" in the UI
            'passed':      passed,
            'dir':         _probe_dir(exp),   # v09: ใช้ตรวจก้านชน
            **extra,                          # v12
        })

    holes_out = {}
    failed_point_refs = []
    suspect_total = 0

    for hole_id, hole_entry in holes.items():
        segments_out = []
        for seg_idx in sorted(hole_entry['_segments'].keys()):
            seg_entry = hole_entry['_segments'][seg_idx]
            layers_out = []
            for lyr_idx in sorted(seg_entry['_layers'].keys()):
                seg_entry['_layers'][lyr_idx]['points'].sort(key=lambda p: p['point_idx'])
            # v10: ก้านโพรบอาจแตะผนัง — แจ้งเตือนเท่านั้น (ไม่ตัดจุดออก)
            for _p in _mark_shaft_contacts([seg_entry['_layers'][k] for k in sorted(seg_entry['_layers'])]):
                suspect_total += 1
                hole_entry['suspect_points'] = hole_entry.get('suspect_points', 0) + 1
            for lyr_idx in sorted(seg_entry['_layers'].keys()):
                layer_entry = seg_entry['_layers'][lyr_idx]
                used = layer_entry['points']
                layer_entry['passed'] = all(p['passed'] for p in used)
                layer_entry['circle'] = _layer_circle(used, tolerance_mm)   # v07
                for p in used:
                    if not p['passed']:
                        failed_point_refs.append({
                            'hole_id':   hole_id,
                            'seg_idx':   seg_idx,
                            'layer_idx': lyr_idx,
                            'point_idx': p['point_idx'],
                            'offset_mm': p['distance_mm'],
                        })
                layers_out.append(layer_entry)
            segments_out.append({'seg_idx': seg_idx, 'layers': layers_out})

        # a hole 'passed' IFF every one of its points passed — a single
        # failing point already fails the whole hole. No percentage-based
        # leniency anywhere here.
        holes_out[hole_id] = {
            'display_id':    hole_entry['display_id'],
            'passed':        (hole_entry['total_points'] > 0 and
                              hole_entry['passed_points'] == hole_entry['total_points']),
            'total_points':  hole_entry['total_points'],
            'passed_points': hole_entry['passed_points'],
            'max_deviation': hole_entry['max_deviation'],
            'suspect_points': hole_entry.get('suspect_points', 0),   # v09
            'best_fit_offset': (tuple(float(v) for v in shifts[hole_id])   # v11
                                if hole_id in shifts else None),
            'segments':      segments_out,
            'floor':         hole_entry.get('floor'),   # v08 — None ถ้าไม่ได้แตะพื้น
        }
        if hole_entry.get('_floor_failed'):
            failed_point_refs.append({'hole_id': hole_id, 'seg_idx': 0, 'layer_idx': -1,
                                      'point_idx': 0, 'offset_mm': hole_entry['floor']['distance_mm']})

    failed_points = total_points - passed_points

    return {
        'tolerance_mm':       tolerance_mm,
        'tip_radius_mm':      r_tip if comp_on else 0.0,   # v07
        'compensation':       compensation,                # 'on' / 'off' / 'unavailable'
        'tip_source':         tip_source,                  # v12: 'run' (ผนังนอกรอบนี้) / 'setting'
        'pretravel':          comp_on or None,             # v12: 'normal' / 'travel' / None (ไม่ชดเชย)
        'calibration':        calibration,                 # v12: {} ถ้า G-code ไม่มีจุดคาลิเบรต
        'calib_points':       matched - total_points,      # v12
        'best_fit':           bool(best_fit),              # v11
        'total_points':       total_points,
        'passed_points':      passed_points,
        'failed_points':      failed_points,
        'failed_point_refs':  failed_point_refs,
        'suspect_points':     suspect_total,               # v10 — ก้านโพรบอาจแตะผนัง (เตือนเท่านั้น)
        'expected_count':     len(expected_points) - (matched - total_points),
        'actual_count':       len(actual_points) - (matched - total_points),
        'sequence_mismatch':  len(expected_points) != len(actual_points),
        'settings_mismatch':  [],   # เติมทีหลังโดยผู้เรียก (diff_snapshots())
        'holes':              holes_out,
    }


def export_results_csv(result: dict, filepath: str) -> None:
    """v12: บันทึกผลรายจุดเป็น CSV — ทั้งค่าดิบ (ไม่ชดเชย) และค่าหลังชดเชยในแถวเดียวกัน
    raw = PRB − WCO (ศูนย์กลางลูกบอล), cad = จุดที่เส้นทางโพรบทะลุผิว CAD,
    dev_nocomp = (raw − cad)·m0 (ถือว่าศูนย์กลางลูกบอลคือผิว), exp_center = ศูนย์กลางลูกบอลที่คาดที่ r,
    comp = raw + r·m (จุดแตะที่วัดได้), cad_contact = จุดแตะตาม CAD, dev = (comp − cad_contact)·m"""
    import csv

    def xyz(v):
        return ["" if v is None else f"{float(c):.4f}" for c in (v if v is not None else (None,) * 3)]

    r = result.get('tip_radius_mm', 0.0)
    cal = result.get('calibration') or {}
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["# log", result.get('log_filename', '')])
        w.writerow(["# compensation", result.get('compensation'), "r_eff (mm)", f"{r:.4f}",
                    "source", result.get('tip_source', 'setting'),
                    "tolerance (mm)", result.get('tolerance_mm'), "best_fit", result.get('best_fit')])
        for ax, v in (cal.get('axes') or {}).items():
            w.writerow([f"# calibration {ax}", "span", f"{v['span']:.4f}", "width CAD", f"{v['width_cad']:.4f}",
                        "width caliper", "" if v['width_true'] is None else f"{v['width_true']:.4f}",
                        "Effective Tip dia", f"{v['d_eff']:.4f}", "ok", v['ok'],
                        "measured centre", f"{v['centre']:.4f}"])
        w.writerow(["hole", "seg", "layer", "point", "shape",
                    "n_x", "n_y", "n_z", "wco_x", "wco_y", "wco_z",
                    "raw_x", "raw_y", "raw_z", "cad_x", "cad_y", "cad_z", "dev_nocomp",
                    "r_used", "m_x", "m_y", "m_z", "exp_centre_x", "exp_centre_y", "exp_centre_z",
                    "comp_x", "comp_y", "comp_z", "cad_contact_x", "cad_contact_y", "cad_contact_z",
                    "dev", "abs_dev", "euclid", "passed"])
        for gi, hole in (result.get('holes') or {}).items():
            hid = hole.get('display_id', gi)
            rows = []
            for seg in hole.get('segments', []):
                for lyr in seg.get('layers', []):
                    for pt in lyr.get('points', []):
                        rows.append((seg['seg_idx'], lyr['layer_idx'], pt))
            if hole.get('floor'):
                rows.append((0, -1, dict(hole['floor'], point_idx=0, shape='floor', dir=None)))
            for seg_idx, lyr_idx, pt in rows:
                w.writerow([hid, seg_idx, lyr_idx, pt.get('point_idx'), pt.get('shape')]
                           + xyz(pt.get('dir')) + xyz(pt.get('wco')) + xyz(pt.get('raw_log'))
                           + xyz(pt.get('cad')) + [f"{pt.get('dev_nocomp', 0.0):+.4f}", f"{r:.4f}"]
                           + xyz(pt.get('normal')) + xyz(pt.get('exp_center'))
                           + xyz(pt.get('actual')) + xyz(pt.get('expected'))
                           + [f"{pt.get('dev', 0.0):+.4f}", f"{pt.get('distance_mm', 0.0):.4f}",
                              f"{pt.get('euclid_mm', 0.0):.4f}", pt.get('passed')])


# ==============================================================================
# 2) Stale-settings guard (§6) — shared by both the live-recompute path and
# the schema-file path
# ==============================================================================
def _hole_fingerprint(hole) -> str:
    """คีย์ที่เสถียรสำหรับระบุ "รูเดียวกัน" ข้ามเวลา — ใช้พิกัด/ขนาดของรู
    ปัดเศษ แทน display_id เพราะ display_id เปลี่ยนได้ทุกครั้งที่มีการ
    เลือก/ยกเลิกเลือกรูใหม่ (ดู ui/main_window.py::_renumber_holes_by_category())
    ใช้ร่วมกันโดย build_settings_snapshot()/diff_snapshots() (การเทียบ) และ
    apply_settings_snapshot() (การคืนค่า) — เกณฑ์จับคู่เดียวกันทั้งสองทาง"""
    sh = getattr(hole, '_step_hole', None)
    if sh is not None:
        ox, oy, oz = sh.open_3d
    else:
        ox = getattr(hole, 'x', 0.0) or 0.0
        oy = getattr(hole, 'y', 0.0) or 0.0
        oz = getattr(hole, 'surface_z', 0.0) or 0.0
    radius = getattr(hole, 'radius', 0.0) or 0.0
    depth  = getattr(hole, 'depth', 0.0) or 0.0
    fp = f"{round(float(ox), 2)}_{round(float(oy), 2)}_{round(float(oz), 2)}_{round(float(radius), 3)}_{round(float(depth), 2)}"
    if getattr(sh, 'shape', 'circle') == 'rect':   # v05
        fp += f"_rect{round(sh.half_u * 2, 3)}x{round(sh.half_v * 2, 3)}r{round(sh.corner_radius, 3)}"
    elif getattr(sh, 'shape', 'circle') == 'channel':
        fp += f"_chan{round(sh.half_len * 2, 3)}x{round(sh.half_v * 2, 3)}"
    return fp


def build_settings_snapshot(holes: list, view_name: str, screen_rot: int = 0) -> dict:
    """จับภาพค่าตั้งค่าการตรวจสอบ "ทั้งหมด" ของทุกรูที่ส่งเข้ามา — v04:
    ผู้เรียกควรส่ง ALL current holes เข้ามา (ไม่ใช่แค่รูที่ selected_for_
    inspection == True) เพื่อให้ snapshot เป็นภาพสมบูรณ์ของการตั้งค่า ณ
    ขณะนั้น รวมถึง "รูไหนถูกเลือกไว้บ้าง" ด้วย ไม่ใช่แค่ค่าปรับจูนของรูที่
    ถูกเลือกอยู่แล้วเท่านั้น (ดู v03 -> v04 changelog ด้านบนไฟล์สำหรับบั๊กที่
    เกิดจากการไม่ทำแบบนี้) — เรียกทั้งตอน export G-code จริง
    (core/gcode_export_panel.py) และตอนโหลดผลตรวจ .log
    (ui/evaluation_left_panel.py, สำหรับสร้าง "live snapshot ปัจจุบัน" ไป
    เทียบกับ snapshot ที่บันทึกไว้ ผ่าน diff_snapshots())

    Returns
    -------
    dict: {
      'view_name': str,
      'holes': {
        <fingerprint>: {
          'display_id': ...,        # เก็บไว้เพื่อรายงานผล ไม่ใช้เทียบ equality
          'multi_segment': bool,
          'selected_for_inspection': bool,   # v04 — hole ทั้งใบถูกเลือกไว้หรือไม่
          # single-segment:
          'layers', 'points_per_layer', 'zigzag_inspection', 'zigzag_degree'
          # multi-segment แทนที่ด้วย:
          'segments': [ {seg_idx, layers, points_per_layer,
                          zigzag_inspection, zigzag_degree,
                          selected_for_inspection}, ... ]
        }, ...
      }
    }
    """
    snapshot = {'view_name': view_name, 'screen_rot': int(screen_rot), 'holes': {}}

    for hole in holes:
        fp = _hole_fingerprint(hole)
        segs = getattr(hole, 'segments', None) or []
        hole_selected = bool(getattr(hole, 'selected_for_inspection', False))   # v04
        sh = getattr(hole, '_step_hole', None)
        depth_info = {   # v08: ความลึกสูงสุดของรูตาม CAD (บันทึกไว้ดูอย่างเดียว — ไม่ใช้เทียบ)
            'measure_floor':  bool(getattr(hole, 'measure_floor', False)),
            'max_depth_mm':   None if sh is None else round(float(sh.depth), 4),
            'floor_depth_mm': None if sh is None or hole_floor_depth(sh) is None
                              else round(float(hole_floor_depth(sh)), 4),
        }

        if segs:
            snapshot['holes'][fp] = {
                'display_id':               getattr(hole, 'display_id', '?'),
                'multi_segment':             True,
                'selected_for_inspection':   hole_selected,   # v04
                'segments': [
                    {
                        'seg_idx':                 getattr(cfg, 'seg_idx', si),
                        'layers':                  cfg.layers,
                        'points_per_layer':         cfg.points_per_layer,
                        'zigzag_inspection':        cfg.zigzag_inspection,
                        'zigzag_degree':            cfg.zigzag_degree,
                        'selected_for_inspection':  cfg.selected_for_inspection,
                    }
                    for si, cfg in enumerate(segs)
                ],
                **depth_info,
            }
        else:
            snapshot['holes'][fp] = {
                'display_id':               getattr(hole, 'display_id', '?'),
                'multi_segment':             False,
                'selected_for_inspection':   hole_selected,   # v04
                'layers':                    hole.layers,
                'points_per_layer':          hole.points_per_layer,
                'zigzag_inspection':         hole.zigzag_inspection,
                'zigzag_degree':              hole.zigzag_degree,
                **depth_info,
            }

    return snapshot


def _segment_settings_differ(old_segs: list, new_segs: list) -> bool:
    if len(old_segs) != len(new_segs):
        return True
    watched_keys = ('layers', 'points_per_layer', 'zigzag_inspection',
                     'zigzag_degree', 'selected_for_inspection')
    for old_seg, new_seg in zip(old_segs, new_segs):
        for key in watched_keys:
            if old_seg.get(key) != new_seg.get(key):
                return True
    return False


def _hole_settings_differ(old_cfg: dict, new_cfg: dict) -> bool:
    if old_cfg.get('multi_segment') != new_cfg.get('multi_segment'):
        return True
    # v04: a hole being selected/unselected entirely is itself a
    # meaningful settings change for the stale-settings banner.
    if old_cfg.get('selected_for_inspection') != new_cfg.get('selected_for_inspection'):
        return True
    if bool(old_cfg.get('measure_floor', False)) != bool(new_cfg.get('measure_floor', False)):   # v08
        return True
    if new_cfg.get('multi_segment'):
        return _segment_settings_differ(
            old_cfg.get('segments', []), new_cfg.get('segments', []))
    watched_keys = ('layers', 'points_per_layer', 'zigzag_inspection', 'zigzag_degree')
    return any(old_cfg.get(key) != new_cfg.get(key) for key in watched_keys)


def diff_snapshots(old_snapshot: dict, new_snapshot: dict) -> list:
    """เทียบ snapshot สองอัน (ตอน export/บันทึกไว้ กับตอนประเมินผลปัจจุบัน)
    คืนรายการ display_id (ตาม new_snapshot — สะท้อนหมายเลขปัจจุบัน) ของรูที่
    มีค่าตั้งค่าเปลี่ยนไป หรือ view ที่ใช้ export เปลี่ยนไป — READ-ONLY เสมอ
    ไม่แก้ไข snapshot ทั้งสองฝั่ง

    หมายเหตุ: รูที่มีอยู่ใน new_snapshot แต่ไม่มีใน old_snapshot (fingerprint
    ไม่ตรงกัน — เช่น geometry เปลี่ยนไปเพราะสลับมุมมอง/regenerate holes)
    จะไม่ถูกนับเป็น "settings mismatch" ในที่นี้ เพราะเป็นคนละปัญหา (geometry
    เปลี่ยน ไม่ใช่แค่ตั้งค่าการตรวจสอบเปลี่ยน) — ถือว่าไม่มีข้อมูลเก่าให้เทียบ"""
    if not old_snapshot or not new_snapshot:
        return []

    old_holes = old_snapshot.get('holes', {})
    new_holes = new_snapshot.get('holes', {})
    view_changed = (old_snapshot.get('view_name') != new_snapshot.get('view_name') or
                    old_snapshot.get('screen_rot', 0) != new_snapshot.get('screen_rot', 0))   # v06

    mismatched = []
    for fp, new_cfg in new_holes.items():
        old_cfg = old_holes.get(fp)
        if old_cfg is None:
            continue
        if view_changed or _hole_settings_differ(old_cfg, new_cfg):
            mismatched.append(new_cfg.get('display_id', '?'))

    return mismatched


# ==============================================================================
# 3) apply_settings_snapshot() — v04: full-replace restore, now including
# the hole-level selected_for_inspection flag
# ==============================================================================
def apply_settings_snapshot(holes: list, snapshot: dict, full_replace: bool = True) -> dict:
    """คืนค่าตั้งค่าการตรวจสอบทั้งหมด (selected_for_inspection ของทั้งรู,
    layers / points_per_layer / zigzag_inspection / zigzag_degree และ
    สำหรับรูหลายระดับเส้นผ่านศูนย์กลาง — selected_for_inspection ต่อ
    segment ด้วย) จาก snapshot กลับเข้า `holes` ที่ตรงกัน (จับคู่ด้วย
    _hole_fingerprint() — เกณฑ์เดียวกับ diff_snapshots()) — MUTATES
    `holes` IN PLACE.

    v04: เรียกโดยตรงทันทีที่โหลดไฟล์ Schema สำเร็จ (ui/evaluation_left_panel.py
    v07's "📂 Load Schema (.json)") — ไม่มีปุ่ม "Restore" แยกต่างหากอีก
    ต่อไป การโหลด = การแทนที่ค่าปัจจุบันทันที ตามที่ผู้ใช้ต้องการ

    Parameters
    ----------
    holes        : list ของ HoleFeature ปัจจุบันทั้งหมด (โดยทั่วไปคือ
                   app.current_holes ทั้งหมด ไม่ใช่แค่รูที่
                   selected_for_inspection — เพื่อให้ทั้งรูที่ snapshot
                   บอกว่า "เลือก" และรูที่ snapshot บอกว่า "ไม่เลือก" ถูก
                   จัดการถูกต้องทั้งคู่)
    snapshot     : dict จาก build_settings_snapshot() (อ่านจาก
                   record['settings_snapshot'] ที่โหลดผ่าน
                   core/expected_points_io.py::load_schema_json())
    full_replace : bool, default True — เมื่อ True (พฤติกรรมเดียวที่ใช้ใน
                   แอปตอนนี้) รูใน `holes` ที่ "ไม่พบคู่" ใน snapshot จะถูก
                   set selected_for_inspection = False ไปด้วย เพราะถือว่า
                   schema ที่โหลดมาคือค่าที่ถูกต้องสมบูรณ์ทั้งหมด ("ไม่มีอยู่
                   ใน schema" = "ไม่ได้ถูกเลือกไว้ตอน export") ตั้งเป็น False
                   เพื่อคงพฤติกรรมเดิม (v03 — แตะเฉพาะรูที่จับคู่ได้ ปล่อย
                   รูอื่นไว้เหมือนเดิม) หากจำเป็นในอนาคต

    Returns
    -------
    dict รายงานผลการคืนค่า: {'matched': int, 'deselected': int,
    'unmatched': int, 'total_snapshot_holes': int}
      'matched'    = จำนวนรูใน `holes` ที่หา fingerprint ตรงใน snapshot
                     เจอและถูกคืนค่าแล้ว (รวมถึง selected_for_inspection)
      'deselected' = จำนวนรูใน `holes` ที่ไม่พบคู่ใน snapshot และ (เมื่อ
                     full_replace=True) ถูกบังคับ selected_for_inspection
                     = False ไปด้วย
      'unmatched'  = จำนวนรูใน snapshot ที่หา fingerprint ตรงใน `holes`
                     ปัจจุบันไม่เจอเลย (เช่น geometry เปลี่ยนไปตั้งแต่
                     export — ไม่ใช่ error แค่ไม่มีอะไรให้คืนค่า)
    """
    snap_holes = snapshot.get('holes', {}) or {}
    matched    = 0
    deselected = 0

    for hole in holes:
        fp  = _hole_fingerprint(hole)
        cfg = snap_holes.get(fp)

        if cfg is None:
            if full_replace:
                if getattr(hole, 'selected_for_inspection', False):
                    deselected += 1
                hole.selected_for_inspection = False
            continue

        matched += 1
        hole.selected_for_inspection = cfg.get('selected_for_inspection',
                                                hole.selected_for_inspection)   # v04
        hole.measure_floor = bool(cfg.get('measure_floor', False))               # v08

        if cfg.get('multi_segment'):
            segs = getattr(hole, 'segments', None) or []
            for seg_cfg in cfg.get('segments', []):
                si = seg_cfg.get('seg_idx')
                if si is None or si >= len(segs):
                    continue   # geometry's segment count changed since export — skip that segment only
                target = segs[si]
                target.layers                  = clamp_layers(seg_cfg.get('layers', target.layers))
                target.points_per_layer        = seg_cfg.get('points_per_layer', target.points_per_layer)
                target.zigzag_inspection       = seg_cfg.get('zigzag_inspection', target.zigzag_inspection)
                target.zigzag_degree           = seg_cfg.get('zigzag_degree', target.zigzag_degree)
                target.selected_for_inspection = seg_cfg.get('selected_for_inspection', target.selected_for_inspection)
        else:
            hole.layers            = clamp_layers(cfg.get('layers', hole.layers))
            hole.points_per_layer  = cfg.get('points_per_layer', hole.points_per_layer)
            hole.zigzag_inspection = cfg.get('zigzag_inspection', hole.zigzag_inspection)
            hole.zigzag_degree     = cfg.get('zigzag_degree', hole.zigzag_degree)

    return {
        'matched':              matched,
        'deselected':           deselected,
        'unmatched':            max(0, len(snap_holes) - matched),
        'total_snapshot_holes': len(snap_holes),
    }
