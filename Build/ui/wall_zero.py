# ==============================================================================
# ui/wall_zero.py — หา X0 Y0 = กึ่งกลางชิ้นงาน (+ Z0 = ผิวบน) ด้วยการแตะผนังด้านนอก 4 ด้าน
# ==============================================================================
# VERSION: 03
# CHANGE LOG (v02 -> v03):
#   เปลี่ยนวิธีเป็น "เริ่มจากกลางชิ้นงาน" (แบบที่ทดสอบกับ plate_with_holes บนเครื่องจริง):
#   ผู้ใช้ jog ลูกบอลไปกลางชิ้นงาน (ประมาณ) ให้ก้นลูกบอลแตะผิวบนพอดี แล้วกด Find centre
#     1. ตั้ง X0 Y0 Z0 ชั่วคราวที่จุดนั้น (Z0 = ผิวบน — ก้นลูกบอลแตะผิว) แล้วยก Z ก่อนเสมอ
#     2. แกน X: ไปนอกผนังซ้าย (ครึ่งความกว้าง + gap) → ลง → แตะเข้าหาชิ้นงาน → ยก →
#        ไปนอกผนังขวา → ลง → แตะ → ยก → ตั้ง X0 = กึ่งกลางสองจุดที่แตะ (G10 L2) → ไป X0
#     3. แกน Y: แบบเดียวกัน (ผนังหน้า/หลัง) → ตั้ง Y0
#     4. ไปที่ X0 Y0 (ความสูงยก) แล้วลดลงช้า ๆ ให้ก้นลูกบอลแตะผิว (Z0) — เลือกปิดได้
#   ขนาดลูกบอลและระยะโก่งก่อนทริกหักล้างกันเองที่กึ่งกลาง จึงไม่ต้อง calibrate ก่อน
#   ทุกการลด Z เกิดนอกขอบชิ้นงาน gap มม. (ค่าเริ่มต้น 30) — กันกรณีวางไม่ตรงกลาง /
#   ขนาดชิ้นงานหรือ steps/mm คลาด (หัวโพรบส่วนใหญ่ไม่ทริกแนว Z: ลงบนผิว = ชน)
# CHANGE LOG (v01 -> v02): far-side gap (แบบเริ่มจากนอกผนัง — แทนที่แล้วใน v03)
#
# ความปลอดภัย: ทุกขั้นรอเครื่อง Idle ก่อนส่งขั้นต่อไป, ALARM / แตะไม่โดน / หมดเวลา →
# ส่ง Stop และหยุด (zero ที่ตั้งไปแล้วในขั้นก่อนหน้ายังอยู่ — แจ้งผู้ใช้), งานนี้ไม่ถูก
# บันทึกเป็นไฟล์ log งานวัด (OpenBuildsLogger.suppress_logs)
#
# ตัวแปรสำคัญที่ปรับจูนได้:
#   _TIMEOUT_S   = เวลาสูงสุดทั้งงาน (วินาที)
#   _SEARCH_PAD  = ระยะค้นหา = gap + ค่านี้ (เผื่อวางไม่ตรงกลาง/ขนาดคลาด)
#   _BACKOFF     = ถอยออกหลังแตะ (มม.)
# ==============================================================================
import re
import time

_PRB = re.compile(r"\[PRB:\s*([-+\d.]+)\s*,\s*([-+\d.]+)\s*,\s*([-+\d.]+)\s*:\s*(\d)\s*\]")
_TIMEOUT_S = 600.0
_SEARCH_PAD = 20.0
_BACKOFF = 2.0
_COORD_P = {"G54": 1, "G55": 2, "G56": 3, "G57": 4, "G58": 5, "G59": 6}


class CentreSettings:
    def __init__(self, width: float, length: float, tip_d: float, gap: float = 30.0, lift: float = 5.0,
                 depth: float = 4.0, feed: float = 100.0, lower_at_end: bool = True):
        self.width, self.length, self.tip_d = float(width), float(length), float(tip_d)
        self.gap, self.lift, self.depth, self.feed = float(gap), float(lift), float(depth), float(feed)
        self.lower_at_end = bool(lower_at_end)

    @property
    def search(self) -> float:
        return self.gap + _SEARCH_PAD

    def outside(self, axis: str) -> float:
        """ระยะจากจุดเริ่มถึงจุดลด Z นอกผนัง (ครึ่งขนาด + gap)"""
        return (self.width if axis == "X" else self.length) / 2.0 + self.gap

    def validate(self) -> str:
        if self.width <= 0 or self.length <= 0:
            return "ขนาดชิ้นงานต้องมากกว่า 0"
        if self.gap < 10.0:
            return "Gap ควรอย่างน้อย 10 มม. (เผื่อวางไม่ตรงกลาง)"
        if self.lift < 2.0 or self.depth <= 0 or self.feed <= 0:
            return "Z lift ≥ 2 มม., Probe depth และ Feed ต้องมากกว่า 0"
        return ""


def side_gcode(axis: str, sign: int, s: CentreSettings) -> str:
    """แตะผนังด้าน sign (−1 = ซ้าย/หน้า, +1 = ขวา/หลัง) — เริ่มและจบที่ความสูง Z+lift"""
    a = axis
    return "\n".join([
        "G90",
        f"G0 Z{s.lift:.3f}",
        f"G0 {a}{sign * s.outside(a):.3f}",            # ไปนอกผนัง (ที่ความสูงยก)
        f"G0 Z{-s.depth:.3f}",                          # ลดลงข้างผนัง
        f"G91 G38.2 {a}{-sign * s.search:.3f} F{s.feed:.0f}",   # แตะเข้าหาชิ้นงาน
        f"G0 {a}{sign * _BACKOFF:.3f}",
        "G90",
        f"G0 Z{s.lift:.3f}",
    ])


class CentreRun:
    """หา X0 Y0 (กึ่งกลาง) + Z0 (ผิวบน) — เรียก start() แล้วรอ on_done(text, ok)"""

    def __init__(self, app, logger, settings: CentreSettings, on_status, on_done):
        self.app, self.logger, self.s = app, logger, settings
        self.on_status, self.on_done = on_status, on_done
        self.active = False
        self.coord = "G54"
        self.prb = []
        self.result = {}
        self.offset = {}
        self._steps = []
        self._i = -1
        self._need = 0
        self._sent_at = 0.0
        self._deadline = 0.0

    # ------------------------------------------------------------------
    def start(self):
        s = self.s
        p = lambda: _COORD_P.get(self.coord, 1)
        self._steps = [
            ("Set X0 Y0 Z0 here, lift", lambda: f"G10 L20 P{p()} X0 Y0 Z0\nG90\nG0 Z{s.lift:.3f}", 0),
            ("X: left wall", lambda: side_gcode("X", -1, s), 1),
            ("X: right wall", lambda: side_gcode("X", +1, s), 1),
            ("X0 = centre", lambda: self._set_axis("X"), 0),
            ("Y: front wall", lambda: side_gcode("Y", -1, s), 1),
            ("Y: back wall", lambda: side_gcode("Y", +1, s), 1),
            ("Y0 = centre", lambda: self._set_axis("Y"), 0),
        ]
        if s.lower_at_end:
            self._steps.append(("Lower to Z0", lambda: "G90\nG0 X0 Y0\nG0 Z1\nG1 Z0 F100", 0))
        self.active, self.prb, self.result, self._i = True, [], {}, -1
        self._deadline = time.monotonic() + _TIMEOUT_S
        self.logger.on_event.append(self._on_event)
        self.logger.suppress_logs(_TIMEOUT_S + 30)
        self._next()
        self.app.root.after(500, self._watchdog)

    def stop(self):
        if self.active:
            try:
                self.logger.stop_machine()
            finally:
                self._end("Stopped — the machine was halted." + self._done_note(), ok=False)

    # ------------------------------------------------------------------
    def _set_axis(self, axis: str) -> str:
        i = {"X": 0, "Y": 1}[axis]
        lo, hi = self.prb[-2][i], self.prb[-1][i]
        mid, span = (lo + hi) / 2.0, abs(hi - lo)
        start = self.offset.get(axis.lower())   # ตอนนี้ axis0 ยังเป็นจุดเริ่ม (ตั้งในขั้นแรก)
        shift = mid - float(start) if start is not None else 0.0
        self.result[axis] = (lo, hi, mid, span, shift)
        p = _COORD_P.get(self.coord, 1)
        return f"G10 L2 P{p} {axis}{mid:.3f}\nG90\nG0 X0 Y0"

    def _next(self):
        self._i += 1
        if self._i >= len(self._steps):
            self._finish()
            return
        label, make, need = self._steps[self._i]
        try:
            code = make()
            self._need = len(self.prb) + need
            self.logger.send_gcode(code)
        except Exception as e:
            self._end(f"Could not send '{label}' to OpenBuilds: {e}" + self._done_note(), ok=False)
            return
        self._sent_at = time.monotonic()
        self.on_status(f"Step {self._i + 1}/{len(self._steps)}: {label}…")

    def _watchdog(self):
        if not self.active:
            return
        if time.monotonic() > self._deadline:
            self.stop()
            return
        self.app.root.after(500, self._watchdog)

    def _on_event(self, name, payload):
        if not self.active:
            return
        if name == "status" and isinstance(payload, dict):
            m = payload.get("machine") or {}
            self.coord = (m.get("modals") or {}).get("coordinatesys") or self.coord
            off = (m.get("position") or {}).get("offset")
            if isinstance(off, dict) and self._i >= 1:   # หลังขั้นแรก (ตั้ง zero ที่จุดเริ่ม) แล้ว
                self.offset = dict(off)
            comms = payload.get("comms") or {}
            if comms.get("alarm"):
                self._fail(f"ALARM {comms.get('alarm')}")
                return
            idle = str(comms.get("runStatus", "")).lower() == "idle" and not comms.get("queue")
            if idle and time.monotonic() - self._sent_at > 1.0:
                if len(self.prb) >= self._need:
                    self._next()
                else:
                    self._fail("a probe move ended without touching a wall "
                               f"(no wall within {self.s.search:g} mm)")
        elif name == "data" and isinstance(payload, dict):
            resp = str(payload.get("response") or "")
            if "ALARM" in resp.upper():
                self._fail(resp.strip())
                return
            m = _PRB.search(resp)
            if m:
                if m.group(4) != "1":
                    self._fail("a probe move ended without touching a wall")
                    return
                self.prb.append(tuple(float(m.group(k)) for k in (1, 2, 3)))

    def _fail(self, why: str):
        try:
            self.logger.stop_machine()
        finally:
            self._end(f"{why} — stopped. Clear an alarm with $X, check the start position "
                      f"(near the centre, ball touching the top) and try again." + self._done_note(), ok=False)

    def _done_note(self) -> str:
        done = [a for a in ("X", "Y") if a in self.result and self._i > (3 if a == "X" else 6)]
        if self._i >= 1:
            return ("\nZ0 was set at the start point" + (f"; {', '.join(a + '0' for a in done)} set at the centre"
                                                        if done else "; X0/Y0 are still the start point") + ".")
        return ""

    def _finish(self):
        lines = ["Centre found — X0 Y0 at the centre of the part, Z0 on the top surface."]
        for a in ("X", "Y"):
            lo, hi, mid, span, shift = self.result[a]
            size = self.s.width if a == "X" else self.s.length
            lines.append(f"{a}: walls {lo:.3f} / {hi:.3f} (machine) → size ≈ {span - self.s.tip_d:.3f} mm "
                         f"(CAD {size:.3f}); centre is {shift:+.3f} mm from the start point")
        self._end("\n".join(lines), ok=True)

    def _end(self, text, ok):
        self.active = False
        if self._on_event in self.logger.on_event:
            self.logger.on_event.remove(self._on_event)
        self.logger.suppress_logs(8)
        self.on_done(text, ok)
