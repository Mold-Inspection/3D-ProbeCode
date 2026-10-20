; ============================================
; 3D ProbeCode - GRBL Probe Program (View: Top)
; Holes: 2  Safe Z: 15.00 mm  Probe Feed: 100 mm/min
; WORK ZERO: X0 Y0 Z0 = the CENTER of the object (as seen on screen), Z0 on the top surface
; set Z0 with the ball BOTTOM touching the top surface
; BEFORE RUNNING: touch off that point and Set Zero X/Y/Z there.
; NOTE: assumes workpiece is raised by 13.50 mm padding (riser plate)
; ============================================
G21 ; mm units
G90 ; absolute positioning
G94 ; feed rate mode: units/min
G0 Z15.000

; --- Hole 2 (1/2) ---
G0 Z15.000
G0 X-5.845 Y70.160
G0 X-5.845 Y70.160 Z1.000
G0 X-5.845 Y70.160 Z-5.845 ; layer 1 seg 1 — center
G38.2 X-5.845 Y47.760 Z-5.845 F100 ; point 1/4 — touch
G91
G0 X-0.000 Y1.200 Z-0.000 ; pull-off from wall
G90
G0 X-5.845 Y70.160 Z-5.845 ; return to center
G38.2 X-21.645 Y70.160 Z-5.845 F100 ; point 2/4 — touch
G91
G0 X1.200 Y0.000 Z-0.000 ; pull-off from wall
G90
G0 X-5.845 Y70.160 Z-5.845 ; return to center
G38.2 X-5.845 Y92.560 Z-5.845 F100 ; point 3/4 — touch
G91
G0 X0.000 Y-1.200 Z0.000 ; pull-off from wall
G90
G0 X-5.845 Y70.160 Z-5.845 ; return to center
G38.2 X9.955 Y70.160 Z-5.845 F100 ; point 4/4 — touch
G91
G0 X-1.200 Y-0.000 Z-0.000 ; pull-off from wall
G90
G0 X-5.845 Y70.160 Z-5.845 ; return to center
G0 X-5.845 Y70.160 Z-10.690 ; layer 2 seg 1 — center
G38.2 X-5.845 Y47.760 Z-10.690 F100 ; point 1/4 — touch
G91
G0 X-0.000 Y1.200 Z-0.000 ; pull-off from wall
G90
G0 X-5.845 Y70.160 Z-10.690 ; return to center
G38.2 X-21.645 Y70.160 Z-10.690 F100 ; point 2/4 — touch
G91
G0 X1.200 Y0.000 Z-0.000 ; pull-off from wall
G90
G0 X-5.845 Y70.160 Z-10.690 ; return to center
G38.2 X-5.845 Y92.560 Z-10.690 F100 ; point 3/4 — touch
G91
G0 X0.000 Y-1.200 Z0.000 ; pull-off from wall
G90
G0 X-5.845 Y70.160 Z-10.690 ; return to center
G38.2 X9.955 Y70.160 Z-10.690 F100 ; point 4/4 — touch
G91
G0 X-1.200 Y-0.000 Z-0.000 ; pull-off from wall
G90
G0 X-5.845 Y70.160 Z-10.690 ; return to center
G0 X-5.845 Y70.160 Z-15.535 ; layer 3 seg 1 — center
G38.2 X-5.845 Y47.760 Z-15.535 F100 ; point 1/4 — touch
G91
G0 X-0.000 Y1.200 Z-0.000 ; pull-off from wall
G90
G0 X-5.845 Y70.160 Z-15.535 ; return to center
G38.2 X-21.645 Y70.160 Z-15.535 F100 ; point 2/4 — touch
G91
G0 X1.200 Y0.000 Z-0.000 ; pull-off from wall
G90
G0 X-5.845 Y70.160 Z-15.535 ; return to center
G38.2 X-5.845 Y92.560 Z-15.535 F100 ; point 3/4 — touch
G91
G0 X0.000 Y-1.200 Z0.000 ; pull-off from wall
G90
G0 X-5.845 Y70.160 Z-15.535 ; return to center
G38.2 X9.955 Y70.160 Z-15.535 F100 ; point 4/4 — touch
G91
G0 X-1.200 Y-0.000 Z-0.000 ; pull-off from wall
G90
G0 X-5.845 Y70.160 Z-15.535 ; return to center

; --- Hole 1 (2/2) ---
G0 Z15.000
G0 X-51.560 Y79.645
G0 X-51.560 Y79.645 Z1.000
G0 X-51.560 Y79.645 Z-5.845 ; layer 1 seg 1 — center
G38.2 X-51.560 Y72.270 Z-5.845 F100 ; point 1/4 — touch
G91
G0 X-0.000 Y1.200 Z-0.000 ; pull-off from wall
G90
G0 X-51.560 Y79.645 Z-5.845 ; return to center
G38.2 X-58.935 Y79.645 Z-5.845 F100 ; point 2/4 — touch
G91
G0 X1.200 Y0.000 Z-0.000 ; pull-off from wall
G90
G0 X-51.560 Y79.645 Z-5.845 ; return to center
G38.2 X-51.560 Y87.020 Z-5.845 F100 ; point 3/4 — touch
G91
G0 X0.000 Y-1.200 Z0.000 ; pull-off from wall
G90
G0 X-51.560 Y79.645 Z-5.845 ; return to center
G38.2 X-44.185 Y79.645 Z-5.845 F100 ; point 4/4 — touch
G91
G0 X-1.200 Y-0.000 Z-0.000 ; pull-off from wall
G90
G0 X-51.560 Y79.645 Z-5.845 ; return to center
G0 X-51.560 Y79.645 Z-10.690 ; layer 2 seg 1 — center
G38.2 X-51.560 Y72.270 Z-10.690 F100 ; point 1/4 — touch
G91
G0 X-0.000 Y1.200 Z-0.000 ; pull-off from wall
G90
G0 X-51.560 Y79.645 Z-10.690 ; return to center
G38.2 X-58.935 Y79.645 Z-10.690 F100 ; point 2/4 — touch
G91
G0 X1.200 Y0.000 Z-0.000 ; pull-off from wall
G90
G0 X-51.560 Y79.645 Z-10.690 ; return to center
G38.2 X-51.560 Y87.020 Z-10.690 F100 ; point 3/4 — touch
G91
G0 X0.000 Y-1.200 Z0.000 ; pull-off from wall
G90
G0 X-51.560 Y79.645 Z-10.690 ; return to center
G38.2 X-44.185 Y79.645 Z-10.690 F100 ; point 4/4 — touch
G91
G0 X-1.200 Y-0.000 Z-0.000 ; pull-off from wall
G90
G0 X-51.560 Y79.645 Z-10.690 ; return to center
G0 X-51.560 Y79.645 Z-15.535 ; layer 3 seg 1 — center
G38.2 X-51.560 Y72.270 Z-15.535 F100 ; point 1/4 — touch
G91
G0 X-0.000 Y1.200 Z-0.000 ; pull-off from wall
G90
G0 X-51.560 Y79.645 Z-15.535 ; return to center
G38.2 X-58.935 Y79.645 Z-15.535 F100 ; point 2/4 — touch
G91
G0 X1.200 Y0.000 Z-0.000 ; pull-off from wall
G90
G0 X-51.560 Y79.645 Z-15.535 ; return to center
G38.2 X-51.560 Y87.020 Z-15.535 F100 ; point 3/4 — touch
G91
G0 X0.000 Y-1.200 Z0.000 ; pull-off from wall
G90
G0 X-51.560 Y79.645 Z-15.535 ; return to center
G38.2 X-44.185 Y79.645 Z-15.535 F100 ; point 4/4 — touch
G91
G0 X-1.200 Y-0.000 Z-0.000 ; pull-off from wall
G90
G0 X-51.560 Y79.645 Z-15.535 ; return to center

G0 Z15.000
M30 ; program end