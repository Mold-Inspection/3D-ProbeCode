# ==============================================================================
# core/channel_extractor.py — สกัด "ร่องเปิด" (open channel / runner) จาก B-Rep
# ==============================================================================
# VERSION: 01
# หน้าที่: หาร่องยาวตรงที่เปิดด้านบน เช่น runner ของแม่พิมพ์ (ก้นโค้ง ผนังข้างตรง
# หรือเอียง draft ปลายกลม และ/หรือปลายที่วิ่งเข้าไปรวมกับช่องอื่น) แล้วคืนเป็น
# core.models.StepChannel — เดิมผิวโค้งของร่องแบบนี้ถูกนับเป็น "รูกลม" ปลอมหลายสิบรู
#
# วิธีตรวจจับ:
#   1. ก้นร่อง = ผิวทรงกระบอก "เว้า" ที่กวาดไม่ถึงวงกลม (< 200°) และยาวตามแกน
#      มากกว่า _MIN_LEN_RATIO × รัศมี (รูเจาะธรรมดากวาดครบ 360° หรือแบ่ง 2 ครึ่ง
#      ที่รวมกันได้ทรงกระบอกเต็ม) — จับกลุ่มผิวที่แกนร่วมกัน = ร่อง 1 เส้น
#   2. ทิศ "ปากร่อง" = ทิศตรงข้ามกับด้านที่ผิวก้นร่องอยู่ (เทียบกับแกนทรงกระบอก)
#   3. ระยะผนังข้าง/ก้น/ปลาย วัดด้วยการยิงเส้นตรงตัดกับ B-Rep จริง
#      (IntCurvesFace_ShapeIntersector) — ได้ค่าเป๊ะตามแบบ ใช้ได้กับหน้าตัดทุก
#      รูปแบบ (ก้นกลม, ก้นแบน, ผนังเอียง) และใช้ตัดสินว่าปลายร่องปิดหรือเปิด
#
# คืนค่า (channels, skip_faces, openings):
#   channels   : list ของ StepChannel
#   skip_faces : ผิวโค้งทั้งหมดที่เป็นส่วนของร่อง — step_extractor ต้องข้าม
#                (ไม่ให้กลายเป็นรูกลมปลอม)
#   openings   : ปลายเปิดของร่อง [(จุดกลางปลายเปิดที่ผิวบน, ทิศจากปลายเปิดเข้าไปในร่อง,
#                ครึ่งความกว้างผิวบน)] — step_extractor ใช้กันมุมโพรบของรูที่ร่อง
#                วิ่งเข้าไป (ตรงนั้นไม่มีผนัง โพรบจะเดินทะลุเข้าไปในร่อง)
#
# ข้อจำกัด: ร่องต้องตรง (ไม่โค้งตามแนวยาว) และหน้าตัดคงที่ตลอดความยาว
#
# ตัวแปรสำคัญที่ปรับจูนได้:
#   _MAX_SWEEP_DEG   = มุมกวาดสูงสุดของผิวก้นร่อง (เกินนี้ถือเป็นรูธรรมดา)
#   _MIN_LEN_RATIO   = ความยาวขั้นต่ำของร่อง เทียบกับรัศมีก้นร่อง
#   _OPEN_END_MARGIN = ระยะเว้นจากปลายเปิดก่อนวางจุดโพรบแรก (mm, บวกครึ่งความกว้าง)
#   _CLOSED_END_MARGIN = ระยะเว้นจากปลายปิดก่อนวางจุดโพรบผนังข้าง (mm)
#   _PROFILE_SAMPLES = จำนวนระดับความลึกที่วัดความกว้างร่อง
# ==============================================================================
import math

import numpy as np

from core.models import StepChannel

_MAX_SWEEP_DEG     = 200.0
_MIN_LEN_RATIO     = 2.5
_OPEN_END_MARGIN   = 1.0
_CLOSED_END_MARGIN = 0.5
_PROFILE_SAMPLES   = 33
_AXIS_TOL          = 0.05


class _Rays:
    """ยิงเส้นตรงตัด B-Rep ทั้งชิ้น — คืนระยะถึงผิวแรกที่ชน (None = ไม่ชนอะไร)"""
    def __init__(self, shape):
        from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
        self._it = IntCurvesFace_ShapeIntersector()
        self._it.Load(shape, 1e-7)

    def dist(self, p, d, max_d: float = 1e4):
        from OCP.gp import gp_Lin, gp_Pnt, gp_Dir
        self._it.Perform(gp_Lin(gp_Pnt(*map(float, p)), gp_Dir(*map(float, d))), 1e-6, max_d)
        if not self._it.IsDone() or self._it.NbPnt() == 0:
            return None
        return min(self._it.WParameter(k) for k in range(1, self._it.NbPnt() + 1))


def _floor_candidates(faces, log):
    """ผิวทรงกระบอกเว้าที่กวาดไม่ครบวง และยาวพอจะเป็นก้นร่อง"""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepGProp import BRepGProp_Face
    from OCP.BRepTools import BRepTools
    from OCP.gp import gp_Pnt, gp_Vec

    out = []
    for idx, face in enumerate(faces):
        if face.geomType() != 'CYLINDER':
            continue
        try:
            cyl = BRepAdaptor_Surface(face.wrapped).Cylinder()
            ax = cyl.Axis()
            C = np.array([ax.Location().X(), ax.Location().Y(), ax.Location().Z()])
            A = np.array([ax.Direction().X(), ax.Direction().Y(), ax.Direction().Z()])
            r = float(cyl.Radius())
            u0, u1, v0, v1 = BRepTools.UVBounds_s(face.wrapped)   # u = มุม, v = ระยะตามแกน
            if math.degrees(u1 - u0) >= _MAX_SWEEP_DEG or (v1 - v0) < _MIN_LEN_RATIO * r:
                continue
            p, n = gp_Pnt(), gp_Vec()
            BRepGProp_Face(face.wrapped).Normal(0.5 * (u0 + u1), 0.5 * (v0 + v1), p, n)
            P = np.array([p.X(), p.Y(), p.Z()])
            N = np.array([n.X(), n.Y(), n.Z()])
            rel = P - C
            radial = rel - float(np.dot(rel, A)) * A
            if float(np.dot(N, radial)) >= 0:   # นูน = ผิวด้านนอก ไม่ใช่ก้นร่อง
                continue
            # แกนแบบ canonical: ทิศชี้ไปทางค่าบวกของแกนที่ใหญ่สุด, จุดบนแกนที่ใกล้ origin
            if A[int(np.argmax(np.abs(A)))] < 0:
                A = -A
            base = C - float(np.dot(C, A)) * A
            s_c = float(np.dot(C, A))
            s0, s1 = sorted((s_c + v0 * float(np.dot(np.array([ax.Direction().X(), ax.Direction().Y(),
                                                               ax.Direction().Z()]), A)),
                             s_c + v1 * float(np.dot(np.array([ax.Direction().X(), ax.Direction().Y(),
                                                               ax.Direction().Z()]), A))))
            out.append(dict(face=face, idx=idx + 1, base=base, A=A, r=r, s0=s0, s1=s1,
                            radial=radial / max(np.linalg.norm(radial), 1e-12)))
        except Exception as e:
            log(f"channel: cylinder face#{idx + 1} skipped ({e!r})")
    return out


def _group_coaxial(cands):
    """ผิวก้นร่องเส้นเดียวกัน: รัศมีเท่ากัน แกนขนาน ช่วงความยาวซ้อนกัน และแกนห่างกัน
    ไม่เกินรัศมี — ก้นร่องมักถูกแบ่งเป็น 2 ผิวซ้าย/ขวา (บางแบบมีแถบเรียบคั่นตรงกลาง
    ทำให้แกนของ 2 ผิวไม่ตรงกันพอดี) แต่ร่อง 2 เส้นที่อยู่แนวเดียวกันคนละช่วงจะไม่ถูกรวม"""
    groups = []
    for c in cands:
        for g in groups:
            h = g[0]
            if (abs(c['r'] - h['r']) < 0.01 and abs(abs(float(np.dot(c['A'], h['A']))) - 1.0) < 1e-6
                    and np.linalg.norm(c['base'] - h['base']) <= c['r']
                    and min(c['s1'], h['s1']) - max(c['s0'], h['s0']) > -_AXIS_TOL):
                g.append(c)
                break
        else:
            groups.append([c])
    return groups


def _profile(rays, floor_pt, open_dir, across, depth):
    """ระยะผนังข้าง +across / -across ที่ความลึก 0..depth จากผิวบน (ผิวบนก่อน)"""
    depths = np.linspace(0.0, depth, _PROFILE_SAMPLES)
    eps = min(0.02, depth * 0.01)
    wp, wm = [], []
    for d in depths:
        h = float(np.clip(depth - d, eps, depth - eps))
        q = floor_pt + h * open_dir
        a, b = rays.dist(q, across), rays.dist(q, -across)
        if a is None or b is None:
            return None
        wp.append(a)
        wm.append(b)
    return depths, np.array(wp), np.array(wm)


def extract_channels(step_data, mesh_centroid, log=print, exclude_faces=()):
    shape = step_data.val().wrapped
    faces = step_data.faces().vals()
    rays  = _Rays(shape)
    cen   = np.asarray(mesh_centroid, dtype=float)

    channels, skip, openings = [], [], []
    cands = [c for c in _floor_candidates(faces, log)
             if not any(c['face'].isSame(x) for x in exclude_faces)]   # มุมโค้งของช่องสี่เหลี่ยม
    for group in _group_coaxial(cands):
        r, A = group[0]['r'], group[0]['A']
        s0, s1 = min(c['s0'] for c in group), max(c['s1'] for c in group)
        base = np.mean([c['base'] for c in group], axis=0)
        # ปากร่อง = ทิศตรงข้ามกับด้านที่ผิวก้นร่องอยู่
        m = np.mean([c['radial'] for c in group], axis=0)
        if np.linalg.norm(m) < 0.3:
            continue   # ผิวล้อมรอบแกนหลายด้าน — ไม่ใช่ร่องเปิดด้านเดียว
        open_dir = -m / np.linalg.norm(m)
        # ทิศข้ามร่อง = แกน v ของ G-code (v = แกนเข้าเนื้อ × u_dir) — profile_w_plus วัดไปทาง +v
        across = np.cross(-open_dir, A)
        across /= np.linalg.norm(across)

        s_mid = 0.5 * (s0 + s1)
        axis_mid = base + s_mid * A
        f = rays.dist(axis_mid, -open_dir)
        if f is None:
            continue
        floor_mid = axis_mid - f * open_dir

        # ผิวบน: ไล่ขึ้นจากก้นร่องจนเส้นข้างไม่ชนผนังใกล้ ๆ อีก (หยาบ 0.25 แล้วละเอียด)
        limit = max(6.0 * r, 10.0)

        def inside(h):
            q = floor_mid + h * open_dir
            a, b = rays.dist(q, across), rays.dist(q, -across)
            return a is not None and b is not None and a < limit and b < limit

        h, step = 0.05, 0.25
        if not inside(h):
            continue
        while h < 200.0 and inside(h + step):
            h += step
        lo_h, hi_h = h, h + step
        for _ in range(12):
            mid = 0.5 * (lo_h + hi_h)
            lo_h, hi_h = (mid, hi_h) if inside(mid) else (lo_h, mid)
        depth = lo_h
        if depth < 0.3:
            continue

        # ร่องต้อง "เปิดออกสู่ภายนอก": เหนือปากร่องต้องเป็นที่โล่ง — ตัดผิวโค้งที่หันเข้าหา
        # ช่องอื่น (เช่นมุมโค้งในช่องสี่เหลี่ยม ซึ่งเส้นจะชนผนังฝั่งตรงข้าม) และท่อภายใน
        above = rays.dist(floor_mid + (depth + 0.05) * open_dir, open_dir)
        if above is not None and above < 10.0 * max(depth, r):
            log(f"channel candidate at s=[{s0:.1f},{s1:.1f}] r={r:.2f}: not open to the outside — skipped")
            continue
        # ทิศปากร่องต้องตั้งฉากกับแนวร่อง (ร่องวิ่งไปตามผิวงาน ไม่ใช่ทิ่มลงไป)
        if abs(float(np.dot(open_dir, A))) > 0.2:
            continue

        prof = _profile(rays, floor_mid, open_dir, across, depth)
        if prof is None:
            log(f"channel at s=[{s0:.1f},{s1:.1f}]: wall profile failed — skipped")
            continue
        depths, w_plus, w_minus = prof
        w_top = float(max(w_plus[0], w_minus[0]))
        half_len = 0.5 * (s1 - s0)

        # ปลายร่อง: ปิด = มีผนังปลายใกล้ ๆ, เปิด = ร่องวิ่งต่อเข้าไปในช่องอื่น
        closed, margins = {}, {}
        for sign, s_end in ((+1, s1), (-1, s0)):
            floor_end = floor_mid + (s_end - s_mid) * A
            q_mid = floor_end + 0.5 * depth * open_dir
            e = rays.dist(q_mid, sign * A)
            if e is not None and e <= 2.0 * w_top + 1.0:
                prof_e = []
                for d in depths:
                    hh = float(np.clip(depth - d, 0.02, depth - 0.02))
                    ed = rays.dist(floor_end + hh * open_dir, sign * A)
                    prof_e.append(ed if ed is not None else e)
                closed[sign] = prof_e
                margins[sign] = _CLOSED_END_MARGIN
            else:
                margins[sign] = w_top + _OPEN_END_MARGIN
                top_end = floor_end + depth * open_dir
                openings.append((tuple(top_end - cen), tuple(-sign * A), w_top))

        st_lo, st_hi = -half_len + margins[-1], half_len - margins[+1]
        if st_hi < st_lo:
            st_lo = st_hi = 0.0

        open_3d = floor_mid + depth * open_dir - cen
        deep_3d = floor_mid - cen
        channels.append(StepChannel(open_3d, deep_3d, A, half_len, st_lo, st_hi,
                                    depths, w_plus, w_minus, closed))
        log(f"CHANNEL r={r:.2f} len={2 * half_len:.2f} width_top={2 * w_top:.2f} depth={depth:.2f} "
            f"closed_ends={sorted(closed)} (floor faces {[c['idx'] for c in group]})")

        # ผิวโค้งที่เป็นส่วนของร่อง (ก้น, ปลายกลม, ผนังเอียงปลาย) — ไม่ให้กลายเป็นรูปลอม
        # ปลายปิด: เลยปลายไปถึงผนังปลาย; ปลายเปิด: เลยเข้าไปอีกครึ่งความกว้าง (ผิวโค้งรอยต่อ
        # ระหว่างก้นร่องกับช่องที่ร่องวิ่งเข้าไป ไม่ใช่ผนังของช่องนั้น)
        ext = {s: (max(closed[s]) + 1.0 if s in closed else w_top) for s in (+1, -1)}
        for face in faces:
            if face.geomType() not in ('CYLINDER', 'CONE', 'TORUS', 'SPHERE'):
                continue
            bb = face.BoundingBox()
            c = np.array([0.5 * (bb.xmin + bb.xmax), 0.5 * (bb.ymin + bb.ymax), 0.5 * (bb.zmin + bb.zmax)])
            rel = c - floor_mid
            s_rel = float(np.dot(rel, A))
            if not (-half_len - ext[-1] - 1e-6 <= s_rel <= half_len + ext[+1] + 1e-6):
                continue
            if abs(float(np.dot(rel, across))) > w_top + 0.5:
                continue
            if not (-0.5 <= float(np.dot(rel, open_dir)) <= depth + 0.5):
                continue
            skip.append(face)

    return channels, skip, openings
