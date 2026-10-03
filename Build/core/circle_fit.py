# ==============================================================================
# core/circle_fit.py — หาวงกลมที่เข้ากับจุดวัด 1 ชั้นได้ดีที่สุด (Least Squares)
# ==============================================================================
# VERSION: 01
#
# หน้าที่: รับจุด 3 มิติของ 1 layer ของรูกลม (จุดที่คาดหวังจาก CAD หรือจุดที่วัดได้
# หลังชดเชยรัศมีหัวโพรบแล้ว) → คืนจุดศูนย์กลาง, เส้นผ่าศูนย์กลาง และค่าความกลม
# แบบเดียวกับที่ซอฟต์แวร์เครื่อง CMM รายงานสำหรับ "circle element"
#
# วิธีคำนวณ:
#   1) ระนาบของชั้น — SVD ของจุดรอบค่าเฉลี่ย (แกนที่แปรผันน้อยสุด = แนวแกนรู)
#   2) ค่าเริ่มต้นจากสมการพีชคณิต (Kåsa): x² + y² + Dx + Ey + F = 0 แก้แบบ Least Squares
#   3) ปรับให้เป็น Least Squares เชิงเรขาคณิตจริง (ลด Σ(|pᵢ − c| − r)²) ด้วย
#      Gauss–Newton — ตรงกับวงกลมอ้างอิง LSCI ของ ISO 12181 / BS 7172
#   ความกลม (Roundness) = รัศมีสูงสุด − รัศมีต่ำสุด เทียบกับจุดศูนย์กลางที่ fit ได้
#   ต้องมีอย่างน้อย 4 จุด (3 จุดผ่านวงกลมได้พอดีเสมอ ความกลมจึงเป็น 0 ไม่มีความหมาย)
#
# ตัวแปรสำคัญที่ปรับจูนได้: _GN_ITERS, _GN_TOL
# ==============================================================================
import numpy as np

_GN_ITERS = 50      # จำนวนรอบสูงสุดของ Gauss–Newton
_GN_TOL   = 1e-10   # หยุดเมื่อขั้นการปรับเล็กกว่านี้ (mm)


def fit_circle_3d(points):
    """Least-squares circle ของจุด 3 มิติที่อยู่บนระนาบเดียวกัน (≥ 3 จุด)
    คืน dict หรือ None ถ้าจุดน้อยเกิน/เรียงเป็นเส้นตรง:
      center    : (x, y, z) จุดศูนย์กลาง
      radius    : รัศมี, diameter: เส้นผ่าศูนย์กลาง
      normal    : เวกเตอร์หน่วยตั้งฉากระนาบ (แนวแกนรู)
      residuals : ระยะของแต่ละจุดจากวงกลม (+ = อยู่นอกวง) เรียงตามลำดับจุดที่ส่งเข้ามา
      roundness : รัศมีสูงสุด − ต่ำสุด (None ถ้าน้อยกว่า 4 จุด)
      n         : จำนวนจุด"""
    P = np.asarray(points, dtype=float)
    if P.ndim != 2 or len(P) < 3:
        return None
    c0 = P.mean(axis=0)
    _u, s, vt = np.linalg.svd(P - c0)
    if s[1] < 1e-9:                      # จุดเรียงเป็นเส้นตรง — ไม่มีวงกลม
        return None
    u, v, normal = vt[0], vt[1], vt[2]
    x = (P - c0) @ u
    y = (P - c0) @ v

    # ค่าเริ่มต้น: Kåsa
    A = np.c_[x, y, np.ones(len(x))]
    sol, *_ = np.linalg.lstsq(A, -(x * x + y * y), rcond=None)
    a, b = -sol[0] / 2.0, -sol[1] / 2.0
    r = float(np.sqrt(max(a * a + b * b - sol[2], 1e-12)))

    # Gauss–Newton: ลดผลรวมกำลังสองของระยะจริงถึงวงกลม
    for _ in range(_GN_ITERS):
        dx, dy = x - a, y - b
        d = np.hypot(dx, dy)
        d = np.where(d < 1e-12, 1e-12, d)
        J = np.c_[-dx / d, -dy / d, -np.ones(len(x))]
        step, *_ = np.linalg.lstsq(J, -(d - r), rcond=None)
        a, b, r = a + step[0], b + step[1], r + step[2]
        if np.abs(step).max() < _GN_TOL:
            break

    res = np.hypot(x - a, y - b) - r
    return {
        'center':    tuple(float(c) for c in (c0 + a * u + b * v)),
        'radius':    float(r),
        'diameter':  float(2.0 * r),
        'normal':    tuple(float(c) for c in normal),
        'residuals': [float(e) for e in res],
        'roundness': float(res.max() - res.min()) if len(P) >= 4 else None,
        'n':         int(len(P)),
    }
