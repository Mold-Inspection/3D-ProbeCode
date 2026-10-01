; ============================================
; 3D ProbeCode - AXIS TEST (corner trace)
; Object: plate_with_holes.step  View: Top
; Size: X 226.500 mm  x  Y 300.000 mm
; BEFORE RUNNING: put the needle at the UPPER-LEFT corner of the
;   object (as seen on screen) and Set Zero X/Y/Z there.
; Path: upper-left -> upper-right -> lower-right -> lower-left -> upper-left
;   X+ = right, Y+ = toward back of machine (up on screen).
; No G92 / work-offset change: uses the zero you set.
; ============================================
G21 ; mm units
G90 ; absolute positioning
G94 ; feed rate mode: units/min
G0 Z5.000 ; lift needle
G1 X226.500 Y0.000 F500 ; -> upper-right
G4 P2.0 ; check needle is on the upper-right corner
G1 X226.500 Y-300.000 F500 ; -> lower-right
G4 P2.0 ; check needle is on the lower-right corner
G1 X0.000 Y-300.000 F500 ; -> lower-left
G4 P2.0 ; check needle is on the lower-left corner
G1 X0.000 Y0.000 F500 ; -> upper-left (zero)
G1 Z0.000 F200 ; lower back to set-zero point
M30 ; program end
