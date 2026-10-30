# core/gcode_generator.py
# VERSION: 17
# CHANGE LOG (v16 -> v17):
#   FEATURE (จุดแตะจาก B-Rep ตรง ๆ): build_point_map(probe_r=...) — ทุกจุดคิดจากไฟล์ STEP ด้วย
#   core/surface_oracle.py: x/y/z = จุดที่เส้นทางโพรบทะลุผิว CAD จริง และ 'trig' = ตาราง
#   [r, s, mx, my, mz] (ลูกบอลรัศมี r แตะที่ระยะเดิน s จาก start ด้วยทิศตั้งฉากผิว m) + sx/sy/sz
#   (จุดเริ่มเดิน) — แทนการเดาจากรัศมีที่ระดับชั้น + ความชันจากผลต่างจำกัด (ทรงกลม/มุมโค้ง
#   ลูกบอลแตะต่ำกว่าระดับชั้น แบบเดิมคลาดถึง 0.12 มม. ที่ชั้นลึกของหลุม R10 ด้วยลูก ⌀2)
#   G38.2 ปลายทาง = จุดแตะจริงของลูกบอลจริง (ตาราง r = R) + R + overtravel (ระยะเผื่อเท่าเดิม)
#   FEATURE (คาลิเบรตหัวโพรบด้านนอก): calib=dict(lo, hi) → ก่อนเข้ารูแตะผนังนอก 4 ด้าน (X−, X+,
#   Y−, Y+) ที่ลึก CALIB_DEPTH จากผิวบน — หน้า Evaluation หา Effective Tip ⌀ ของรอบนั้นจาก
#   span − ขนาดจริง (core/evaluation_engine.py v12) จุดเหล่านี้ shape='calib' อยู่ต้น point map
# CHANGE LOG (v15 -> v16):
#   ตัดระบบ Padding Height ออก (suggest_padding_height, GCodeSettings.padding_height และบรรทัด
#   NOTE ในหัวไฟล์) — Z0 ตั้งที่ผิวบนชิ้นงานเสมอ ความสูงแผ่นรองไม่มีผลกับพิกัดใด ๆ
# CHANGE LOG (v14 -> v15):
#   layer_depths(): ความลึกแต่ละชั้นใต้ปากรู — แท็บ Evaluation เตือนชั้นที่ลึกเกินจุดที่ก้านแตะขอบ
# CHANGE LOG (v13 -> v14):
#   จบโปรแกรม: ยก Z ไป Safe Z ก่อน แล้วกลับ X0 Y0 (ค้างที่ Safe Z) จึงค่อย M30
# CHANGE LOG (v12 -> v13):
#   FEATURE (แตะสองครั้ง): probe_profile.double_touch → ทุกจุด (ผนัง/พื้น) แตะเร็วตาม probe feed
#   แล้วถอย retouch_distance คั่นด้วย RETOUCH_MARK (G4 P0.01) แล้วแตะช้า (retouch_feed)
#   core/log_parser.py v03 ทิ้งจุดแตะเร็วเมื่อเจอ marker — ลำดับจุดยังตรงกับ build_point_map()
#   FEATURE (ผนังเอียง): รูกลมที่รัศมีเปลี่ยนตามความลึก (กรวย/ทรงกลม/มุมโค้ง) — layer มี 'slope'
#   (dr/ds) build_point_map() เพิ่ม mx/my/mz = ทิศตั้งฉากผิวจริง ให้ evaluation คิดจุดที่ลูกบอล
#   แตะจริง และ G38.2 ลดระยะปลายทางตามจุดแตะที่มาก่อน (ไม่ต้องเผื่อ overtravel เพิ่ม)
# CHANGE LOG (v11 -> v12):
#   FEATURE (ระยะเผื่อพื้น): ตำแหน่งชั้นวัดมาจาก core/models.py::layer_fractions() —
#   ชั้นที่ลึกสุดสูงกว่าพื้น/ขั้นใต้ลูกบอลอย่างน้อย รัศมีหัวโพรบ + floor clearance
#   (ถ้าพอแล้ว G-code ไม่เปลี่ยน) probe_safety_report() เตือนรูที่เว้นระยะไม่ได้
#   FEATURE (วัดพื้นก้นรู แนว Z): HoleFeature.measure_floor + probe_profile.z_trigger →
#   หลังวัดผนังครบ แตะพื้นกลางรูด้วย G38.2 ตามแกนรู; build_point_map(z_trigger=...)
#   เพิ่มจุด shape='floor' (layer_idx = -1) ลำดับตรงกับ G-code เสมอ
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

from core.log_parser import RETOUCH_MARK
from core.hole_ordering import order_holes_nearest_neighbor, split_step_ready
from core.models import (FLOOR_SAFETY, hole_floor_depth, layer_fractions, rect_wall_contacts,
                         surface_below)

EDGE_DEG = 30.0        # v17: ทิศแตะของลูกบอลจริงต่างจากทิศที่ผนังเกินนี้ = แตะขอบ/ขั้นก่อนผนัง (เตือน)
CALIB_DEPTH = 3.0      # v17: ความลึกศูนย์กลางลูกบอลใต้ผิวบน ตอนแตะผนังนอก — ปรับได้
CALIB_GAP = 5.0        # v17: ระยะผิวลูกบอลถึงผนังนอกตอนลด Z ข้างชิ้นงาน — ปรับได้
FLOOR_APPROACH = 2.0   # v12: เริ่มแตะพื้นจากระยะลูกบอล-พื้น (ตาม CAD) เท่านี้ — ปรับได้
_SLOPE_DT = 0.02       # v13: ช่วง t ที่ใช้หาความชันผนัง (สัดส่วนความยาวรู)
_SLOPE_MIN = 0.01      # v13: ชันน้อยกว่านี้ (≈0.6°) ถือว่าผนังตั้งตรง


def _wall_slope(radius_at, t: float, length: float) -> float:
    """v13: dr/ds ของผนังรูกลมที่ความลึก t (s = ระยะตามแกนรู) — บวก = รูกว้างขึ้นตามความลึก"""
    t0, t1 = max(0.0, t - _SLOPE_DT), min(1.0, t + _SLOPE_DT)
    if length <= 1e-9 or t1 - t0 <= 1e-9:
        return 0.0
    k = (radius_at(t1) - radius_at(t0)) / ((t1 - t0) * length)
    return float(k) if abs(k) >= _SLOPE_MIN else 0.0


def surface_normal(normal, axis, slope: float):
    """v13: ทิศตั้งฉากผิวผนัง (ชี้เข้าเนื้องาน) ที่จุดแตะ — ผนังตรงคือทิศเดียวกับที่โพรบเดิน"""
    m = np.asarray(normal, dtype=float) - slope * np.asarray(axis, dtype=float)
    return m / np.linalg.norm(m)


def contact_shift(tip_radius: float, slope: float) -> float:
    """v13: ผนังเอียง ลูกบอลแตะเร็วกว่าผนังตรงเท่านี้ (mm ตามทิศที่เดิน) = r(√(1+k²) − 1)"""
    return float(tip_radius) * (float(np.sqrt(1.0 + slope * slope)) - 1.0)


def _touch_lines(target, normal, settings, probe_profile, label: str, what: str) -> list:
    """v13: G38.2 หนึ่งจุด + ถอยออก — double_touch: แตะเร็ว → ถอย → marker → แตะช้า (ใช้ค่านี้)"""
    lines = [f"G38.2 X{target[0]:.3f} Y{target[1]:.3f} Z{target[2]:.3f} "
             f"F{settings.probe_feedrate:.0f} ; {label} — touch"]
    lines.append("G91")
    if getattr(probe_profile, 'double_touch', False):
        d = float(probe_profile.retouch_distance)
        rb = -normal * d
        fwd = normal * (d + settings.overtravel)
        lines.append(f"G0 X{rb[0]:.3f} Y{rb[1]:.3f} Z{rb[2]:.3f} ; back off for the slow re-touch")
        lines.append(f"{RETOUCH_MARK} ; re-touch marker — the log parser keeps the next touch only")
        lines.append(f"G38.2 X{fwd[0]:.3f} Y{fwd[1]:.3f} Z{fwd[2]:.3f} "
                     f"F{float(probe_profile.retouch_feed):.0f} ; {label} — slow re-touch")
    back = -normal * settings.backoff
    lines.append(f"G0 X{back[0]:.3f} Y{back[1]:.3f} Z{back[2]:.3f} ; pull-off from {what}")
    lines.append("G90")
    return lines

class GCodeSettings:
    """Plain settings container consumed by generate_gcode()."""
    def __init__(self, safe_z: float, entry_clearance: float = 2.0,
                 probe_feedrate: float = 100.0, overtravel: float = 0.8,
                 backoff: float = 1.2):
        self.safe_z          = float(safe_z)
        self.entry_clearance = float(entry_clearance)
        self.probe_feedrate  = float(probe_feedrate)
        self.overtravel      = float(overtravel)
        self.backoff         = float(backoff)

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

def floor_probe_plan(hole_feature, z_trigger: bool):
    """v12: จุดพื้นก้นรูที่จะแตะแนวแกนรู — (จุดบนพื้นกลางรู, แกนรูชี้เข้าก้น) หรือ None
    ใช้ร่วมกันทั้ง build_point_map() และ generate_gcode() ให้ลำดับจุดตรงกันเสมอ
    None เมื่อ: หัวโพรบทริกแนว Z ไม่ได้, รูไม่ได้ติ๊ก "Measure floor depth", รูทะลุ,
    หรือ segment ที่ลึกที่สุดถูกเลือกออก (หัวโพรบลงไม่ถึง)"""
    if not z_trigger or not getattr(hole_feature, 'measure_floor', False):
        return None
    sh = getattr(hole_feature, '_step_hole', None)
    if sh is None:
        return None
    segs = getattr(hole_feature, 'segments', None) or []
    if segs and not getattr(segs[0], 'selected_for_inspection', True):
        return None
    fd = hole_floor_depth(sh)
    if fd is None:
        return None
    o = np.array(sh.open_3d, dtype=float)
    axis, _u, _v = _orthonormal_basis(np.array(sh.deep_3d, dtype=float) - o)
    return o + fd * axis, axis


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
            length = float(np.linalg.norm(d - o))
            below  = surface_below(sh, seg_idx)                  # v12: ระยะเผื่อพื้น/ขั้น
            t_vals = layer_fractions(cfg.layers, length, below)
            for local_idx, t in enumerate(t_vals):
                center = o + t * (d - o)
                r      = seg.radius_at(t)
                offset = (np.radians(local_idx * cfg.zigzag_degree)
                         if cfg.zigzag_inspection else 0.0)
                layers.append(dict(
                    seg_idx=seg_idx, center=center, radius=r,
                    slope=_wall_slope(seg.radius_at, t, length),   # v13
                    axis=axis, u=u, v=v, angle_offset=offset,
                    points_n=cfg.points_per_layer,
                    blocked=getattr(sh, 'blocked_dirs', None),
                    floor_gap=None if below is None else (1.0 - t) * length + below))
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
        length   = float(np.linalg.norm(d - o))
        below    = surface_below(sh)                             # v12: ระยะเผื่อพื้น
        t_vals   = layer_fractions(n_layers, length, below)
        for idx, t in enumerate(t_vals):
            center = o + t * (d - o)
            r      = sh.radius_at(t)
            offset = np.radians(idx * deg) if use_zz else 0.0
            lyr = dict(
                seg_idx=0, center=center, radius=r,
                axis=axis, u=u, v=v, angle_offset=offset,
                points_n=hole_feature.points_per_layer,
                blocked=getattr(sh, 'blocked_dirs', None),
                floor_gap=None if below is None else (1.0 - t) * length + below)
            if getattr(sh, 'shape', 'circle') == 'rect':
                lyr.update(shape='rect', half_u=sh.half_u, half_v=sh.half_v,
                           corner_radius=sh.corner_radius)
            elif getattr(sh, 'shape', 'circle') == 'channel':
                lyr.update(channel_layer_fields(sh, t))
            else:
                lyr['slope'] = _wall_slope(sh.radius_at, t, length)   # v13
            layers.append(lyr)

    # จัดเรียงลำดับชั้นจาก "บนลงล่าง" (Top to Bottom) เสมอ
    top_pt = np.array(sh.open_3d)
    layers.sort(key=lambda lyr: float(np.linalg.norm(lyr['center'] - top_pt)))

    for i, lyr in enumerate(layers):
        lyr['layer_idx'] = i

    return layers

def layer_depths(hole_feature) -> dict:
    """v15: {layer_idx: ความลึกของจุดศูนย์กลางลูกบอลใต้ปากรู (mm)} ตามการตั้งค่าชั้นปัจจุบัน
    (ไม่ขึ้นกับมุมมอง) — ใช้เทียบกับ ProbeProfile.shaft_contact_depth()"""
    sh = getattr(hole_feature, '_step_hole', None)
    if sh is None:
        return {}
    o = np.array(sh.open_3d, dtype=float)
    return {lyr['layer_idx']: float(np.linalg.norm(lyr['center'] - o))
            for lyr in _raw_layers_for_hole(hole_feature)}


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
    # v12: + พื้นใต้ชั้นวัดที่ลึกสุด (ระยะเผื่อพื้น) และความยาวก้นสำหรับการแตะพื้นก้นรู
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
    floor_c   = float(getattr(probe_profile, 'floor_clearance', FLOOR_SAFETY['clearance']))
    z_trig    = bool(getattr(probe_profile, 'z_trigger', False))
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
        gaps = [l['floor_gap'] - tip_r for l in layers if l.get('floor_gap') is not None]
        if gaps and min(gaps) < floor_c - 1e-6:   # v12: ชั้นลึกสุดใกล้พื้น/ขั้นเกินไป (ยกขึ้นไม่ได้)
            reasons.append(f"deepest layer leaves only {max(min(gaps), 0.0):.2f} mm between the tip and "
                           f"the floor/step below (needs {floor_c:.2f} mm)")
        plan = floor_probe_plan(h, z_trig)
        if plan is not None:   # v12: แตะพื้นก้นรู — ก้นต้องยาวถึงพื้น
            fdepth = float(np.linalg.norm(plan[0] - mouth))
            if fdepth > stylus:
                reasons.append(f"floor is {fdepth:.1f} mm deep, stylus is only {stylus:.1f} mm "
                               f"(untick Measure floor depth)")
        if reasons:
            report.append((h, reasons))
    return report


def exact_touch_report(point_map) -> dict:
    """v17: สรุปจุดที่ตาราง B-Rep เตือน {hole_id: {'edge': n, 'start': n, 'none': n}} —
    'edge'  ลูกบอลจริงแตะขอบ/ขั้น/พื้นก่อนถึงผนัง (ค่าที่วัดได้ไม่ใช่ผนัง),
    'start' ลูกบอลแตะผิว CAD ตั้งแต่จุดเริ่ม (ชั้นลึกเกิน/ชิดพื้น — ลงไปก็ชน),
    'none'  เส้นทางไม่ชนผิวภายในระยะเดิน (ใช้สูตรเดิมแทน)"""
    out = {}
    for p in point_map:
        key = ('edge' if p.get('edge_first') else
               {'start_touching': 'start', 'no_contact': 'none'}.get(p.get('exact_fail')))
        if key:
            d = out.setdefault(str(p.get('hole_id', '?')), {'edge': 0, 'start': 0, 'none': 0})
            d[key] += 1
    return out


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
def _step_frame(view_name, screen_rot, origin):
    """v17: (to_step(p), dir_to_step(v), dir_from_step(v)) — พิกัดเครื่อง (หลังลบ origin) ↔ พิกัด STEP"""
    from core import surface_oracle
    from core.projector import view_rotation_matrix
    rot = view_rotation_matrix(view_name, screen_rot)
    org = np.zeros(3) if origin is None else np.asarray(origin, dtype=float)
    cen = surface_oracle.centroid()
    return (lambda p: rot.T @ (np.asarray(p, dtype=float) + org) + cen,
            lambda v: rot.T @ np.asarray(v, dtype=float),
            lambda v: rot @ np.asarray(v, dtype=float))


def _touch_record(start, normal, dist, probe_r, frame):
    """v17: ข้อมูลจุดแตะจาก B-Rep — {'x','y','z' (จุดทะลุผิว), 'sx'.. (จุดเริ่ม), 'trig'} หรือ None"""
    from core import surface_oracle
    if not probe_r or frame is None or not surface_oracle.available():
        return None
    to_step, dir_to_step, dir_from_step = frame
    try:
        table = surface_oracle.touch_table(to_step(start), dir_to_step(normal), float(probe_r),
                                           max_travel=float(dist) + 2.0 * float(probe_r) + 5.0)
    except Exception as e:
        print(f"[gcode_generator] surface_oracle failed ({e!r}) — using the layer radius")
        return None
    if table is None:   # ไม่มีตาราง: บอกเหตุผลไว้ (หน้า Export เตือน) แล้วใช้สูตรเดิม
        return {'exact_fail': surface_oracle.last_reason or 'no_contact'}
    hit = np.asarray(start, dtype=float) + table[0][1] * np.asarray(normal, dtype=float)
    rec = {'x': float(hit[0]), 'y': float(hit[1]), 'z': float(hit[2]),
           'sx': float(start[0]), 'sy': float(start[1]), 'sz': float(start[2]),
           'trig': [[round(r, 6), round(s_, 6)] + [round(float(c), 7) for c in dir_from_step(m)]
                    for r, s_, m in table]}
    # ลูกบอลจริงแตะคนละผิวกับจุดบนผนัง (ขอบขั้น/พื้นใต้ชั้น/ขอบช่องเปิด) — ทิศแตะต่างกันเกิน EDGE_DEG
    if float(np.dot(table[0][2], table[-1][2])) < np.cos(np.radians(EDGE_DEG)):
        rec['edge_first'] = True
    return rec


def calib_contacts(calib, probe_r: float) -> list:
    """v17: จุดแตะผนังนอก 4 ด้าน [(axis, side, start, normal, dist), ...] — calib = {'lo', 'hi'}
    กรอบชิ้นงานในพิกัดเครื่อง (ลบ origin แล้ว) side −1 = ผนังด้านลบ (โพรบเดินทาง +แกน)"""
    if not calib:
        return []
    lo, hi = np.asarray(calib['lo'], dtype=float), np.asarray(calib['hi'], dtype=float)
    mid = (lo + hi) / 2.0
    z = hi[2] - min(float(calib.get('depth', CALIB_DEPTH)), 0.5 * (hi[2] - lo[2]))
    off = float(probe_r) + float(calib.get('gap', CALIB_GAP))
    out = []
    for k, axis in ((0, 'X'), (1, 'Y')):
        for side in (-1, +1):
            start = mid.copy()
            start[2] = z
            start[k] = (lo[k] - off) if side < 0 else (hi[k] + off)
            normal = np.zeros(3)
            normal[k] = -side
            out.append((axis, side, start, normal, off))
    return out


def build_point_map(holes, view_name: str, screen_rot: int = 0, origin=None,
                    z_trigger: bool = False, probe_r: float = None, calib=None) -> list:
    """คำนวณรายการจุดที่ "คาดหวังว่าจะถูกโพรบสัมผัส" (expected probe touch
    points) แบบเรียงลำดับเดียวกับที่ generate_gcode() จะยิงคำสั่ง G38.2
    ออกมาเป๊ะ ๆ (จุดคาลิเบรตผนังนอก → รู nearest-neighbor -> segment -> layer
    -> มุมจุดในชั้น -> พื้นก้นรู)

    v17: probe_r = รัศมีลูกบอลจริง (Hardware Setting) — ถ้ามีไฟล์ STEP อยู่ (core/surface_oracle.py)
    ทุกจุดได้ x/y/z = จุดที่เส้นทางโพรบทะลุผิว CAD + 'trig' (ตารางจุดแตะตามขนาดลูกบอล 0 … probe_r)
    + sx/sy/sz (จุดเริ่มเดิน) — ไม่มี STEP/probe_r ใช้สูตรเดิม (จุดศูนย์กลางชั้น + รัศมีที่ระดับชั้น)
    calib = {'lo', 'hi'} กรอบชิ้นงาน (พิกัดเครื่อง ลบ origin แล้ว) → จุดแตะผนังนอก 4 จุดต้นรายการ

    ใช้ร่วมกันโดย generate_gcode(), core/expected_points_io.py (Schema) และ
    ui/evaluation_left_panel.py (ฝั่ง EXPECTED ของการเทียบกับ .log)

    Returns
    -------
    list ของ dict เรียงตามลำดับที่จะถูกโพรบจริง แต่ละอันมี:
      hole_id, seg_idx, layer_idx, point_idx, x, y, z, nx, ny, nz (ทิศที่โพรบเดิน), shape
      (+ sx, sy, sz, trig เมื่อคิดจาก B-Rep; cal_axis, cal_side เมื่อ shape == 'calib')
    """
    frame = _step_frame(view_name, screen_rot, origin) if probe_r else None
    point_map = []
    for i, (axis, side, start, normal, dist) in enumerate(calib_contacts(calib, probe_r or 0.0)):
        face = start + dist * normal
        rec = {'hole_id': 'CAL', 'seg_idx': 0, 'layer_idx': -2, 'point_idx': i,
               'x': float(face[0]), 'y': float(face[1]), 'z': float(face[2]),
               'sx': float(start[0]), 'sy': float(start[1]), 'sz': float(start[2]),
               'nx': float(normal[0]), 'ny': float(normal[1]), 'nz': float(normal[2]),
               'shape': 'calib', 'cal_axis': axis, 'cal_side': side}
        rec.update(_touch_record(start, normal, dist, probe_r, frame) or {})
        point_map.append(rec)

    transformed_holes = [transform_hole_feature_for_machining(h, view_name, screen_rot, origin) for h in holes]
    valid, _skipped = split_step_ready(transformed_holes)
    ordered = order_holes_nearest_neighbor(valid)

    for hole in ordered:
        for lyr in _raw_layers_for_hole(hole):
            seg_idx = lyr.get('seg_idx', 0)

            slope = lyr.get('slope', 0.0)
            for pt_i, (start, normal, dist) in enumerate(_layer_contacts(lyr)):
                pt = start + dist * normal   # จุดสัมผัสผนังจริง — ไม่รวม overtravel
                rec = {
                    'hole_id':   getattr(hole, 'display_id', '?'),
                    'seg_idx':   int(seg_idx),
                    'layer_idx': int(lyr['layer_idx']),
                    'point_idx': int(pt_i),
                    'x': float(pt[0]), 'y': float(pt[1]), 'z': float(pt[2]),
                    # v11: ทิศที่โพรบเดินเข้าหาผนัง (เวกเตอร์หน่วย, พิกัดเครื่อง) — ใช้ชดเชย
                    # รัศมีหัวโพรบตอนประเมินผล และชนิดรูปทรง (ใช้เลือก layer ที่จะ fit วงกลม)
                    'nx': float(normal[0]), 'ny': float(normal[1]), 'nz': float(normal[2]),
                    'shape': lyr.get('shape', 'circle'),
                }
                exact = _touch_record(start, normal, dist, probe_r, frame)   # v17
                if exact:
                    rec.update(exact)
                if not (exact or {}).get('trig') and slope:   # v13: ผนังเอียง — ทิศตั้งฉากผิว (evaluation คิดจุดที่ลูกบอลแตะจริง)
                    m = surface_normal(normal, lyr['axis'], slope)
                    rec.update(mx=float(m[0]), my=float(m[1]), mz=float(m[2]))
                point_map.append(rec)
        plan = floor_probe_plan(hole, z_trigger)   # v12: พื้นก้นรู — หลังผนังครบทุกชั้น
        if plan is not None:
            fp, ax = plan
            rec = {
                'hole_id':   getattr(hole, 'display_id', '?'),
                'seg_idx':   0, 'layer_idx': -1, 'point_idx': 0,
                'x': float(fp[0]), 'y': float(fp[1]), 'z': float(fp[2]),
                'nx': float(ax[0]), 'ny': float(ax[1]), 'nz': float(ax[2]),
                'shape': 'floor',
            }
            r_ = float(probe_r or 0.0)
            rec.update(_touch_record(fp - (r_ + FLOOR_APPROACH) * ax, ax, r_ + FLOOR_APPROACH,
                                     probe_r, frame) or {})   # v17
            point_map.append(rec)
    return point_map


def _probe_target(rec, start, normal, dist, early, tip_r, overtravel, floor=False):
    """v17: ปลายทาง G38.2 — จากตารางจุดแตะ B-Rep (แถวสุดท้าย = ลูกบอลจริง) ถ้ามี ไม่งั้นสูตรเดิม
    ผนัง: เลยจุดแตะของศูนย์กลางลูกบอลไป R + overtravel (เท่ากับเดิม: ถึงผิว CAD + overtravel)
    พื้น: เลยจุดแตะไป overtravel"""
    trig = (rec or {}).get('trig')
    if trig:
        s_hit = float(trig[-1][1])
        # ผนังเอียง: ลูกบอลกดเข้าผิวได้ลึกเท่าผนังตรงต้องเดินไกลขึ้น 1/cos α (α = มุมทิศเดินกับทิศตั้งฉากผิว)
        cos_a = max(0.3, float(np.dot(normal, trig[-1][2:5])))
        reach = s_hit + (overtravel + (0.0 if floor else tip_r)) / cos_a
        # ไม่สั้นกว่าผิว CAD + overtravel (ลูกบอลจริงอาจไปแตะขอบ/ขั้นก่อน แต่ต้องเดินถึงผนังได้)
        return start + max(reach, float(trig[0][1]) + overtravel) * normal
    if floor:
        return start + (dist - tip_r + overtravel) * normal
    return start + (dist - early + overtravel) * normal


# ---------------------------------------------------------------------
# เพิ่มอาร์กิวเมนต์ view_name เข้ามาในฟังก์ชันหลัก
def generate_gcode(holes, probe_profile, settings: GCodeSettings, view_name: str = "Top",
                   screen_rot: int = 0, origin=None, zero_note: str = None, calib=None):
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
    z_trigger = bool(getattr(probe_profile, 'z_trigger', False))   # v12
    tip_r = float(probe_profile.tip_radius)
    point_map = build_point_map(holes, view_name, screen_rot, origin, z_trigger=z_trigger,
                                probe_r=tip_r, calib=calib)   # v17
    recs = iter(point_map)   # v17: ลำดับเดียวกับการเขียน G38.2 ด้านล่างทุกจุด

    lines = []

    lines.append("; ============================================")
    lines.append(f"; 3D ProbeCode - GRBL Probe Program (View: {view_name})")
    lines.append(f"; Holes: {len(ordered)}  Safe Z: {settings.safe_z:.2f} mm  "
                 f"Probe Feed: {settings.probe_feedrate:.0f} mm/min")
    if getattr(probe_profile, 'double_touch', False):   # v13
        lines.append(f"; DOUBLE TOUCH: back off {float(probe_profile.retouch_distance):.2f} mm, re-touch at "
                     f"F{float(probe_profile.retouch_feed):.0f} — the slow touch is the measured value")
    if zero_note:   # v09: Work zero ที่ผู้ใช้เลือก (core/work_zero.py)
        lines.append(f"; WORK ZERO: X0 Y0 Z0 = {zero_note}")
        lines.append("; BEFORE RUNNING: touch off that point and Set Zero X/Y/Z there.")
    else:
        lines.append("; NOTE: work zero = mesh centroid (no G54 offset applied)")
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

    cal = calib_contacts(calib, tip_r)   # v17: คาลิเบรตหัวโพรบที่ผนังนอกก่อนเข้ารู
    if cal:
        lines.append(f"; --- Tip calibration: outer walls X-, X+, Y-, Y+ at {CALIB_DEPTH:g} mm below the top "
                     f"(Effective Tip for this run) ---")
        lines.append("; the ball goes down OUTSIDE the part - keep clamps/fixtures away from the side centres")
    for axis, side, start, normal, dist in cal:
        target = _probe_target(next(recs), start, normal, dist, 0.0, tip_r, settings.overtravel)
        label = f"calibration {axis}{'+' if side > 0 else '-'} wall"
        lines.append(f"G0 Z{settings.safe_z:.3f}")
        lines.append(f"G0 X{start[0]:.3f} Y{start[1]:.3f} ; {label} - outside the part")
        lines.append(f"G0 Z{start[2]:.3f} ; down beside the wall")
        lines.extend(_touch_lines(target, normal, settings, probe_profile, label, "wall"))
        lines.append(f"G0 Z{settings.safe_z:.3f}")
    if cal:
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
            early    = contact_shift(tip_r, lyr.get('slope', 0.0))   # v13 (ใช้เมื่อไม่มีตาราง B-Rep)
            for pt_i, (start, normal, dist) in enumerate(contacts):
                target = _probe_target(next(recs), start, normal, dist, early, tip_r,
                                       settings.overtravel)   # v17

                # v07: ช่องสี่เหลี่ยม — ไปจุดเริ่มบนเส้นกึ่งกลางช่องก่อน (ช่องนูน
                # จึงเดินตรงจากจุดศูนย์กลางได้โดยไม่ชนผนัง)
                if not np.allclose(start, c):
                    lines.append(f"G0 X{start[0]:.3f} Y{start[1]:.3f} Z{start[2]:.3f} "
                                 f"; point {pt_i + 1}/{n} — approach")

                lines.extend(_touch_lines(target, normal, settings, probe_profile,
                                          f"point {pt_i + 1}/{n}", "wall"))   # v13
                lines.append(f"G0 X{c[0]:.3f} Y{c[1]:.3f} Z{c[2]:.3f} ; return to center")

        plan = floor_probe_plan(hole, z_trigger)   # v12: แตะพื้นก้นรูแนวแกนรู (Z trigger)
        if plan is not None:
            fp, ax = plan
            start  = fp - (tip_r + FLOOR_APPROACH) * ax              # ลูกบอลลอยเหนือพื้น FLOOR_APPROACH
            target = _probe_target(next(recs), start, ax, tip_r + FLOOR_APPROACH, 0.0, tip_r,
                                   settings.overtravel, floor=True)  # เลยจุดแตะพื้นได้ไม่เกิน overtravel
            lines.append(f"G0 X{start[0]:.3f} Y{start[1]:.3f} Z{start[2]:.3f} ; floor — approach")
            lines.extend(_touch_lines(target, ax, settings, probe_profile,
                                      "floor (Z trigger)", "floor"))   # v13
            lines.append(f"G0 X{start[0]:.3f} Y{start[1]:.3f} Z{start[2]:.3f} ; floor — retract")
        lines.append("")

    lines.append(f"G0 Z{settings.safe_z:.3f} ; v14: lift to safe Z first")
    lines.append("G0 X0 Y0 ; v14: back to work zero X0 Y0 (stays at safe Z)")
    lines.append("M30 ; program end")

    return "\n".join(lines), skipped, point_map