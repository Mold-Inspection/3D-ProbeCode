; ============================================
; 3D ProbeCode - HOLE CENTER TEST
; Object: plate_with_holes.step  View: Top
; Size: X 226.500 mm  x  Y 300.000 mm   Holes: 6
; BEFORE RUNNING: put the needle at the UPPER-LEFT corner of the
;   object (as seen on screen) and Set Zero X/Y/Z there.
; Visits the center of every hole selected for inspection, then
;   returns to the zero point. Needle stays lifted the whole time.
;   X+ = right, Y+ = toward back of machine (up on screen).
; No G92 / work-offset change: uses the zero you set.
; ============================================
G21 ; mm units
G90 ; absolute positioning
G94 ; feed rate mode: units/min
G0 Z5.000 ; lift needle
G1 X61.500 Y-73.000 F500 ; -> 1/6 hole 1 (⌀8.00) center
G4 P2.0 ; check needle is over the center of hole 1 (⌀8.00)
G1 X107.500 Y-82.000 F500 ; -> 2/6 hole 2 (36.00×25.00 R4.0) center
G4 P2.0 ; check needle is over the center of hole 2 (36.00×25.00 R4.0)
G1 X150.500 Y-234.000 F500 ; -> 3/6 hole 3 (slot 11.00×5.00) center
G4 P2.0 ; check needle is over the center of hole 3 (slot 11.00×5.00)
G1 X192.500 Y-234.000 F500 ; -> 4/6 hole 4 (slot 11.00×5.00) center
G4 P2.0 ; check needle is over the center of hole 4 (slot 11.00×5.00)
G1 X192.500 Y-291.000 F500 ; -> 5/6 hole 6 (slot 11.00×5.00) center
G4 P2.0 ; check needle is over the center of hole 6 (slot 11.00×5.00)
G1 X150.500 Y-291.000 F500 ; -> 6/6 hole 5 (slot 11.00×5.00) center
G4 P2.0 ; check needle is over the center of hole 5 (slot 11.00×5.00)
G1 X0.000 Y0.000 F500 ; -> upper-left (zero)
G1 Z0.000 F200 ; lower back to set-zero point
M30 ; program end
