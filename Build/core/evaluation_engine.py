# ==============================================================================
# core/evaluation_engine.py — เปรียบเทียบจุดที่คาดหวัง (จาก STEP) กับจุดที่
# ถูกโพรบจริง (จาก .log ของ OpenBuilds Control) + ตรวจจับ setting ที่เปลี่ยน
# ไปตั้งแต่ export
# ==============================================================================
# VERSION: 01
# หน้าที่: ตรรกะล้วน (pure logic, ไม่แตะ UI) 3 กลุ่ม:
#   1) evaluate_points()         — จับคู่ EXPECTED[i] กับ ACTUAL[i] ด้วย
#      sequence index (ไม่ใช่ spatial nearest-neighbor — ดูเหตุผลใน
#      PLAN_evaluation-tab-openbuilds-log-comparison_v02.md §3), คำนวณ
#      ระยะเบี่ยงเบน 3D แบบ Euclidean ต่อจุด แล้วรวมผลขึ้นเป็น
#      layer -> segment -> hole -> overall accuracy
#   2) build_settings_snapshot() / diff_snapshots() — ระบบ "stale-settings
#      guard" (§6): จับภาพค่าตั้งค่าการตรวจสอบ (layers/points/zigzag/
#      segment-selection) ของแต่ละรู ณ เวลาหนึ่ง เพื่อเทียบว่ามีอะไรเปลี่ยน
#      ไปหรือไม่ระหว่างตอน export G-code กับตอนโหลดผลตรวจ .log
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
    รวมผลขึ้นเป็นโครงสร้าง layer -> segment -> hole -> ภาพรวม

    Parameters
    ----------
    expected_points : list ที่ได้จาก core/gcode_generator.py::build_point_map()
                       — แต่ละอันมี hole_id, seg_idx, layer_idx, point_idx, x, y, z
    actual_points   : list ที่ได้จาก core/log_parser.py::parse_openbuilds_log()
                       — แต่ละอันมี x, y, z (เรียงตามลำดับที่เครื่องทำงานจริง)
    tolerance_mm    : ระยะเบี่ยงเบนสูงสุดที่ยังถือว่า "ผ่าน" (mm)

    Returns
    -------
    dict ตาม contract ที่ ui/tabs/evaluation_tab.py คาดหวัง ยกเว้น 'holes'
    ที่ key ด้วย hole_id (str) แทน global index — ผู้เรียกฝั่ง UI ต้อง remap
    เอง (ดู NOTE ด้านบนของไฟล์) นอกจากนี้ยังมี key เสริมที่ไม่ได้อยู่ใน
    contract เดิมแต่มีประโยชน์:
      expected_count, actual_count : จำนวนจุดดิบของแต่ละฝั่งก่อนตัดตาม min()
      sequence_mismatch            : True ถ้าจำนวนจุดสองฝั่งไม่เท่ากัน
                                      (เช่น probe run ถูกขัดจังหวะกลางทาง)
    """
    total_points = min(len(expected_points), len(actual_points))
    passed_points = 0

    # โครงสร้างชั่วคราวระหว่างสะสมผล — ใช้ dict คีย์กันซ้ำ แล้วค่อยแปลงเป็น
    # list เรียงลำดับตอนจบ
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
            'distance_mm': distance,
            'passed':      passed,
        })

    # --- แปลงโครงสร้างชั่วคราว (_segments/_layers เป็น dict) ให้เป็น list
    # ที่เรียงลำดับแล้ว ตรงกับ contract ของ ui/tabs/evaluation_tab.py ---
    holes_out = {}
    for hole_id, hole_entry in holes.items():
        segments_out = []
        for seg_idx in sorted(hole_entry['_segments'].keys()):
            seg_entry = hole_entry['_segments'][seg_idx]
            layers_out = []
            for lyr_idx in sorted(seg_entry['_layers'].keys()):
                layer_entry = seg_entry['_layers'][lyr_idx]
                layer_entry['points'].sort(key=lambda p: p['point_idx'])
                layer_entry['passed'] = all(p['passed'] for p in layer_entry['points'])
                layers_out.append(layer_entry)
            segments_out.append({'seg_idx': seg_idx, 'layers': layers_out})

        holes_out[hole_id] = {
            'display_id':    hole_entry['display_id'],
            'passed':        (hole_entry['total_points'] > 0 and
                              hole_entry['passed_points'] == hole_entry['total_points']),
            'total_points':  hole_entry['total_points'],
            'passed_points': hole_entry['passed_points'],
            'max_deviation': hole_entry['max_deviation'],
            'segments':      segments_out,
        }

    overall_accuracy = (passed_points / total_points * 100.0) if total_points else 0.0

    return {
        'tolerance_mm':       tolerance_mm,
        'overall_accuracy':   overall_accuracy,
        'total_points':       total_points,
        'passed_points':      passed_points,
        'expected_count':     len(expected_points),
        'actual_count':       len(actual_points),
        'sequence_mismatch':  len(expected_points) != len(actual_points),
        'settings_mismatch':  [],   # เติมทีหลังโดยผู้เรียก (diff_snapshots())
        'holes':              holes_out,
    }


# ==============================================================================
# 2) Stale-settings guard (§6)
# ==============================================================================
def _hole_fingerprint(hole) -> str:
    """คีย์ที่เสถียรสำหรับระบุ "รูเดียวกัน" ข้ามเวลา — ใช้พิกัด/ขนาดของรู
    ปัดเศษ แทน display_id เพราะ display_id เปลี่ยนได้ทุกครั้งที่มีการ
    เลือก/ยกเลิกเลือกรูใหม่ (ดู ui/main_window.py::_renumber_holes_by_category())"""
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
    """จับภาพค่าตั้งค่าการตรวจสอบของทุกรูที่ส่งเข้ามา (ปกติคือรูที่
    selected_for_inspection == True ณ เวลานั้น) — เรียกทั้งตอน export
    G-code จริง (core/gcode_export_panel.py) และตอนโหลดผลตรวจ .log
    (ui/evaluation_left_panel.py) เพื่อนำสองภาพมาเทียบกันผ่าน
    diff_snapshots()

    Returns
    -------
    dict: {
      'view_name': str,
      'holes': {
        <fingerprint>: {
          'display_id': ...,        # เก็บไว้เพื่อรายงานผล ไม่ใช้เทียบ equality
          'multi_segment': bool,
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

        if segs:
            snapshot['holes'][fp] = {
                'display_id':    getattr(hole, 'display_id', '?'),
                'multi_segment': True,
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
                'display_id':         getattr(hole, 'display_id', '?'),
                'multi_segment':      False,
                'layers':             hole.layers,
                'points_per_layer':   hole.points_per_layer,
                'zigzag_inspection':  hole.zigzag_inspection,
                'zigzag_degree':      hole.zigzag_degree,
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
    if new_cfg.get('multi_segment'):
        return _segment_settings_differ(
            old_cfg.get('segments', []), new_cfg.get('segments', []))
    watched_keys = ('layers', 'points_per_layer', 'zigzag_inspection', 'zigzag_degree')
    return any(old_cfg.get(key) != new_cfg.get(key) for key in watched_keys)


def diff_snapshots(old_snapshot: dict, new_snapshot: dict) -> list:
    """เทียบ snapshot สองอัน (ตอน export กับตอนประเมินผล) คืนรายการ
    display_id (ตาม new_snapshot — สะท้อนหมายเลขปัจจุบัน) ของรูที่มีค่า
    ตั้งค่าเปลี่ยนไป หรือ view ที่ใช้ export เปลี่ยนไป

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
