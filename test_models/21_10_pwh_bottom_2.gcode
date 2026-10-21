; ============================================
; 3D ProbeCode - GRBL Probe Program (View: Bottom)
; Holes: 2  Safe Z: 15.00 mm  Probe Feed: 100 mm/min
; DOUBLE TOUCH: back off 0.50 mm, re-touch at F20 — the slow touch is the measured value
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
G0 X71.020 Y-5.135
G0 X71.020 Y-5.135 Z1.000
G0 X71.020 Y-5.135 Z-5.845 ; layer 1 seg 1 — center
G38.2 X48.620 Y-5.135 Z-5.845 F100 ; point 1/4 — touch
G91
G0 X0.500 Y-0.000 Z-0.000 ; back off for the slow re-touch
G4 P0.01 ; re-touch marker — the log parser keeps the next touch only
G38.2 X-4.000 Y0.000 Z0.000 F20 ; point 1/4 — slow re-touch
G0 X1.200 Y-0.000 Z-0.000 ; pull-off from wall
G90
G0 X71.020 Y-5.135 Z-5.845 ; return to center
G38.2 X71.020 Y10.665 Z-5.845 F100 ; point 2/4 — touch
G91
G0 X-0.000 Y-0.500 Z-0.000 ; back off for the slow re-touch
G4 P0.01 ; re-touch marker — the log parser keeps the next touch only
G38.2 X0.000 Y4.000 Z0.000 F20 ; point 2/4 — slow re-touch
G0 X-0.000 Y-1.200 Z-0.000 ; pull-off from wall
G90
G0 X71.020 Y-5.135 Z-5.845 ; return to center
G38.2 X93.420 Y-5.135 Z-5.845 F100 ; point 3/4 — touch
G91
G0 X-0.500 Y-0.000 Z-0.000 ; back off for the slow re-touch
G4 P0.01 ; re-touch marker — the log parser keeps the next touch only
G38.2 X4.000 Y0.000 Z0.000 F20 ; point 3/4 — slow re-touch
G0 X-1.200 Y-0.000 Z-0.000 ; pull-off from wall
G90
G0 X71.020 Y-5.135 Z-5.845 ; return to center
G38.2 X71.020 Y-20.935 Z-5.845 F100 ; point 4/4 — touch
G91
G0 X0.000 Y0.500 Z-0.000 ; back off for the slow re-touch
G4 P0.01 ; re-touch marker — the log parser keeps the next touch only
G38.2 X-0.000 Y-4.000 Z0.000 F20 ; point 4/4 — slow re-touch
G0 X0.000 Y1.200 Z-0.000 ; pull-off from wall
G90
G0 X71.020 Y-5.135 Z-5.845 ; return to center
G0 X71.020 Y-5.135 Z-10.690 ; layer 2 seg 1 — center
G38.2 X48.620 Y-5.135 Z-10.690 F100 ; point 1/4 — touch
G91
G0 X0.500 Y-0.000 Z-0.000 ; back off for the slow re-touch
G4 P0.01 ; re-touch marker — the log parser keeps the next touch only
G38.2 X-4.000 Y0.000 Z0.000 F20 ; point 1/4 — slow re-touch
G0 X1.200 Y-0.000 Z-0.000 ; pull-off from wall
G90
G0 X71.020 Y-5.135 Z-10.690 ; return to center
G38.2 X71.020 Y10.665 Z-10.690 F100 ; point 2/4 — touch
G91
G0 X-0.000 Y-0.500 Z-0.000 ; back off for the slow re-touch
G4 P0.01 ; re-touch marker — the log parser keeps the next touch only
G38.2 X0.000 Y4.000 Z0.000 F20 ; point 2/4 — slow re-touch
G0 X-0.000 Y-1.200 Z-0.000 ; pull-off from wall
G90
G0 X71.020 Y-5.135 Z-10.690 ; return to center
G38.2 X93.420 Y-5.135 Z-10.690 F100 ; point 3/4 — touch
G91
G0 X-0.500 Y-0.000 Z-0.000 ; back off for the slow re-touch
G4 P0.01 ; re-touch marker — the log parser keeps the next touch only
G38.2 X4.000 Y0.000 Z0.000 F20 ; point 3/4 — slow re-touch
G0 X-1.200 Y-0.000 Z-0.000 ; pull-off from wall
G90
G0 X71.020 Y-5.135 Z-10.690 ; return to center
G38.2 X71.020 Y-20.935 Z-10.690 F100 ; point 4/4 — touch
G91
G0 X0.000 Y0.500 Z-0.000 ; back off for the slow re-touch
G4 P0.01 ; re-touch marker — the log parser keeps the next touch only
G38.2 X-0.000 Y-4.000 Z0.000 F20 ; point 4/4 — slow re-touch
G0 X0.000 Y1.200 Z-0.000 ; pull-off from wall
G90
G0 X71.020 Y-5.135 Z-10.690 ; return to center
G0 X71.020 Y-5.135 Z-15.535 ; layer 3 seg 1 — center
G38.2 X48.620 Y-5.135 Z-15.535 F100 ; point 1/4 — touch
G91
G0 X0.500 Y-0.000 Z-0.000 ; back off for the slow re-touch
G4 P0.01 ; re-touch marker — the log parser keeps the next touch only
G38.2 X-4.000 Y0.000 Z0.000 F20 ; point 1/4 — slow re-touch
G0 X1.200 Y-0.000 Z-0.000 ; pull-off from wall
G90
G0 X71.020 Y-5.135 Z-15.535 ; return to center
G38.2 X71.020 Y10.665 Z-15.535 F100 ; point 2/4 — touch
G91
G0 X-0.000 Y-0.500 Z-0.000 ; back off for the slow re-touch
G4 P0.01 ; re-touch marker — the log parser keeps the next touch only
G38.2 X0.000 Y4.000 Z0.000 F20 ; point 2/4 — slow re-touch
G0 X-0.000 Y-1.200 Z-0.000 ; pull-off from wall
G90
G0 X71.020 Y-5.135 Z-15.535 ; return to center
G38.2 X93.420 Y-5.135 Z-15.535 F100 ; point 3/4 — touch
G91
G0 X-0.500 Y-0.000 Z-0.000 ; back off for the slow re-touch
G4 P0.01 ; re-touch marker — the log parser keeps the next touch only
G38.2 X4.000 Y0.000 Z0.000 F20 ; point 3/4 — slow re-touch
G0 X-1.200 Y-0.000 Z-0.000 ; pull-off from wall
G90
G0 X71.020 Y-5.135 Z-15.535 ; return to center
G38.2 X71.020 Y-20.935 Z-15.535 F100 ; point 4/4 — touch
G91
G0 X0.000 Y0.500 Z-0.000 ; back off for the slow re-touch
G4 P0.01 ; re-touch marker — the log parser keeps the next touch only
G38.2 X-0.000 Y-4.000 Z0.000 F20 ; point 4/4 — slow re-touch
G0 X0.000 Y1.200 Z-0.000 ; pull-off from wall
G90
G0 X71.020 Y-5.135 Z-15.535 ; return to center

; --- Hole 2 (2/2) ---
G0 Z15.000
G0 X82.165 Y-51.400
G0 X82.165 Y-51.400 Z1.000
G0 X82.165 Y-51.400 Z-5.845 ; layer 1 seg 1 — center
G38.2 X82.165 Y-58.775 Z-5.845 F100 ; point 1/4 — touch
G91
G0 X-0.000 Y0.500 Z-0.000 ; back off for the slow re-touch
G4 P0.01 ; re-touch marker — the log parser keeps the next touch only
G38.2 X0.000 Y-4.000 Z0.000 F20 ; point 1/4 — slow re-touch
G0 X-0.000 Y1.200 Z-0.000 ; pull-off from wall
G90
G0 X82.165 Y-51.400 Z-5.845 ; return to center
G38.2 X74.790 Y-51.400 Z-5.845 F100 ; point 2/4 — touch
G91
G0 X0.500 Y0.000 Z-0.000 ; back off for the slow re-touch
G4 P0.01 ; re-touch marker — the log parser keeps the next touch only
G38.2 X-4.000 Y-0.000 Z0.000 F20 ; point 2/4 — slow re-touch
G0 X1.200 Y0.000 Z-0.000 ; pull-off from wall
G90
G0 X82.165 Y-51.400 Z-5.845 ; return to center
G38.2 X82.165 Y-44.025 Z-5.845 F100 ; point 3/4 — touch
G91
G0 X0.000 Y-0.500 Z0.000 ; back off for the slow re-touch
G4 P0.01 ; re-touch marker — the log parser keeps the next touch only
G38.2 X-0.000 Y4.000 Z-0.000 F20 ; point 3/4 — slow re-touch
G0 X0.000 Y-1.200 Z0.000 ; pull-off from wall
G90
G0 X82.165 Y-51.400 Z-5.845 ; return to center
G38.2 X89.540 Y-51.400 Z-5.845 F100 ; point 4/4 — touch
G91
G0 X-0.500 Y-0.000 Z-0.000 ; back off for the slow re-touch
G4 P0.01 ; re-touch marker — the log parser keeps the next touch only
G38.2 X4.000 Y0.000 Z0.000 F20 ; point 4/4 — slow re-touch
G0 X-1.200 Y-0.000 Z-0.000 ; pull-off from wall
G90
G0 X82.165 Y-51.400 Z-5.845 ; return to center
G0 X82.165 Y-51.400 Z-10.690 ; layer 2 seg 1 — center
G38.2 X82.165 Y-58.775 Z-10.690 F100 ; point 1/4 — touch
G91
G0 X-0.000 Y0.500 Z-0.000 ; back off for the slow re-touch
G4 P0.01 ; re-touch marker — the log parser keeps the next touch only
G38.2 X0.000 Y-4.000 Z0.000 F20 ; point 1/4 — slow re-touch
G0 X-0.000 Y1.200 Z-0.000 ; pull-off from wall
G90
G0 X82.165 Y-51.400 Z-10.690 ; return to center
G38.2 X74.790 Y-51.400 Z-10.690 F100 ; point 2/4 — touch
G91
G0 X0.500 Y0.000 Z-0.000 ; back off for the slow re-touch
G4 P0.01 ; re-touch marker — the log parser keeps the next touch only
G38.2 X-4.000 Y-0.000 Z0.000 F20 ; point 2/4 — slow re-touch
G0 X1.200 Y0.000 Z-0.000 ; pull-off from wall
G90
G0 X82.165 Y-51.400 Z-10.690 ; return to center
G38.2 X82.165 Y-44.025 Z-10.690 F100 ; point 3/4 — touch
G91
G0 X0.000 Y-0.500 Z0.000 ; back off for the slow re-touch
G4 P0.01 ; re-touch marker — the log parser keeps the next touch only
G38.2 X-0.000 Y4.000 Z-0.000 F20 ; point 3/4 — slow re-touch
G0 X0.000 Y-1.200 Z0.000 ; pull-off from wall
G90
G0 X82.165 Y-51.400 Z-10.690 ; return to center
G38.2 X89.540 Y-51.400 Z-10.690 F100 ; point 4/4 — touch
G91
G0 X-0.500 Y-0.000 Z-0.000 ; back off for the slow re-touch
G4 P0.01 ; re-touch marker — the log parser keeps the next touch only
G38.2 X4.000 Y0.000 Z0.000 F20 ; point 4/4 — slow re-touch
G0 X-1.200 Y-0.000 Z-0.000 ; pull-off from wall
G90
G0 X82.165 Y-51.400 Z-10.690 ; return to center
G0 X82.165 Y-51.400 Z-15.535 ; layer 3 seg 1 — center
G38.2 X82.165 Y-58.775 Z-15.535 F100 ; point 1/4 — touch
G91
G0 X-0.000 Y0.500 Z-0.000 ; back off for the slow re-touch
G4 P0.01 ; re-touch marker — the log parser keeps the next touch only
G38.2 X0.000 Y-4.000 Z0.000 F20 ; point 1/4 — slow re-touch
G0 X-0.000 Y1.200 Z-0.000 ; pull-off from wall
G90
G0 X82.165 Y-51.400 Z-15.535 ; return to center
G38.2 X74.790 Y-51.400 Z-15.535 F100 ; point 2/4 — touch
G91
G0 X0.500 Y0.000 Z-0.000 ; back off for the slow re-touch
G4 P0.01 ; re-touch marker — the log parser keeps the next touch only
G38.2 X-4.000 Y-0.000 Z0.000 F20 ; point 2/4 — slow re-touch
G0 X1.200 Y0.000 Z-0.000 ; pull-off from wall
G90
G0 X82.165 Y-51.400 Z-15.535 ; return to center
G38.2 X82.165 Y-44.025 Z-15.535 F100 ; point 3/4 — touch
G91
G0 X0.000 Y-0.500 Z0.000 ; back off for the slow re-touch
G4 P0.01 ; re-touch marker — the log parser keeps the next touch only
G38.2 X-0.000 Y4.000 Z-0.000 F20 ; point 3/4 — slow re-touch
G0 X0.000 Y-1.200 Z0.000 ; pull-off from wall
G90
G0 X82.165 Y-51.400 Z-15.535 ; return to center
G38.2 X89.540 Y-51.400 Z-15.535 F100 ; point 4/4 — touch
G91
G0 X-0.500 Y-0.000 Z-0.000 ; back off for the slow re-touch
G4 P0.01 ; re-touch marker — the log parser keeps the next touch only
G38.2 X4.000 Y0.000 Z0.000 F20 ; point 4/4 — slow re-touch
G0 X-1.200 Y-0.000 Z-0.000 ; pull-off from wall
G90
G0 X82.165 Y-51.400 Z-15.535 ; return to center

G0 Z15.000 ; v14: lift to safe Z first
G0 X0 Y0 ; v14: back to work zero X0 Y0 (stays at safe Z)
M30 ; program end