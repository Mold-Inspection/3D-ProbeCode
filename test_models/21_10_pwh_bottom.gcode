; ============================================
; 3D ProbeCode - GRBL Probe Program (View: Bottom)
; Holes: 2  Safe Z: 15.00 mm  Probe Feed: 100 mm/min
; WORK ZERO: X0 Y0 Z0 = the CENTER of the object (as seen on screen), Z0 on the top surface
; set Z0 with the ball BOTTOM touching the top surface
; BEFORE RUNNING: touch off that point and Set Zero X/Y/Z there.
; NOTE: assumes workpiece is raised by 13.50 mm padding (riser plate)
; NOTE: Coordinate system transformed for Bottom view machining
; NOTE: X/Y rotated 90 deg to match the on-screen orientation
; ============================================
G21 ; mm units
G90 ; absolute positioning
G94 ; feed rate mode: units/min
G0 Z15.000

; --- Hole 1 (1/2) ---
G0 Z15.000
G0 X70.160 Y-5.845
G0 X70.160 Y-5.845 Z1.000
G0 X70.160 Y-5.845 Z-5.845 ; layer 1 seg 1 — center
G38.2 X47.760 Y-5.845 Z-5.845 F100 ; point 1/4 — touch
G91
G0 X1.200 Y-0.000 Z-0.000 ; pull-off from wall
G90
G0 X70.160 Y-5.845 Z-5.845 ; return to center
G38.2 X70.160 Y9.955 Z-5.845 F100 ; point 2/4 — touch
G91
G0 X-0.000 Y-1.200 Z-0.000 ; pull-off from wall
G90
G0 X70.160 Y-5.845 Z-5.845 ; return to center
G38.2 X92.560 Y-5.845 Z-5.845 F100 ; point 3/4 — touch
G91
G0 X-1.200 Y-0.000 Z-0.000 ; pull-off from wall
G90
G0 X70.160 Y-5.845 Z-5.845 ; return to center
G38.2 X70.160 Y-21.645 Z-5.845 F100 ; point 4/4 — touch
G91
G0 X0.000 Y1.200 Z-0.000 ; pull-off from wall
G90
G0 X70.160 Y-5.845 Z-5.845 ; return to center
G0 X70.160 Y-5.845 Z-10.690 ; layer 2 seg 1 — center
G38.2 X47.760 Y-5.845 Z-10.690 F100 ; point 1/4 — touch
G91
G0 X1.200 Y-0.000 Z-0.000 ; pull-off from wall
G90
G0 X70.160 Y-5.845 Z-10.690 ; return to center
G38.2 X70.160 Y9.955 Z-10.690 F100 ; point 2/4 — touch
G91
G0 X-0.000 Y-1.200 Z-0.000 ; pull-off from wall
G90
G0 X70.160 Y-5.845 Z-10.690 ; return to center
G38.2 X92.560 Y-5.845 Z-10.690 F100 ; point 3/4 — touch
G91
G0 X-1.200 Y-0.000 Z-0.000 ; pull-off from wall
G90
G0 X70.160 Y-5.845 Z-10.690 ; return to center
G38.2 X70.160 Y-21.645 Z-10.690 F100 ; point 4/4 — touch
G91
G0 X0.000 Y1.200 Z-0.000 ; pull-off from wall
G90
G0 X70.160 Y-5.845 Z-10.690 ; return to center
G0 X70.160 Y-5.845 Z-15.535 ; layer 3 seg 1 — center
G38.2 X47.760 Y-5.845 Z-15.535 F100 ; point 1/4 — touch
G91
G0 X1.200 Y-0.000 Z-0.000 ; pull-off from wall
G90
G0 X70.160 Y-5.845 Z-15.535 ; return to center
G38.2 X70.160 Y9.955 Z-15.535 F100 ; point 2/4 — touch
G91
G0 X-0.000 Y-1.200 Z-0.000 ; pull-off from wall
G90
G0 X70.160 Y-5.845 Z-15.535 ; return to center
G38.2 X92.560 Y-5.845 Z-15.535 F100 ; point 3/4 — touch
G91
G0 X-1.200 Y-0.000 Z-0.000 ; pull-off from wall
G90
G0 X70.160 Y-5.845 Z-15.535 ; return to center
G38.2 X70.160 Y-21.645 Z-15.535 F100 ; point 4/4 — touch
G91
G0 X0.000 Y1.200 Z-0.000 ; pull-off from wall
G90
G0 X70.160 Y-5.845 Z-15.535 ; return to center

; --- Hole 2 (2/2) ---
G0 Z15.000
G0 X79.645 Y-51.560
G0 X79.645 Y-51.560 Z1.000
G0 X79.645 Y-51.560 Z-5.845 ; layer 1 seg 1 — center
G38.2 X79.645 Y-58.935 Z-5.845 F100 ; point 1/4 — touch
G91
G0 X-0.000 Y1.200 Z-0.000 ; pull-off from wall
G90
G0 X79.645 Y-51.560 Z-5.845 ; return to center
G38.2 X72.270 Y-51.560 Z-5.845 F100 ; point 2/4 — touch
G91
G0 X1.200 Y0.000 Z-0.000 ; pull-off from wall
G90
G0 X79.645 Y-51.560 Z-5.845 ; return to center
G38.2 X79.645 Y-44.185 Z-5.845 F100 ; point 3/4 — touch
G91
G0 X0.000 Y-1.200 Z0.000 ; pull-off from wall
G90
G0 X79.645 Y-51.560 Z-5.845 ; return to center
G38.2 X87.020 Y-51.560 Z-5.845 F100 ; point 4/4 — touch
G91
G0 X-1.200 Y-0.000 Z-0.000 ; pull-off from wall
G90
G0 X79.645 Y-51.560 Z-5.845 ; return to center
G0 X79.645 Y-51.560 Z-10.690 ; layer 2 seg 1 — center
G38.2 X79.645 Y-58.935 Z-10.690 F100 ; point 1/4 — touch
G91
G0 X-0.000 Y1.200 Z-0.000 ; pull-off from wall
G90
G0 X79.645 Y-51.560 Z-10.690 ; return to center
G38.2 X72.270 Y-51.560 Z-10.690 F100 ; point 2/4 — touch
G91
G0 X1.200 Y0.000 Z-0.000 ; pull-off from wall
G90
G0 X79.645 Y-51.560 Z-10.690 ; return to center
G38.2 X79.645 Y-44.185 Z-10.690 F100 ; point 3/4 — touch
G91
G0 X0.000 Y-1.200 Z0.000 ; pull-off from wall
G90
G0 X79.645 Y-51.560 Z-10.690 ; return to center
G38.2 X87.020 Y-51.560 Z-10.690 F100 ; point 4/4 — touch
G91
G0 X-1.200 Y-0.000 Z-0.000 ; pull-off from wall
G90
G0 X79.645 Y-51.560 Z-10.690 ; return to center
G0 X79.645 Y-51.560 Z-15.535 ; layer 3 seg 1 — center
G38.2 X79.645 Y-58.935 Z-15.535 F100 ; point 1/4 — touch
G91
G0 X-0.000 Y1.200 Z-0.000 ; pull-off from wall
G90
G0 X79.645 Y-51.560 Z-15.535 ; return to center
G38.2 X72.270 Y-51.560 Z-15.535 F100 ; point 2/4 — touch
G91
G0 X1.200 Y0.000 Z-0.000 ; pull-off from wall
G90
G0 X79.645 Y-51.560 Z-15.535 ; return to center
G38.2 X79.645 Y-44.185 Z-15.535 F100 ; point 3/4 — touch
G91
G0 X0.000 Y-1.200 Z0.000 ; pull-off from wall
G90
G0 X79.645 Y-51.560 Z-15.535 ; return to center
G38.2 X87.020 Y-51.560 Z-15.535 F100 ; point 4/4 — touch
G91
G0 X-1.200 Y-0.000 Z-0.000 ; pull-off from wall
G90
G0 X79.645 Y-51.560 Z-15.535 ; return to center

G0 Z15.000
M30 ; program end