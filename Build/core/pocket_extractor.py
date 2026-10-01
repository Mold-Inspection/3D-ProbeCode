# ==============================================================================
# core/pocket_extractor.py — สกัด "ช่องสี่เหลี่ยม" (rectangular pocket) จาก B-Rep
# ==============================================================================
# VERSION: 02
# CHANGE LOG (v01 -> v02):
#   FEATURE: ช่องทรงแคปซูล (slot/obround — เส้นตรงขนาน 2 เส้น + ปลายครึ่ง
#   วงกลม 2 ด้าน) — เก็บเป็น StepPocket ที่ corner_radius == half_v (คือ
#   สี่เหลี่ยมมุมโค้งที่รัศมีมุมเท่าครึ่งความกว้าง) จึงใช้ pipeline เดิมได้
#   ทั้งหมด; ผิวครึ่งทรงกระบอกที่ปลาย slot ถูกข้ามเหมือนมุมโค้ง (เดิม slot
#   1 ช่องถูกนับเป็นรูกลมปลอม 2 รู)
# ==============================================================================
# หน้าที่: หาช่องสี่เหลี่ยมจัตุรัส/ผืนผ้า ทั้งมุมคมและมุมโค้ง (ทะลุหรือไม่ทะลุ)
# จากไฟล์ STEP แล้วคืนเป็น core.models.StepPocket ให้ใช้ต่อใน pipeline เดิม
#
# วิธีตรวจจับ: ปากช่องทุกช่องคือ "inner wire" (ขอบรูใน) ของผิวระนาบที่ช่องนั้น
# เจาะลงไป — wire ที่เป็นช่องสี่เหลี่ยมต้องมีเส้นตรง 4 เส้น (ขนาน/ตั้งฉากกันเป็น
# คู่) และส่วนโค้งมุม 0 เส้น (มุมคม) หรือ 4 เส้นรัศมีเท่ากัน กวาด 90° (มุมโค้ง)
# จากนั้นดูผนัง (face ที่ติดกับขอบ wire) ว่าลึกลงไปในเนื้อวัสดุ (= ช่อง) หรือ
# ยื่นขึ้นจากผิว (= boss/เสา ไม่ใช่ช่อง — ข้าม)
#
# ผิวทรงกระบอกที่มุมโค้งของช่อง (เว้า 90°) จะถูกคืนกลับไปด้วย (corner_faces)
# ให้ step_extractor.py ข้าม — เดิมมุมเหล่านี้ถูกนับเป็น "รูกลม" 4 รูต่อช่อง
#
# ช่องทรงแคปซูล (slot): wire มีเส้นตรงขนานกัน 2 เส้น + ส่วนโค้งรัศมีเท่ากัน
# ที่มุมกวาดรวม 360° (ปลายละ 180°) — v02
#
# ข้อจำกัด: ไม่รองรับช่องที่ผนังเอียง (draft), ช่องเปิดออกขอบชิ้นงาน
#
# ตัวแปรสำคัญที่ปรับจูนได้:
#   _PARALLEL_TOL  = ค่าเผื่อของ |cos| เมื่อเทียบว่าเส้นขนาน/ตั้งฉากกัน
#   _ARC_SWEEP_TOL = ค่าเผื่อมุมกวาดของส่วนโค้งมุม (rad) เทียบกับ 90°
#   _DIM_TOL       = ค่าเผื่อระยะ (mm) ตอนตรวจว่าเส้นตรงอยู่บนด้านของสี่เหลี่ยม
#   _MIN_DEPTH     = ความลึกต่ำสุด (mm) ที่ถือว่าเป็นช่อง
# ==============================================================================
import math

import numpy as np

from core.models import StepPocket

_PARALLEL_TOL  = 1e-3
_ARC_SWEEP_TOL = 0.05
_DIM_TOL       = 0.01
_MIN_DEPTH     = 0.1


def _vec(p):
    return np.array([p.x, p.y, p.z], dtype=float)


def _edge_dir(edge):
    d = _vec(edge.endPoint()) - _vec(edge.startPoint())
    n = float(np.linalg.norm(d))
    return d / n if n > 1e-9 else None


def _edge_samples(edge, n=5):
    return [_vec(edge.positionAt(t)) for t in np.linspace(0.0, 1.0, n)]


def _classify_rect_wire(wire, normal):
    """ตรวจ wire ว่าเป็นสี่เหลี่ยม (มุมคม/มุมโค้ง) หรือแคปซูล (slot) หรือไม่
    คืน dict(center, u, v, half_u, half_v, corner_radius) หรือ None
    (slot: corner_radius == half_v)"""
    edges = wire.Edges()
    lines = [e for e in edges if e.geomType() == 'LINE']
    arcs  = [e for e in edges if e.geomType() == 'CIRCLE']
    if len(lines) + len(arcs) != len(edges):
        return None
    if len(lines) == 4 and len(arcs) in (0, 4):
        is_slot = False
    elif len(lines) == 2 and len(arcs) >= 2:
        is_slot = True
    else:
        return None

    dirs = [_edge_dir(e) for e in lines]
    if any(d is None for d in dirs):
        return None

    # แกน u = ทิศของเส้นที่ยาวที่สุด, v ตั้งฉากในระนาบปากช่อง
    longest = max(range(len(lines)), key=lambda i: lines[i].Length())
    u = dirs[longest] - float(np.dot(dirs[longest], normal)) * normal
    u /= np.linalg.norm(u)
    v = np.cross(normal, u)

    n_par = n_perp = 0
    for d in dirs:
        c = abs(float(np.dot(d, u)))
        if c > 1.0 - _PARALLEL_TOL:   n_par += 1
        elif c < _PARALLEL_TOL:       n_perp += 1
        else:                         return None
    if n_par != 2 or n_perp != (0 if is_slot else 2):
        return None

    corner_r = 0.0
    if arcs:
        radii, sweeps = [], []
        for a in arcs:
            try:
                r = float(a.radius())
            except Exception:
                return None
            if r <= 0:
                return None
            radii.append(r)
            sweeps.append(a.Length() / r)
        if max(radii) - min(radii) > _DIM_TOL:
            return None
        if is_slot:
            # ปลายครึ่งวงกลม 2 ด้าน (อาจถูกแบ่งเป็นหลายเส้น) — มุมกวาดรวม 360°
            if (abs(sum(sweeps) - 2 * math.pi) > 2 * _ARC_SWEEP_TOL
                    or max(sweeps) > math.pi + _ARC_SWEEP_TOL):
                return None
        elif any(abs(sw - math.pi / 2) > _ARC_SWEEP_TOL for sw in sweeps):
            return None
        corner_r = float(np.mean(radii))

    pts = np.array([p for e in edges for p in _edge_samples(e)])
    pu, pv = pts @ u, pts @ v
    cu, cv = (pu.min() + pu.max()) / 2.0, (pv.min() + pv.max()) / 2.0
    half_u, half_v = (pu.max() - pu.min()) / 2.0, (pv.max() - pv.min()) / 2.0
    if half_v < _DIM_TOL or corner_r > half_v + _DIM_TOL:
        return None
    if is_slot:
        if abs(corner_r - half_v) > max(_DIM_TOL, 1e-3 * half_v):
            return None
        corner_r = float(half_v)

    # เส้นตรงทุกเส้นต้องอยู่บนด้านใดด้านหนึ่งของสี่เหลี่ยมจริง
    tol = max(_DIM_TOL, 1e-4 * half_u)
    for e in lines:
        m = _vec(e.positionAt(0.5))
        on_u_side = abs(abs(float(m @ u) - cu) - half_u) < tol
        on_v_side = abs(abs(float(m @ v) - cv) - half_v) < tol
        if not (on_u_side or on_v_side):
            return None

    p0 = pts[0]
    center = p0 + (cu - float(p0 @ u)) * u + (cv - float(p0 @ v)) * v
    return dict(center=center, u=u, v=v, half_u=float(half_u),
                half_v=float(half_v), corner_radius=corner_r)


def extract_rect_pockets(step_data, mesh_centroid, log=print):
    """คืน (pockets, corner_faces)
      pockets      : list ของ StepPocket (พิกัดเทียบ mesh centroid แบบเดียวกับ
                     StepHole ใน step_extractor.py)
      corner_faces : list ของ cadquery Face ทรงกระบอกที่เป็นมุมโค้งของช่อง —
                     ผู้เรียกต้องข้ามไม่นับเป็นรูกลม"""
    offset = np.array(mesh_centroid, dtype=float)
    pockets, corner_faces, seen = [], [], set()

    for solid in step_data.solids().vals():
        for face in solid.Faces():
            if face.geomType() != 'PLANE':
                continue
            inner_wires = face.innerWires()
            if not inner_wires:
                continue
            normal = _vec(face.normalAt())          # ชี้ออกจากเนื้อวัสดุ
            normal /= np.linalg.norm(normal)

            for wire in inner_wires:
                rect = _classify_rect_wire(wire, normal)
                if rect is None:
                    continue

                walls = []
                for e in wire.Edges():
                    for wf in e.ancestors(solid, "Face"):
                        if not wf.isSame(face) and not any(wf.isSame(w) for w in walls):
                            walls.append(wf)
                if not walls:
                    continue

                # ระยะของผนังตามแนว normal: ช่องต้องลึก "ลง" ในเนื้อวัสดุ (-normal)
                heights = [float((_vec(vx.Center()) - rect['center']) @ normal)
                           for wf in walls for vx in wf.Vertices()]
                depth = -min(heights)
                if depth < _MIN_DEPTH or max(heights) > _DIM_TOL:
                    log(f"  POCKET SKIP: rectangular loop is a boss/step, not a pocket "
                        f"(wall extent {min(heights):.2f}..{max(heights):.2f})")
                    continue

                corner_faces += [wf for wf in walls if wf.geomType() == 'CYLINDER']

                open_3d = rect['center'] - offset
                deep_3d = open_3d - depth * normal
                mid = (open_3d + deep_3d) / 2.0
                key = (tuple(np.round(mid, 1)), round(rect['half_u'], 2),
                       round(rect['half_v'], 2), round(depth, 2))
                if key in seen:          # ช่องทะลุ: เจอซ้ำที่ปากอีกด้านหนึ่ง
                    continue
                seen.add(key)

                pockets.append(StepPocket(open_3d, deep_3d, tuple(-normal), rect['u'],
                                          rect['half_u'], rect['half_v'],
                                          rect['corner_radius']))
                log(f"  POCKET: {rect['half_u']*2:.2f}x{rect['half_v']*2:.2f} "
                    f"R{rect['corner_radius']:.2f} depth={depth:.2f}")

    return pockets, corner_faces
