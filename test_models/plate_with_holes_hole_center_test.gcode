; ============================================
; 3D ProbeCode - HOLE CENTER TEST
; Object: plate_with_holes.step  View: Top
; Size: X 226.630 mm  x  Y 299.040 mm   Holes: 2
; BEFORE RUNNING: put the needle at the CENTER of the
;   object (as seen on screen) and Set Zero X/Y/Z there.
; Visits the center of every hole selected for inspection, then
;   returns to the zero point. Needle stays lifted the whole time.
;   X+ = right, Y+ = toward back of machine (up on screen).
; No G92 / work-offset change: uses the zero you set.
; ============================================
G21 ; mm units
G90 ; absolute positioning
G94 ; feed rate mode: units/min
G0 Z15.000 ; lift needle
G1 X-5.845 Y70.160 F500 ; -> 1/2 hole 2 (37.80×24.60 R7.8) center
G4 P2.0 ; check needle is over the center of hole 2 (37.80×24.60 R7.8)
G1 X-51.560 Y79.645 F500 ; -> 2/2 hole 1 (⌀7.75) center
G4 P2.0 ; check needle is over the center of hole 1 (⌀7.75)
G1 X0.000 Y0.000 F500 ; -> center (zero)
G1 Z0.000 F200 ; lower back to set-zero point
M30 ; program end
