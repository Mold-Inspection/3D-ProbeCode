# 3D ProbeCode

**3D ProbeCode** is a desktop application for planning CMM (Coordinate Measuring Machine) touch-probe inspection paths on machined or molded parts. It loads exact B-Rep hole geometry from STEP/STP CAD files, lets the user inspect the part from six standard views, detects hole features, and generates a layer-by-layer probe contact path for each hole — including a physical probe-stylus reach/fit check.

> Internal engineering context: this tool exists to remove guesswork from touch-probe programming for hole inspection — instead of eyeballing probe depths and radii, it derives them directly from the CAD's exact cylindrical/conical B-Rep faces.

---

## Features

- **STEP/STP-only ingestion** — the tool intentionally rejects mesh-only formats (STL, OBJ, etc.), since accurate probe planning requires exact B-Rep hole geometry, not a tessellated approximation.
- **Six standard views** (Top / Bottom / Front / Back / Left / Right) with 90° screen rotation, all backed by a shared projection engine so geometry, hole markers, and probe paths always stay aligned.
- **Automatic hole extraction from STEP B-Rep**
  - Detects cylindrical/conical faces, merges half-faces and counterbore steps into single logical holes.
  - Per-view visibility check via mesh raycasting/occlusion (a hole only gets a canvas marker if it's actually visible/reachable from that view).
  - Side-bore recovery via multi-sample raycasting for holes whose axis is perpendicular to the view direction.
- **Selected / Unselected hole tracking** — holes that fail depth/occlusion/breach checks are not discarded; they're surfaced as "Unselected Holes" with a human-readable reject reason, and can be manually promoted into the inspection list.
- **Probe Stylus Profile** — configurable stylus length and tip diameter, with live validation (`ProbeProfile`) of whether the probe can reach a hole's depth and fit its diameter. Warnings are shown per-hole rather than blocking selection.
- **Per-hole inspection configuration** — number of Z-layers, points per layer, and optional zigzag probing (progressive angular offset per layer).
- **3D path visualization (Customization tab)** — renders the actual planned tool path, wall contact points, bottom-depth target, and probe-profile warnings for the currently selected hole.
- **Depth-pin tool (Selection tab)** — click to pin measured depth at any point on the 2D view; hover shows live depth readout.
- **Path Mapper tab** *(in development)* — placeholder for planned G-code/import and reporting features (see Roadmap).

---

## Application Structure

```
Build/
├── main.py                       # Entry point
├── core/
│   ├── cad_loader.py              # STEP/STP loading & mesh tessellation (v01)
│   ├── geometry_engine.py         # MoldGeometry facade — coordinates all core modules
│   ├── projector.py                # 3D → 2D view projection + rotation matrices
│   ├── step_extractor.py          # B-Rep hole extraction, merging, per-view visibility (v13)
│   ├── path_planner.py            # Layer-by-layer probe path computation
│   ├── probe_profile.py           # Probe stylus reach/fit validation
│   └── models.py                  # HoleFeature / StepHole data classes (v01)
└── ui/
    ├── main_window.py              # Main window, sidebars, hole list, probe panel (v06)
    └── tabs/
        ├── selection_tab.py        # 2D view canvas: detection, pins, hover (v03)
        ├── customization_tab.py    # 3D probe path visualization (v01)
        └── path_mapper_tab.py      # Placeholder — future G-code/reporting tab
```

### Backend (`core/`)

| Module | Responsibility |
|---|---|
| `cad_loader.py` | Loads `.step`/`.stp` files only; raises `ValueError` for any other extension. Tessellates to a temporary STL for mesh display while retaining the STEP B-Rep for geometry extraction. Centers the mesh on its centroid. |
| `geometry_engine.py` (`MoldGeometry`) | Facade that owns the loader, projector, extractor, and planner, and exposes simple per-view getter methods to the UI. |
| `projector.py` (`Projector`) | Applies the fixed rotation table for each of the six named views, plus an additional on-screen Z-rotation, and projects 3D points/mesh triangles into 2D display coordinates with depth. Caches view parameters keyed on `(view_name, screen_rot)`. |
| `step_extractor.py` (`StepExtractor`) | Scans STEP B-Rep faces for cylindrical/conical hole candidates, deduplicates, merges half-faces and counterbore steps, then per-view determines which holes are visible (raycast occlusion), too shallow, or side-bores needing multi-sample recovery. Rejected candidates are tagged `is_rejected` with a `reject_reason` and a best-effort fallback position instead of being dropped. |
| `path_planner.py` (`PathPlanner`) | Given a hole and a layer count, computes evenly spaced depth layers along the hole axis, projects each into the active view, and (optionally) applies a cumulative zigzag angular offset per layer. |
| `probe_profile.py` (`ProbeProfile`) | Stores stylus length and tip diameter; `check_hole()` validates whether the probe can reach a given depth and fit a given radius, returning warning strings for the UI. |
| `models.py` | `HoleFeature` — UI-facing hole with inspection settings (layers, points/layer, zigzag, selection state, rejection metadata). `StepHole` — raw B-Rep hole (open/deep 3D points, radii, axis, depth). |

### Frontend (`ui/`)

| Module | Responsibility |
|---|---|
| `main_window.py` (`UIManager`) | Builds the main window: left sidebar (file upload, hole generation, view/rotation controls, probe profile panel) and right sidebar (Selected Holes / Unselected Holes lists). Owns application state (`current_holes`, `screen_rotation`, `selected_hole_idx`, etc.) and drives navigation between the Selection / Customization / Path Mapper tabs. |
| `tabs/selection_tab.py` (`SelectionTab`) | Renders the 2D depth-colored view, handles hole detection for non-STEP (mesh-only fallback) geometry, manages depth-pins, and hover-driven canvas feedback (hole highlight, "Unselected" marker). |
| `tabs/customization_tab.py` (`CustomizationTab`) | Renders a 3D cross-section of the selected hole showing the computed probe tool path, per-layer wall contact points (zigzag-colored if enabled), the bottom-depth target star, and probe-profile warnings. |
| `tabs/path_mapper_tab.py` (`PathMapperTab`) | Placeholder tab displaying a "Under Development" panel listing planned features. |

---

## Workflow

1. **Upload** a `.step`/`.stp` file.
2. **Select a view** (Top/Bottom/Front/Back/Left/Right) and optionally **rotate** the screen 90° at a time.
3. Click **Generate Holes** — extracts and classifies holes for the current view; locks view controls until cleared.
4. Review the **Selected Holes** / **Unselected Holes** sidebar sections:
   - Selected holes get a numbered marker on the canvas and full inspection settings.
   - Unselected holes show a reject reason and can be manually promoted via the "Select for Inspection" checkbox.
5. (Optional) Expand **Probe Stylus Profile** and set stylus length / tip diameter — per-hole reach/fit warnings update automatically.
6. For each selected hole, configure **Z-Layers**, **Points/Layer**, and optionally **Zigzag Inspection** with a rotation-per-layer angle.
7. Switch to the **Customization** tab to visualize the actual 3D probe path for the currently selected hole.
8. *(Planned)* Use **Path Mapper** to import machine logs, apply probe compensation, fit circles per layer, and generate a deviation report against the CAD reference.

---

## Requirements

- Python 3.x
- `customtkinter`
- `matplotlib`
- `numpy`
- `trimesh`
- `cadquery` (STEP B-Rep import/export)

---

## Running

```bash
python main.py
```

---
- `main_window.py` — v06
- `geometry_engine.py`, `projector.py`, `path_planner.py`, `probe_profile.py`, `path_mapper_tab.py` — unversioned (treat as v01 on next change)
