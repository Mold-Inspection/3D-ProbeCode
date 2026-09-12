# ==============================================================================
# core/evaluation_engine.py — เปรียบเทียบจุดที่คาดหวัง (จาก STEP หรือจากไฟล์
# Schema .json ที่โหลดไว้) กับจุดที่ถูกโพรบจริง (จาก .log ของ OpenBuilds
# Control) + ตรวจจับ setting ที่เปลี่ยนไปตั้งแต่ export + คืนค่า settings
# snapshot กลับเข้ารู (full replace, เรียกอัตโนมัติตอนโหลด schema)
# ==============================================================================
# VERSION: 04
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


# ==============================================================================
# 1) evaluate_points()
# ==============================================================================
def evaluate_points(expected_points: list, actual_points: list, tolerance_mm: float) -> dict:
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

    Returns
    -------
    dict ตาม contract ที่ ui/tabs/evaluation_tab.py คาดหวัง ยกเว้น 'holes'
    ที่ key ด้วย hole_id (str) แทน global index — ผู้เรียกฝั่ง UI ต้อง remap
    เอง (ดู NOTE ด้านบนของไฟล์) key ระดับบนสุดที่มี:
      tolerance_mm, total_points, passed_points, failed_points,
      failed_point_refs, expected_count, actual_count,
      sequence_mismatch, settings_mismatch, holes
    """
    total_points = min(len(expected_points), len(actual_points))
    passed_points = 0

    holes: dict = {}

    for i in range(total_points):
        exp = expected_points[i]
        act = actual_points[i]

        ex, ey, ez = float(exp['x']), float(exp['y']), float(exp['z'])
        ax_, ay_, az_ = float(act['x']), float(act['y']), float(act['z'])
        dx, dy, dz = ax_ - ex, ay_ - ey, az_ - ez
        distance = math.sqrt(dx * dx + dy * dy + dz * dz)
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
            'actual':      (ax_, ay_, az_),
            'delta':       (dx, dy, dz),
            'distance_mm': distance,   # "Offset (mm)" in the UI
            'passed':      passed,
        })

    holes_out = {}
    failed_point_refs = []

    for hole_id, hole_entry in holes.items():
        segments_out = []
        for seg_idx in sorted(hole_entry['_segments'].keys()):
            seg_entry = hole_entry['_segments'][seg_idx]
            layers_out = []
            for lyr_idx in sorted(seg_entry['_layers'].keys()):
                layer_entry = seg_entry['_layers'][lyr_idx]
                layer_entry['points'].sort(key=lambda p: p['point_idx'])
                layer_entry['passed'] = all(p['passed'] for p in layer_entry['points'])
                for p in layer_entry['points']:
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
            'segments':      segments_out,
        }

    failed_points = total_points - passed_points

    return {
        'tolerance_mm':       tolerance_mm,
        'total_points':       total_points,
        'passed_points':      passed_points,
        'failed_points':      failed_points,
        'failed_point_refs':  failed_point_refs,
        'expected_count':     len(expected_points),
        'actual_count':       len(actual_points),
        'sequence_mismatch':  len(expected_points) != len(actual_points),
        'settings_mismatch':  [],   # เติมทีหลังโดยผู้เรียก (diff_snapshots())
        'holes':              holes_out,
    }


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
    return f"{round(float(ox), 2)}_{round(float(oy), 2)}_{round(float(oz), 2)}_{round(float(radius), 3)}_{round(float(depth), 2)}"


def build_settings_snapshot(holes: list, view_name: str) -> dict:
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
    snapshot = {'view_name': view_name, 'holes': {}}

    for hole in holes:
        fp = _hole_fingerprint(hole)
        segs = getattr(hole, 'segments', None) or []
        hole_selected = bool(getattr(hole, 'selected_for_inspection', False))   # v04

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
    view_changed = old_snapshot.get('view_name') != new_snapshot.get('view_name')

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

        if cfg.get('multi_segment'):
            segs = getattr(hole, 'segments', None) or []
            for seg_cfg in cfg.get('segments', []):
                si = seg_cfg.get('seg_idx')
                if si is None or si >= len(segs):
                    continue   # geometry's segment count changed since export — skip that segment only
                target = segs[si]
                target.layers                  = seg_cfg.get('layers', target.layers)
                target.points_per_layer        = seg_cfg.get('points_per_layer', target.points_per_layer)
                target.zigzag_inspection       = seg_cfg.get('zigzag_inspection', target.zigzag_inspection)
                target.zigzag_degree           = seg_cfg.get('zigzag_degree', target.zigzag_degree)
                target.selected_for_inspection = seg_cfg.get('selected_for_inspection', target.selected_for_inspection)
        else:
            hole.layers            = cfg.get('layers', hole.layers)
            hole.points_per_layer  = cfg.get('points_per_layer', hole.points_per_layer)
            hole.zigzag_inspection = cfg.get('zigzag_inspection', hole.zigzag_inspection)
            hole.zigzag_degree     = cfg.get('zigzag_degree', hole.zigzag_degree)

    return {
        'matched':              matched,
        'deselected':           deselected,
        'unmatched':            max(0, len(snap_holes) - matched),
        'total_snapshot_holes': len(snap_holes),
    }
