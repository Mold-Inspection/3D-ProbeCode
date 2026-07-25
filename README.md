<!-- README.md — v01 -->
# 3D ProbeCode

A desktop tool that reads a CAD model (STEP/STP), automatically detects holes that need to be measured, lets you plan a probe path for each hole, and exports a ready-to-run G-code probing program (GRBL dialect).

---

## What it does today

**1. Load a CAD model**
- Accepts `.step` / `.stp` files only.
- Converts the CAD B-Rep into a mesh for display, while keeping the raw B-Rep for precise hole math.

**2. View the part from 6 angles**
- Top, Bottom, Front, Back, Left, Right.
- 2D depth-map view with zoom, rotate, hover-to-read-depth, and click-to-pin depth measurements.

**3. Detect holes automatically**
- If the STEP file has real geometry (cylinders, cones, torus, sphere caps), holes are extracted analytically — accurate radius, depth, and axis, including multi-diameter holes (counterbores).
- If only a mesh is available (no STEP B-Rep), holes are found by clustering points on the surface.
- Detected holes are numbered, shown on the 2D view, and listed in the sidebar (selected vs. unselected, with reasons like "too shallow" or "occluded").

**4. Customize the probing plan per hole**
- Set number of layers (depths) and points per layer.
- Optional zigzag mode (rotates probe angle per layer to reduce repeated contact points).
- Multi-diameter holes get separate settings per segment.
- A 3D preview (Customization tab) shows the actual tool path and wall-contact points, and warns if your probe (stylus length / tip diameter) can't physically reach or fit the hole.

**5. Preview the travel path**
- Path Mapper tab shows the order holes will be visited and a close-up path preview per hole.

**6. Export G-code**
- Generates a GRBL-style probing program (`G38.2` probe moves) for every hole marked "selected for inspection."
- Uses real 3D coordinates (not screen-projected ones), so the output is machine-accurate regardless of which view you were looking at on screen.
- Orders holes with a simple nearest-neighbor path.
- Holes with no STEP geometry (mesh-only) are skipped and reported.

---

## Project structure

```
Build/
├── main.py                     # entry point
├── core/
│   ├── geometry_engine.py       # facade connecting all core modules
│   ├── cad_loader.py            # loads STEP/STP, builds mesh
│   ├── projector.py             # 3D → 2D view projection
│   ├── step_extractor.py        # extracts holes from STEP B-Rep
│   ├── path_planner.py          # builds probe path layers (screen-space, for preview)
│   ├── gcode_generator.py       # builds G-code (raw 3D space, for the real machine)
│   ├── gcode_export_panel.py    # UI panel for G-code export
│   ├── probe_profile.py         # probe stylus dimensions + fit/reach checks
│   └── models.py                # shared data structures (HoleFeature, StepHole, ...)
└── ui/
    ├── main_window.py           # main window, sidebars, hole list, state management
    └── tabs/
        ├── selection_tab.py     # 2D view + pin/measure/hole detection
        ├── customization_tab.py # 3D probe path preview per hole
        └── path_mapper_tab.py   # travel path / route preview
```

---

## Requirements

- Python 3.x
- `cadquery`, `trimesh`, `numpy`, `matplotlib`, `customtkinter`

## Running the app

```bash
python main.py
```

---

## Roadmap

### 🚧 Planned: CNC log import & evaluation
**Not yet implemented.** After a probing job runs on the real machine, the plan is to bring the resulting log back into the app and compare it against the planned path:

- Import the machine's probe log (actual measured depths/positions).
- Evaluate results against the plan — both:
  - **Graphically**: overlay actual vs. planned probe points on the existing 2D/3D views.
  - **Numerically**: show deviation values (depth error, position error) per hole/point.

This closes the loop: *Plan → Export G-code → Run on machine → Import log → Evaluate accuracy.*

---

## Notes on versioning

Files in this project follow a simple version-tag convention (`v01`, `v02`, ...) in a header comment, incremented whenever a file is meaningfully changed.
