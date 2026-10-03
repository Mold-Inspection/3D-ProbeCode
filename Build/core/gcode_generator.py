# core/gcode_generator.py
# VERSION: 11
# CHANGE LOG (v10 -> v11):
#   build_point_map() เพิ่ม nx/ny/nz (ทิศที่โพรบเดินเข้าหาผนัง) และ shape ต่อจุด —
#   core/evaluation_engine.py ใช้ชดเชยรัศมีหัวโพรบและ fit วงกลมรายชั้น (G-code ไม่เปลี่ยน)
# CHANGE LOG (v09 -> v10):
#   FEATURE: รูกลมที่ผนังมีช่วงเปิด (blocked_dirs: ปากร่อง, รูซ้อนกัน, รอยบาก — วัดจริง
#   ใน core/step_extractor.py::_wall_gaps) — circle_layer_angles() หมุนชุดจุดทั้ง layer
#   ไปมุมที่ห่างช่องเปิดที่สุด ถ้ายังไม่พ้นจึงเลื่อนทีละจุด และจุดที่ไม่มีผนังให้แตะจริง ๆ
#   จะถูกตัดออก (G-code, Schema, preview ตรงกันเพราะใช้ _layer_contacts() ตัวเดียว)
#   contact_plan_report() สรุปผลให้แผง Properties และหน้า Export แจ้งผู้ใช้
# CHANGE LOG (v08 -> v09):
#   FEATURE: Work zero ที่เลือกได้ (core/work_zero.py) — generate_gcode() /
#   build_point_map() / transform_hole_feature_for_machining() รับ `origin`
#   (ตำแหน่งจุด zero ในพิกัดเครื่อง) แล้วลบออกจากทุก "ตำแหน่ง" (ไม่ใช่ทิศทาง)
#   suggest_safe_z() รับ zero_z; generate_gcode() รับ zero_note สำหรับหัวไฟล์
#   ค่าเริ่มต้น origin=None / zero_note=None = ผลลัพธ์เหมือน v08 ทุกตัวอักษร
# CHANGE LOG (v07 -> v08):
#   FIX: พิกัด X/Y ของ G-code และ expected points (Evaluation) ไม่ตามปุ่ม
#   Rotate บนจอ และมุมมอง Left/Right หมุนต่างจากจอ 90° — apply_view_transform()
#   ใช้เมทริกซ์เดียวกับจอแล้ว (core/projector.py::view_rotation_matrix) และ
#   build_point_map()/generate_gcode() รับ screen_rot เพิ่ม (ค่าเริ่มต้น 0 —
#   Top/Bottom/Front/Back ที่ไม่หมุนจอให้ผลเหมือน v07 ทุกตัวอักษร)
# CHANGE LOG (v06 -> v07):
#   FEATURE: ช่องสี่เหลี่ยม (StepPocket, shape == 'rect') — จุดสัมผัสผนังของ
#   แต่ละ layer ถูกคำนวณผ่าน _layer_contacts() ที่เดียว ใช้ร่วมกันทั้ง
#   build_point_map() และ generate_gcode() (ลำดับจุดตรงกันเป๊ะเหมือนเดิม)
#     - รูกลม: เหมือน v06 ทุกประการ (เริ่มที่จุดศูนย์กลาง เดินออกตามรัศมี) —
#       ข้อความ G-code ของรูกลมไม่เปลี่ยนแม้แต่บรรทัดเดียว
#     - ช่องสี่เหลี่ยม: จุดกระจายบนผนังตรงทั้ง 4 ด้าน (core/models.py::
#       rect_wall_contacts()) — เดินไปจุดเริ่มบนเส้นกึ่งกลางช่องก่อน
#       ("; approach") แล้ว G38.2 ตั้งฉากเข้าหาผนัง; zigzag = เลื่อน
#       ตำแหน่งจุดตามแนวผนัง (degree/360 ของระยะห่างระหว่างจุดต่อ layer)
#   transform_hole_feature_for_machining() แปลง u_dir ของช่องด้วย
# CHANGE LOG (v05 -> v06):
#   FEATURE (PLAN_machine-z-height-and-padding-calculation.md, Step 4):
#   new function suggest_padding_height(machine_profile, probe_profile) —
#   computes a suggested riser/padding height (mm) to place under the
#   workpiece so the probe tip can physically reach it within the
#   machine's downward Z travel range. Formula (see PLAN doc for full
#   derivation from the machine's physical layout):
#     tip_clearance_at_top   = z_height - stylus_holder_height - stylus_length
#     tip_position_at_bottom = tip_clearance_at_top - z_travel
#     suggested_padding      = max(0.0, tip_position_at_bottom)
#   Reads core/machine_profile.py v02's new `z_height` field together with
#   core/probe_profile.py v02's new `stylus_holder_height` field (both
#   added earlier in the same plan) and the existing `stylus_length` /
#   `z_travel`. Pure function, no side effects — mirrors suggest_safe_z()
#   in shape/spirit (a "propose a good default from known geometry"
#   helper), but reads machine/probe PROFILES instead of mesh geometry.
#   No fail-safe / bounds validation here by explicit instruction (e.g.
#   no warning if the result would exceed z_height) — deferred to a
#   future phase.
#
#   FEATURE: GCodeSettings gained a new `padding_height: float = 0.0`
#   field (optional — defaults to "no padding assumed" so existing
#   callers/tests that don't pass it are unaffected). generate_gcode()'s
#   header comment block now always reports the padding value assumed
#   for that export, e.g.:
#     "; NOTE: assumes workpiece is raised by 12.50 mm padding (riser plate)"
#   This is comment-only — no change to any coordinate math, G38.2
#   targets, or point_map output. build_point_map() is untouched.
import re
import numpy as np
import copy  # ต้อง import copy เพื่อใช้ในการจำลองพิกัด

from core.hole_ordering import order_holes_nearest_neighbor, split_step_ready
from core.models import rect_wall_contacts

class GCodeSettings:
    """Plain settings container consumed by generate_gcode()."""
    def __init__(self, safe_z: float, entry_clearance: float = 2.0,
                 probe_feedrate: float = 100.0, overtravel: float = 0.8,
                 backoff: float = 1.2, padding_height: float = 0.0):
        self.safe_z          = float(safe_z)
        self.entry_clearance = float(entry_clearance)
        self.probe_feedrate  = float(probe_feedrate)
        self.overtravel      = float(overtravel)
        self.backoff         = float(backoff)
        self.padding_height  = float(padding_height)   # v06 — riser height assumed under the workpiece (mm), informational only

def suggest_safe_z(mesh, margin: float = 10.0, view_name: str = "Top",
                   zero_z: float = 0.0) -> float:
    """
    เสนอค่า Safe Z โดยคำนวณจากจุดที่สูงที่สุดของ Bounding Box 
    หลังจากจำลองการพลิกชิ้นงาน (Transform) ตามมุมมองปัจจุบันแล้ว
    """
    b_min, b_max = mesh.bounds
    
    # สร้างพิกัดมุมทั้ง 8 ของกล่อง Bounding Box 
    corners = [
        np.array([x, y, z])
        for x in (b_min[0], b_max[0])
        for y in (b_min[1], b_max[1])
        for z in (b_min[2], b_max[2])
    ]
    
    # จับมุมทั้ง 8 มาหมุนตาม View ที่กำลังเลือกอยู่
    transformed_corners = [apply_view_transform(c, view_name) for c in corners]
    
    # หาค่า Z ที่สูงที่สุดจากด้านที่ถูกหงายขึ้นมา
    max_z = max(c[2] for c in transformed_corners)
    
    # v09: zero_z = ความสูงของจุด Work zero ในพิกัดเครื่อง (0 = mesh centroid เดิม)
    return float(max_z) - float(zero_z) + margin

# ---------------------------------------------------------------------
# v06: เสนอค่า Padding Height ใต้ชิ้นงาน จากข้อมูล machine/probe profile
# ---------------------------------------------------------------------
def suggest_padding_height(machine_profile, probe_profile) -> float:
    """คำนวณความสูง padding (แผ่นรอง) พื้นฐานที่ควรใช้ใต้ชิ้นงาน โดยเทียบ
    ระยะที่ปลายโพรบจะไปถึง ณ จุดต่ำสุดของการเดินแกน Z กับพื้น — ถ้าปลายโพรบ
    ยังลอยอยู่เหนือพื้นแม้ Z จะเดินลงมาสุดระยะ (z_travel) แล้ว ระยะที่เหลือ
    นั้นคือความสูง padding ที่ต้องรองใต้ชิ้นงานเพื่อให้ปลายโพรบไปถึงผิวงานได้
    ไม่มีการตรวจสอบ fail-safe ใด ๆ ในฟังก์ชันนี้ (เช่น ไม่เตือนถ้า padding
    ที่แนะนำมากเกินกว่า z_height จะรองรับได้จริง) — ตามคำสั่งชัดเจนว่ายังไม่
    ต้องใส่ระบบกันพลาดในเฟสนี้ (ดู PLAN_machine-z-height-and-padding-
    calculation.md)

    Parameters
    ----------
    machine_profile : core.machine_profile.MachineProfile — ต้องมี
                       .z_height (พื้นถึงใต้ก้นแกน Z ตอน home) และ .z_travel
                       (ระยะเดินสูงสุดแกน Z)
    probe_profile   : core.probe_profile.ProbeProfile — ต้องมี
                       .stylus_holder_height และ .stylus_length

    Returns
    -------
    float : ความสูง padding ที่แนะนำ (mm) — ไม่ติดลบ (clamp ที่ 0.0)
    """
    tip_clearance_at_top = (float(machine_profile.z_height)
                             - float(probe_profile.stylus_holder_height)
                             - float(probe_profile.stylus_length))
    tip_position_at_bottom = tip_clearance_at_top - float(machine_profile.z_travel)
    return max(0.0, tip_position_at_bottom)

# ---------------------------------------------------------------------
# ระบบแปลงพิกัด 3D เพื่อจำลองการ "พลิกชิ้นงาน" ตามมุมมอง
# ---------------------------------------------------------------------
def apply_view_transform(pt, view_name, screen_rot: int = 0):
    """แปลงพิกัด 3D เพื่อตั้งชิ้นงานให้ด้านที่ต้องการหงายขึ้นด้านบน (เข้าหาโพรบ Z+)
    v08: ใช้เมทริกซ์เดียวกับจอ (core/projector.py::view_rotation_matrix) และรวม
    การหมุนจอ (screen_rot) — X/Y ของ G-code จึงตรงกับที่เห็นบนจอเสมอ (เดิม
    Left/Right หมุนต่างจากจอ 90° และไม่สนใจปุ่ม Rotate เลย)"""
    from core.projector import view_rotation_matrix
    return view_rotation_matrix(view_name, screen_rot) @ np.asarray(pt, dtype=float)

def transform_hole_feature_for_machining(hf_orig, view_name, screen_rot: int = 0, origin=None):
    """Deep copy รูและแปลงพิกัดทั้งหมดตามมุมมอง (+ การหมุนจอ) ก่อนส่งไปเขียน G-code
    v09: origin = ตำแหน่งจุด Work zero ในพิกัดเครื่อง (core/work_zero.py) — ลบออก
    จาก "ตำแหน่ง" ทุกจุด (open/deep) แต่ไม่ลบจาก "ทิศทาง" (axis, u_dir)"""
    hf = copy.deepcopy(hf_orig)
    if hf._step_hole:
        sh = hf._step_hole
        org = np.zeros(3) if origin is None else np.asarray(origin, dtype=float)
        tf  = lambda p: apply_view_transform(p, view_name, screen_rot)   # ทิศทาง: หมุนอย่างเดียว
        pos = lambda p: tf(p) - org                                       # ตำแหน่ง: หมุนแล้วเลื่อนตาม zero
        sh.open_3d = pos(sh.open_3d)
        sh.deep_3d = pos(sh.deep_3d)
        sh.axis    = tf(sh.axis)
        if getattr(sh, 'shape', 'circle') in ('rect', 'channel'):   # ทิศด้านยาวของช่อง/ร่อง
            sh.u_dir = tf(sh.u_dir)
        if getattr(sh, 'blocked_dirs', None):   # ทิศปากร่องที่วิ่งเข้ารูนี้ (ห้ามวางจุดโพรบ)
            sh.blocked_dirs = [(tuple(tf(dv)), half) for dv, half in sh.blocked_dirs]
        for seg in getattr(sh, 'segments', []):
            seg.open_3d = pos(seg.open_3d)
            seg.deep_3d = pos(seg.deep_3d)

    return hf

# ---------------------------------------------------------------------
def _orthonormal_basis(axis_vec):
    """Return (unit_axis, u, v)"""
    axis = np.array(axis_vec, dtype=float)
    norm = np.linalg.norm(axis)
    if norm < 1e-9:
        axis = np.array([0.0, 0.0, 1.0])
    else:
        axis = axis / norm
    arbitrary = np.array([0.0, 0.0, 1.0]) if abs(axis[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    u = np.cross(axis, arbitrary)
    u_norm = np.linalg.norm(u)
    u = u / u_norm if u_norm > 1e-9 else np.array([1.0, 0.0, 0.0])
    v = np.cross(axis, u)
    return axis, u, v

def _raw_layers_for_hole(hole_feature):
    sh = hole_feature._step_hole
    is_multi = bool(getattr(hole_feature, 'segments', None))
    layers = []

    if is_multi:
        for seg_idx, (seg, cfg) in enumerate(zip(sh.segments, hole_feature.segments)):
            if not getattr(cfg, 'selected_for_inspection', True):
                continue   

            axis, u, v = _orthonormal_basis(np.array(seg.deep_3d) - np.array(seg.open_3d))
            o = np.array(seg.open_3d)
            d = np.array(seg.deep_3d)
            t_vals = np.linspace(0.0, 1.0, cfg.layers + 2)[1:-1]
            for local_idx, t in enumerate(t_vals):
                center = o + t * (d - o)
                r      = seg.radius_at(t)
                offset = (np.radians(local_idx * cfg.zigzag_degree)
                         if cfg.zigzag_inspection else 0.0)
                layers.append(dict(
                    seg_idx=seg_idx, center=center, radius=r,
                    axis=axis, u=u, v=v, angle_offset=offset,
                    points_n=cfg.points_per_layer,
                    blocked=getattr(sh, 'blocked_dirs', None)))
    else:
        axis, u, v = _orthonormal_basis(np.array(sh.deep_3d) - np.array(sh.open_3d))
        if getattr(sh, 'shape', 'circle') in ('rect', 'channel'):
            # v07: ฐาน u/v ของช่องสี่เหลี่ยม/ร่องต้องตรงกับแนวผนังจริง
            u = np.array(sh.u_dir, dtype=float)
            u = u - float(np.dot(u, axis)) * axis
            u /= np.linalg.norm(u)
            v = np.cross(axis, u)
        o = np.array(sh.open_3d)
        d = np.array(sh.deep_3d)
        n_layers = hole_feature.layers
        use_zz   = getattr(hole_feature, 'zigzag_inspection', False)
        deg      = getattr(hole_feature, 'zigzag_degree', 45.0)
        t_vals   = np.linspace(0.0, 1.0, n_layers + 2)[1:-1]
        for idx, t in enumerate(t_vals):
            center = o + t * (d - o)
            r      = sh.radius_at(t)
            offset = np.radians(idx * deg) if use_zz else 0.0
            lyr = dict(
                seg_idx=0, center=center, radius=r,
                axis=axis, u=u, v=v, angle_offset=offset,
                points_n=hole_feature.points_per_layer,
                blocked=getattr(sh, 'blocked_dirs', None))
            if getattr(sh, 'shape', 'circle') == 'rect':
                lyr.update(shape='rect', half_u=sh.half_u, half_v=sh.half_v,
                           corner_radius=sh.corner_radius)
            elif getattr(sh, 'shape', 'circle') == 'channel':
                lyr.update(channel_layer_fields(sh, t))
            layers.append(lyr)

    # จัดเรียงลำดับชั้นจาก "บนลงล่าง" (Top to Bottom) เสมอ
    top_pt = np.array(sh.open_3d)
    layers.sort(key=lambda lyr: float(np.linalg.norm(lyr['center'] - top_pt)))

    for i, lyr in enumerate(layers):
        lyr['layer_idx'] = i

    return layers

def channel_layer_fields(sh, t: float) -> dict:
    """ค่าของ layer ร่องเปิด (StepChannel) ที่ความลึก t — ใช้ร่วมกับ preview
    (core/path_planner.py) ให้จุดตรงกับ G-code เป๊ะ"""
    return dict(shape='channel', half_len=sh.half_len,
                station_lo=sh.station_lo, station_hi=sh.station_hi,
                w_plus=sh.wall_dist(t, +1), w_minus=sh.wall_dist(t, -1),
                end_pos=sh.end_dist(t, +1), end_neg=sh.end_dist(t, -1))


def _channel_contacts(lyr) -> list:
    """ร่องเปิด: จุดสถานี (station) เรียงตามความยาวร่อง แต่ละสถานีแตะผนังข้าง 2 ด้าน
    (+v แล้ว −v) เริ่มจากแนวกึ่งกลางร่อง + แตะผนังปลายที่ปิดอีกด้านละ 1 จุด
    จำนวนสถานี = points_per_layer // 2 (ขั้นต่ำ 1) — ปลายเปิดไม่มีจุดโพรบ
    (โพรบจะวิ่งเข้าไปในช่องที่ร่องต่ออยู่โดยไม่แตะอะไร)"""
    c, u, v = lyr['center'], lyr['u'], lyr['v']
    n_st = max(1, int(lyr['points_n']) // 2)
    lo, hi = lyr['station_lo'], lyr['station_hi']
    stations = [0.5 * (lo + hi)] if (n_st == 1 or hi - lo < 1e-6) else np.linspace(lo, hi, n_st)
    out = []
    for s in stations:
        start = c + float(s) * u
        out.append((start, v, lyr['w_plus']))
        out.append((start, -v, lyr['w_minus']))
    for sign, key in ((+1, 'end_pos'), (-1, 'end_neg')):
        e = lyr.get(key)
        if e is not None:
            out.append((c + sign * lyr['half_len'] * u, sign * u, e))
    return out


def _avoid_blocked(angles, blocked, u, v) -> np.ndarray:
    """เลื่อนมุมจุดโพรบที่ตกในช่วงปากร่อง (ไม่มีผนัง) ออกไปที่ขอบช่วงที่ใกล้กว่า"""
    centers = [(float(np.arctan2(np.dot(dv, v), np.dot(dv, u))), half)
               for dv, half in ((np.asarray(d, dtype=float), h) for d, h in blocked)]
    out = []
    for a in angles:
        for ca, half in centers:
            diff = (a - ca + np.pi) % (2 * np.pi) - np.pi
            if abs(diff) < half:
                a = ca + (half if diff >= 0 else -half)
        out.append(a)
    return np.array(out)


_ROT_STEP_DEG = 1.0    # ความละเอียดการค้นหามุมหมุนชุดจุด
_ROT_GOOD_DEG = 15.0   # ห่างขอบช่องเปิดเท่านี้ถือว่าดีพอ — แล้วเลือกมุมที่หมุนน้อยที่สุด


def _gap_margins(angles, centers) -> np.ndarray:
    """ระยะเชิงมุม (rad) ของแต่ละจุดถึงขอบช่วงไม่มีผนังที่ใกล้ที่สุด: บวก = อยู่บนผนัง, ลบ = ตกในช่อง"""
    angles = np.asarray(angles, dtype=float)
    m = np.full(len(angles), np.inf)
    for ca, half in centers:
        if half >= np.pi - 1e-9:   # ไม่มีผนังรอบรูเลย
            return np.full(len(angles), -np.inf)
        diff = np.abs((angles - ca + np.pi) % (2 * np.pi) - np.pi)
        m = np.minimum(m, diff - half)
    return m


def circle_layer_angles(lyr):
    """มุมจุดโพรบของ layer รูกลม — คืน (angles, มุมที่หมุน rad, mask จุดที่ไม่มีผนังให้แตะ)
    รูที่ผนังมีช่วงเปิด (lyr['blocked']):
      1) ทุกจุดอยู่บนผนังอยู่แล้ว → ใช้ตามที่ตั้งไว้ (ไม่หมุน)
      2) หมุนทั้งชุด (ระยะห่างเท่าเดิม) ไปมุมที่ห่างช่องเปิดที่สุด
      3) หมุนแล้วยังไม่พ้น → เลื่อนจุดที่เหลือไปขอบผนัง (_avoid_blocked)
      4) จุดที่ยังไม่มีผนัง หรือถูกเลื่อนไปทับจุดอื่น → ไม่โพรบ (mask = True)"""
    n = int(lyr['points_n'])
    base = np.linspace(0, 2 * np.pi, n, endpoint=False) + lyr['angle_offset']
    blocked = lyr.get('blocked')
    if not blocked or n <= 0:
        return base, 0.0, np.zeros(len(base), dtype=bool)
    u, v = lyr['u'], lyr['v']
    centers = [(float(np.arctan2(np.dot(dv, v), np.dot(dv, u))), half)
               for dv, half in ((np.asarray(d, dtype=float), h) for d, h in blocked)]
    if _gap_margins(base, centers).min() >= 0:
        return base, 0.0, np.zeros(n, dtype=bool)

    period, good = 2 * np.pi / n, np.radians(_ROT_GOOD_DEG)
    best_key, best = None, 0.0
    for d in np.arange(-period / 2, period / 2, np.radians(_ROT_STEP_DEG)):
        key = (min(float(_gap_margins(base + d, centers).min()), good), -abs(float(d)))
        if best_key is None or key > best_key:
            best_key, best = key, float(d)
    angles = base + best
    if _gap_margins(angles, centers).min() < 0:
        angles = _avoid_blocked(angles, blocked, u, v)
    bad = _gap_margins(angles, centers) < -1e-6
    tol = np.radians(1.0)
    for i in range(n):
        if bad[i]:
            continue
        for j in range(i):
            if not bad[j] and abs((angles[i] - angles[j] + np.pi) % (2 * np.pi) - np.pi) < tol:
                bad[i] = True
                break
    return angles, best, bad


def contact_plan_report(hole_feature, view_name: str = "Top", screen_rot: int = 0) -> dict:
    """สรุปการหลบช่องเปิดในผนังของรูนี้ (ตามค่าที่ตั้งอยู่ตอนนี้) สำหรับแผง Properties และหน้า Export
    {'rotated_deg': มุมที่หมุนมากสุด, 'skipped': จำนวนจุดที่ไม่มีผนังให้แตะ,
     'skipped_layers': ลำดับ layer (นับจาก 1) ที่มีจุดถูกตัด, 'total': จำนวนจุดทั้งหมดก่อนตัด}"""
    rep = {'rotated_deg': 0.0, 'skipped': 0, 'skipped_layers': [], 'total': 0}
    sh = getattr(hole_feature, '_step_hole', None)
    if sh is None or not getattr(sh, 'blocked_dirs', None) or getattr(sh, 'shape', 'circle') != 'circle':
        return rep
    hf = transform_hole_feature_for_machining(hole_feature, view_name, screen_rot)
    for lyr in _raw_layers_for_hole(hf):
        _a, rot, bad = circle_layer_angles(lyr)
        rep['rotated_deg'] = max(rep['rotated_deg'], abs(float(np.degrees(rot))))
        rep['total'] += len(bad)
        if bad.any():
            rep['skipped'] += int(bad.sum())
            rep['skipped_layers'].append(lyr['layer_idx'] + 1)
    return rep


def _layer_contacts(lyr) -> list:
    """v07: จุดสัมผัสผนังของ layer เดียว เรียงตามลำดับที่จะถูกโพรบ —
    list ของ (start, normal, wall_dist): โพรบเริ่มที่ start แล้วเดินตาม
    normal (เวกเตอร์หน่วย) ระยะ wall_dist จึงถึงผนังจริง
    รูกลม: start = จุดศูนย์กลาง layer, normal = แนวรัศมี (เหมือน v06)"""
    c, u, v = lyr['center'], lyr['u'], lyr['v']
    offset, n = lyr['angle_offset'], lyr['points_n']

    if lyr.get('shape') == 'rect':
        phase = (offset / (2 * np.pi)) % 1.0
        return [(c + su * u + sv * v, nu * u + nv * v, dist)
                for su, sv, nu, nv, dist in rect_wall_contacts(
                    lyr['half_u'], lyr['half_v'], lyr['corner_radius'], n, phase)]

    if lyr.get('shape') == 'channel':
        return _channel_contacts(lyr)

    # v10: รูที่ผนังมีช่วงเปิด — หมุน/เลื่อนจุดให้อยู่บนผนัง จุดที่ไม่มีผนังให้แตะถูกตัดออก
    angles, _rot, bad = circle_layer_angles(lyr)
    return [(c, np.cos(a) * u + np.sin(a) * v, lyr['radius'])
            for a, skip in zip(angles, bad) if not skip]


# ---------------------------------------------------------------------
# v10: ตรวจความปลอดภัยก่อน export (ใช้ค่าจาก Hardware Setting จริง)
# ---------------------------------------------------------------------
def probe_safety_report(holes, probe_profile, backoff: float = 0.0) -> list:
    """รูที่โปรแกรมนี้จะโพรบได้ไม่ปลอดภัยด้วยหัวโพรบปัจจุบัน — [(hole, [เหตุผล...]), ...]

    คิดจาก layer ที่จะถูกโพรบจริง (_raw_layers_for_hole — segment ที่ไม่ได้เลือกไม่นับ):
      - ก้านสั้นไป    : layer ที่ลึกที่สุดอยู่ลึกกว่า stylus_length จากปากรู
      - หัวโพรบใหญ่ไป : ระยะจากจุดศูนย์กลาง layer ถึงผนัง (รัศมี หรือครึ่งด้านแคบของ
                        ช่องสี่เหลี่ยม) ลบรัศมีหัวโพรบ น้อยกว่า wall_clearance
      - Back-off ยาวไป : ถอยหลังหลังแตะผนัง (backoff) ไกลกว่าระยะที่หัวโพรบขยับได้
                        ข้ามรู (2 x ระยะว่าง) → ชนผนังฝั่งตรงข้าม"""
    report = []
    tip_r     = float(probe_profile.tip_radius)
    clearance = float(getattr(probe_profile, 'wall_clearance', 0.0))
    stylus    = float(probe_profile.stylus_length)
    for h in holes:
        sh = getattr(h, '_step_hole', None)
        if sh is None:
            continue   # ไม่มีข้อมูล STEP — generate_gcode() ข้ามและรายงานแยกอยู่แล้ว
        layers = _raw_layers_for_hole(h)
        if not layers:
            continue
        mouth = np.array(sh.open_3d, dtype=float)
        depth = max(float(np.linalg.norm(np.asarray(l['center']) - mouth)) for l in layers)
        def _narrowest(l):
            if l.get('shape') == 'rect':
                return min(l['half_u'], l['half_v'])
            if l.get('shape') == 'channel':   # ผนังข้าง 2 ด้าน + ผนังปลายที่ปิด
                return min([l['w_plus'], l['w_minus']] +
                           [e for e in (l.get('end_pos'), l.get('end_neg')) if e is not None])
            return float(l['radius'])
        narrow = min(_narrowest(l) for l in layers)
        room = narrow - tip_r   # ระยะที่จุดศูนย์กลางหัวโพรบเดินได้จากกลาง layer ถึงจุดแตะผนัง
        reasons = []
        if depth > stylus:
            reasons.append(f"deepest probe point is {depth:.1f} mm deep, stylus is only {stylus:.1f} mm")
        if room < clearance:
            reasons.append(f"tip \u2300{probe_profile.tip_diameter:.2f} mm leaves {max(room, 0.0):.2f} mm "
                           f"to the wall (needs {clearance:.2f} mm)")
        elif backoff > 2.0 * room:
            reasons.append(f"back-off {backoff:.2f} mm is longer than the {2.0 * room:.2f} mm the tip can "
                           f"move across the hole \u2014 it would hit the opposite wall")
        if reasons:
            report.append((h, reasons))
    return report


def gcode_extents(gcode_text: str) -> dict:
    """ช่วงพิกัดที่โปรแกรมสั่งเดินจริงในแต่ละแกน {'X': (min, max), ...} — นับทุกคำสั่ง
    เคลื่อนที่ (G0/G1/G38.2) ทั้งโหมด G90 และ G91 (ไล่ตำแหน่งต่อจากคำสั่งก่อนหน้า)
    G38.2 นับถึงปลายทางที่สั่ง (รวม overtravel) จึงเผื่อมากกว่าการเดินจริงเล็กน้อย"""
    pos, lo, hi = {}, {}, {}
    absolute = True
    for raw in gcode_text.splitlines():
        line = raw.split(';', 1)[0].strip().upper()
        if not line:
            continue
        if line.startswith('G90'):
            absolute = True
            continue
        if line.startswith('G91'):
            absolute = False
            continue
        if not re.match(r'^G(0|1|38\.2)(\s|$)', line):
            continue
        for ax, val in re.findall(r'([XYZ])\s*(-?\d+(?:\.\d+)?)', line):
            v = float(val)
            pos[ax] = v if (absolute or ax not in pos) else pos[ax] + v
            lo[ax] = min(lo.get(ax, pos[ax]), pos[ax])
            hi[ax] = max(hi.get(ax, pos[ax]), pos[ax])
    return {ax: (lo[ax], hi[ax]) for ax in lo}


# ---------------------------------------------------------------------
def build_point_map(holes, view_name: str, screen_rot: int = 0, origin=None) -> list:
    """คำนวณรายการจุดที่ "คาดหวังว่าจะถูกโพรบสัมผัส" (expected probe touch
    points) แบบเรียงลำดับเดียวกับที่ generate_gcode() จะยิงคำสั่ง G38.2
    ออกมาเป๊ะ ๆ (รู nearest-neighbor -> segment -> layer -> มุมจุดในชั้น)
    — ไม่ต้องพึ่ง GCodeSettings (safe_z/overtravel/backoff/feedrate/
    padding_height) เลย เพราะค่าพวกนี้เป็นแค่ margin ด้านความปลอดภัยหรือ
    การตั้งค่าทางกายภาพตอนเขียน G-code ไม่ใช่ส่วนหนึ่งของตำแหน่งผิวชิ้นงาน
    จริงตาม geometry — ให้ x/y/z ในผลลัพธ์เป็นจุดสัมผัสผนังรูจริง (จุด
    ศูนย์กลาง + รัศมี ณ ชั้นนั้น) ตรงกับตำแหน่งที่ผิวชิ้นงานควรอยู่ตาม STEP

    ใช้ร่วมกันโดย:
      - generate_gcode() ด้านล่าง (เป็น point_map ที่ return กลับไป)
      - ui/evaluation_left_panel.py (เป็นฝั่ง EXPECTED ของการเทียบกับไฟล์
        .log จาก OpenBuilds Control — ดู core/evaluation_engine.py::
        evaluate_points() และ PLAN_evaluation-tab-openbuilds-log-
        comparison_v02.md §3)

    Parameters
    ----------
    holes     : list ของ HoleFeature "ต้นฉบับ" (ยังไม่ผ่าน view transform) —
                เดียวกับที่ส่งเข้า generate_gcode()
    view_name : ชื่อมุมมองที่ใช้ตอน export/ประเมินผล (กำหนดทิศทางพลิก
                ชิ้นงานผ่าน apply_view_transform() — ต้องตรงกับตอน export จริง)

    Returns
    -------
    list ของ dict เรียงตามลำดับที่จะถูกโพรบจริง แต่ละอันมี:
      hole_id   : hole.display_id ของรูนั้น (ตอนคำนวณ point map)
      seg_idx   : ลำดับ segment ภายในรู (0 ถ้าเป็นรูปกติ segment เดียว)
      layer_idx : ลำดับ layer ภายใน segment (0-based)
      point_idx : ลำดับจุดภายใน layer (0-based)
      x, y, z   : พิกัดจุดสัมผัสผนังรูที่คาดหวัง (mm)
    """
    transformed_holes = [transform_hole_feature_for_machining(h, view_name, screen_rot, origin) for h in holes]
    valid, _skipped = split_step_ready(transformed_holes)
    ordered = order_holes_nearest_neighbor(valid)

    point_map = []
    for hole in ordered:
        for lyr in _raw_layers_for_hole(hole):
            seg_idx = lyr.get('seg_idx', 0)

            for pt_i, (start, normal, dist) in enumerate(_layer_contacts(lyr)):
                pt = start + dist * normal   # จุดสัมผัสผนังจริง — ไม่รวม overtravel
                point_map.append({
                    'hole_id':   getattr(hole, 'display_id', '?'),
                    'seg_idx':   int(seg_idx),
                    'layer_idx': int(lyr['layer_idx']),
                    'point_idx': int(pt_i),
                    'x': float(pt[0]), 'y': float(pt[1]), 'z': float(pt[2]),
                    # v11: ทิศที่โพรบเดินเข้าหาผนัง (เวกเตอร์หน่วย, พิกัดเครื่อง) — ใช้ชดเชย
                    # รัศมีหัวโพรบตอนประเมินผล และชนิดรูปทรง (ใช้เลือก layer ที่จะ fit วงกลม)
                    'nx': float(normal[0]), 'ny': float(normal[1]), 'nz': float(normal[2]),
                    'shape': lyr.get('shape', 'circle'),
                })
    return point_map


# ---------------------------------------------------------------------
# เพิ่มอาร์กิวเมนต์ view_name เข้ามาในฟังก์ชันหลัก
def generate_gcode(holes, probe_profile, settings: GCodeSettings, view_name: str = "Top",
                   screen_rot: int = 0, origin=None, zero_note: str = None):
    """
    Build a GRBL probe program from `holes`.
    """
    # 1. จำลองการพลิกชิ้นงานก่อนทำงานเสมอ
    transformed_holes = [transform_hole_feature_for_machining(h, view_name, screen_rot, origin) for h in holes]
    
    valid, skipped = split_step_ready(transformed_holes)
    ordered = order_holes_nearest_neighbor(valid)

    # v05: point_map is now produced by build_point_map() — called on the
    # same ORIGINAL (pre-transform) `holes` + `view_name` used above, so it
    # is guaranteed to walk holes/segments/layers/points in the exact same
    # order as the G-code emission loop below (see build_point_map()'s
    # docstring for why that's safe). The .gcode TEXT emitted below is
    # completely unchanged from v04.
    point_map = build_point_map(holes, view_name, screen_rot, origin)

    lines = []

    lines.append("; ============================================")
    lines.append(f"; 3D ProbeCode - GRBL Probe Program (View: {view_name})")
    lines.append(f"; Holes: {len(ordered)}  Safe Z: {settings.safe_z:.2f} mm  "
                 f"Probe Feed: {settings.probe_feedrate:.0f} mm/min")
    if zero_note:   # v09: Work zero ที่ผู้ใช้เลือก (core/work_zero.py)
        lines.append(f"; WORK ZERO: X0 Y0 Z0 = {zero_note}")
        lines.append("; BEFORE RUNNING: touch off that point and Set Zero X/Y/Z there.")
    else:
        lines.append("; NOTE: work zero = mesh centroid (no G54 offset applied)")
    # v06: report the padding height assumed under the workpiece for this
    # export — comment-only, does not affect any coordinate below.
    lines.append(f"; NOTE: assumes workpiece is raised by {settings.padding_height:.2f} mm padding (riser plate)")
    if str(view_name).lower() != "top":
        lines.append(f"; NOTE: Coordinate system transformed for {view_name} view machining")
    if screen_rot:
        lines.append(f"; NOTE: X/Y rotated {screen_rot} deg to match the on-screen orientation")
    if skipped:
        names = ", ".join(str(getattr(h, 'display_id', '?')) for h in skipped)
        lines.append(f"; WARNING: {len(skipped)} hole(s) skipped (no STEP geometry): {names}")
    lines.append("; ============================================")
    lines.append("G21 ; mm units")
    lines.append("G90 ; absolute positioning")
    lines.append("G94 ; feed rate mode: units/min")
    lines.append(f"G0 Z{settings.safe_z:.3f}")
    lines.append("")

    for hi, hole in enumerate(ordered):
        sh = hole._step_hole
        # axis ชี้จากปากรู (open) เข้าไปสู่ก้นรู (deep) -> เป็นเวกเตอร์พุ่งเข้าด้านใน
        axis, _, _ = _orthonormal_basis(np.array(sh.deep_3d) - np.array(sh.open_3d))
        
        # [FIX] เปลี่ยนเป็นลบ (-) เพื่อถอย entry_pt ออกมาจากปากรูสู่อากาศ (Clearance) ไม่ใช่จมลงไปในรู
        entry_pt = np.array(sh.open_3d) - settings.entry_clearance * axis

        lines.append(f"; --- Hole {getattr(hole, 'display_id', '?')} ({hi + 1}/{len(ordered)}) ---")

        excluded_segs = [i + 1 for i, cfg in enumerate(getattr(hole, 'segments', []))
                          if not getattr(cfg, 'selected_for_inspection', True)]
        if excluded_segs:
            lines.append(f"; NOTE: segment(s) {excluded_segs} excluded (unreachable)")

        lines.append(f"G0 Z{settings.safe_z:.3f}")
        lines.append(f"G0 X{sh.open_3d[0]:.3f} Y{sh.open_3d[1]:.3f}")
        lines.append(f"G0 X{entry_pt[0]:.3f} Y{entry_pt[1]:.3f} Z{entry_pt[2]:.3f}")

        for lyr in _raw_layers_for_hole(hole):
            c             = lyr['center']
            seg_tag       = f" seg {lyr['seg_idx'] + 1}" if 'seg_idx' in lyr else ""

            lines.append(f"G0 X{c[0]:.3f} Y{c[1]:.3f} Z{c[2]:.3f} "
                         f"; layer {lyr['layer_idx'] + 1}{seg_tag} — center")

            contacts = _layer_contacts(lyr)
            n        = len(contacts)
            for pt_i, (start, normal, dist) in enumerate(contacts):
                target = start + (dist + settings.overtravel) * normal
                back   = -normal * settings.backoff

                # v07: ช่องสี่เหลี่ยม — ไปจุดเริ่มบนเส้นกึ่งกลางช่องก่อน (ช่องนูน
                # จึงเดินตรงจากจุดศูนย์กลางได้โดยไม่ชนผนัง)
                if not np.allclose(start, c):
                    lines.append(f"G0 X{start[0]:.3f} Y{start[1]:.3f} Z{start[2]:.3f} "
                                 f"; point {pt_i + 1}/{n} — approach")

                lines.append(f"G38.2 X{target[0]:.3f} Y{target[1]:.3f} "
                             f"Z{target[2]:.3f} F{settings.probe_feedrate:.0f} "
                             f"; point {pt_i + 1}/{n} — touch")

                lines.append("G91")
                lines.append(f"G0 X{back[0]:.3f} Y{back[1]:.3f} Z{back[2]:.3f} ; pull-off from wall")
                lines.append("G90")
                lines.append(f"G0 X{c[0]:.3f} Y{c[1]:.3f} Z{c[2]:.3f} ; return to center")
        lines.append("")

    lines.append(f"G0 Z{settings.safe_z:.3f}")
    lines.append("M30 ; program end")

    return "\n".join(lines), skipped, point_map