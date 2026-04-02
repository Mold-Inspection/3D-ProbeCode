# 3D Mold Depth Viewer

A lightweight, interactive Python tool for inspecting and visualizing the depths of 3D CNC molds and flat-plate STL files. 

Built with `matplotlib` and `trimesh`, this viewer automatically aligns CAD exports, renders a 2D depth map of the surface, and allows users to explore specific coordinate depths using an interactive hover tooltip and custom marker placement.

## ✨ Features

* **Automatic CAD Alignment:** Automatically detects the thinnest axis of the imported STL and forces it to be the Z-axis (Depth), solving the common "Y-Up" vs "Z-Up" export issues from software like SolidWorks or Blender.
* **Interactive Depth Tooltip:** Hover anywhere over the mold to instantly see the precise Z-depth in millimeters.
* **Custom Coordinate Marking:** Right-click anywhere on the plot to drop a numbered marker (e.g., `P1`, `P2`) and log the exact X/Y coordinates to the console.
* **Standard Orthographic Views:** Quickly switch between Top, Bottom, Front, Back, Left, and Right profiles.
* **Screen Rotation:** Rotate the current view by 90-degree increments for easier viewing of long or wide parts.
* **Dark Mode UI:** A custom, eye-friendly dark interface built on top of Matplotlib.

## 🛠️ Requirements

This project requires Python 3.x and the following libraries:

* `matplotlib` (For plotting and UI)
* `numpy` (For fast coordinate math)
* `trimesh` (For parsing and transforming STL geometry)
* `tkinter` (For the native file upload dialog)
