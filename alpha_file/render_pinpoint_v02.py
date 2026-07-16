# render_pinpoint.py
# VERSION: 02
# CHANGE LOG (v01 -> v02):
#   Replaced the hardcoded STEP file path with a native file-picker dialog
#   (tkinter.filedialog.askopenfilename) so the user selects the file
#   directly through File Explorer instead of typing/guessing a path —
#   this was the root cause of repeated "STEP File could not be loaded"
#   errors, which were actually just os.path.exists() returning False on
#   a wrong relative/hardcoded path, not a CadQuery/OCP problem.
# Reads a STEP file with CadQuery, finds every face whose geomType is
# CYLINDER, pulls the two circular edges bounding that face, and renders
# a 3D matplotlib plot of the part with:
#   - the cylinder face's axis drawn as a teal line (between the two
#     edge centers)
#   - the two circular edges themselves drawn as coral rings, in the
#     plane perpendicular to the axis, at their real radius
# The underlying mesh is exported from the STEP data (trimesh) and drawn
# as a light gray wireframe for spatial context only — it is not used
# for any of the cylinder/edge math, which comes entirely from the
# analytic STEP B-Rep data.
#
# NOTE: this groups candidate cylinder faces by rounded (X, Z) axis
# position only, to pick ONE representative face per axis location for
# a clean plot. It does NOT run full counterbore/half-face merging
# (see step_extractor.py's _merge_half_faces / _merge_counterbores) —
# so a stepped counterbore hole (two faces, two radii, same axis) will
# still show as two separate rings on one shared axis line, not as one
# merged hole. That's intentional here: this script is for visualizing
# where the raw CYLINDER faces are, not for producing a final hole count.

import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox
import cadquery as cq
import trimesh
import numpy as np
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Line3DCollection

# --- File picker (v02): opens native Windows/Explorer dialog ---
root = tk.Tk()
root.withdraw()  # hide the empty tkinter root window, only show the dialog
fp = filedialog.askopenfilename(
    title="Select STEP file",
    filetypes=[("STEP files", "*.step *.stp *.STEP *.STP"), ("All files", "*.*")]
)
root.destroy()

if not fp:
    print("No file selected — exiting.")
    sys.exit(0)

print("Selected file:", fp)
print("exists:", os.path.exists(fp))

try:
    step_data = cq.importers.importStep(fp)
except Exception as e:
    messagebox.showerror("STEP Load Error", f"Could not load file:\n{fp}\n\n{e!r}")
    raise

tmp = "temp_view.stl"
cq.exporters.export(step_data, tmp, exportType='STL', tolerance=0.1, angularTolerance=0.2)
mesh = trimesh.load(tmp)

faces = step_data.faces().vals()

# Collect one representative face+edge pair per distinct hole axis (group by rounded x,z)
holes = {}
for face in faces:
    if face.geomType() != "CYLINDER":
        continue
    circle_edges = [e for e in face.Edges() if e.geomType() == "CIRCLE"]
    if len(circle_edges) < 2:
        continue
    c0 = circle_edges[0].Center()
    c1 = circle_edges[1].Center()
    key = (round(c0.x, 0), round(c0.z, 0))
    holes.setdefault(key, []).append((face, circle_edges[0], circle_edges[1]))

print(f"Distinct hole axis locations (grouped by X,Z): {len(holes)}")

fig = plt.figure(figsize=(12, 9))
ax = fig.add_subplot(111, projection='3d')

# Draw mesh wireframe (light gray, thin) for context
tris = mesh.triangles
step = max(1, len(tris)//15000)
sampled = tris[::step]
lines = []
for tri in sampled:
    lines += [(tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])]
lc = Line3DCollection(lines, colors='#888888', linewidths=0.15, alpha=0.35)
ax.add_collection3d(lc)

plotted = 0
for key, entries in holes.items():
    face, e0, e1 = entries[0]
    c0, c1 = e0.Center(), e1.Center()
    r0, r1 = e0.radius(), e1.radius()

    # Cylinder wall (teal) as a straight line between the two edge centers
    ax.plot([c0.x, c1.x], [c0.y, c1.y], [c0.z, c1.z], color='#1D9E75', linewidth=2.2, zorder=5)

    # Edge circles (coral) drawn as small rings around each center, in the plane perpendicular to axis
    axis_vec = np.array([c1.x - c0.x, c1.y - c0.y, c1.z - c0.z])
    norm = np.linalg.norm(axis_vec)
    if norm < 1e-6:
        continue
    axis_vec /= norm
    arbitrary = np.array([1, 0, 0]) if abs(axis_vec[0]) < 0.9 else np.array([0, 1, 0])
    u = np.cross(axis_vec, arbitrary); u /= np.linalg.norm(u)
    v = np.cross(axis_vec, u)
    theta = np.linspace(0, 2 * np.pi, 24)
    for c, r in [(c0, r0), (c1, r1)]:
        ring = np.array([c.x, c.y, c.z]) + r * (np.outer(np.cos(theta), u) + np.outer(np.sin(theta), v))
        ax.plot(ring[:, 0], ring[:, 1], ring[:, 2], color='#D85A30', linewidth=1.6, zorder=6)

    plotted += 1

print(f"Highlighted {plotted} hole faces/edges")

ax.set_box_aspect([1, 1, 1])
ax.set_xlabel('X (mm)'); ax.set_ylabel('Y (mm)'); ax.set_zlabel('Z (mm)')
ax.set_title(f"bottom_clamping_plate_pcs2b — {plotted} cylindrical faces (teal) + circular edges (coral)", fontsize=11)
ax.view_init(elev=22, azim=-60)

bounds = mesh.bounds
center = bounds.mean(axis=0)
extent = (bounds[1] - bounds[0]).max() / 2 * 1.1
ax.set_xlim(center[0] - extent, center[0] + extent)
ax.set_ylim(center[1] - extent, center[1] + extent)
ax.set_zlim(center[2] - extent, center[2] + extent)

plt.tight_layout()
out_path = os.path.join(os.path.dirname(fp), "pinpoint_cylinder_faces.png")
plt.savefig(out_path, dpi=160)
print(f"saved: {out_path}")
plt.show()
