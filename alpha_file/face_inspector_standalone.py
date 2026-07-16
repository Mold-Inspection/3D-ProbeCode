# tools/face_inspector_standalone.py
# VERSION: 01
# CHANGE LOG (v01):
#   Standalone, single-file version of the STEP Face Inspector — combines
#   what used to be split across face_inspector.py (parsing logic) and
#   face_inspector_gui.py (GUI) into one file with NO imports from any
#   other project module. Drop this file anywhere and run it on its own;
#   its only dependencies are the third-party packages cadquery and
#   customtkinter (both already used elsewhere in this project).
#
#   Provides a single "Open STEP / STP File" button that launches the OS
#   file-explorer dialog (pre-filtered to .stp/.step), then renders the
#   face-type breakdown and per-face detail (index, type, center X/Y/Z,
#   radius where applicable) in a scrollable text panel.
#
#   Run standalone:
#       python face_inspector_standalone.py
import os
import customtkinter as ctk
import tkinter.messagebox as _mb
import cadquery as cq

SUPPORTED_EXTENSIONS = ('.stp', '.step')

# Face types that expose a meaningful single radius via face.radius()
_RADIUS_TYPES = ('CYLINDER', 'CONE', 'SPHERE', 'TORUS')


# ----------------------------------------------------------------------
# Parsing logic (formerly tools/face_inspector.py)
# ----------------------------------------------------------------------
def inspect_faces(filepath: str) -> dict:
    """
    Load a STEP/STP file and classify every face by geometric surface type.

    Returns
    -------
    {
        'filepath':    str,
        'total_faces': int,
        'counts':      {geom_type: int, ...},
        'faces': [
            {'index': int, 'type': str, 'center': (x, y, z) | (None, None, None),
             'radius': float | None},
            ...
        ]
    }
    """
    ext = os.path.splitext(filepath)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{ext or '(no extension)'}'. "
            f"This tool only accepts .STEP / .STP files."
        )

    step_data = cq.importers.importStep(filepath)

    counts = {}
    faces_info = []

    for i, face in enumerate(step_data.faces().vals()):
        geom_type = face.geomType()
        counts[geom_type] = counts.get(geom_type, 0) + 1

        try:
            c = face.Center()
            center_xyz = (round(c.x, 3), round(c.y, 3), round(c.z, 3))
        except Exception:
            center_xyz = (None, None, None)

        radius = None
        if geom_type in _RADIUS_TYPES:
            try:
                radius = round(float(face.radius()), 3)
            except Exception:
                radius = None

        faces_info.append({
            'index':  i,
            'type':   geom_type,
            'center': center_xyz,
            'radius': radius,
        })

    return {
        'filepath':    filepath,
        'total_faces': len(faces_info),
        'counts':      counts,
        'faces':       faces_info,
    }


# ----------------------------------------------------------------------
# GUI (formerly tools/face_inspector_gui.py)
# ----------------------------------------------------------------------
class FaceInspectorGUI:
    def __init__(self):
        ctk.set_appearance_mode("dark")

        self.root = ctk.CTk()
        self.root.title("STEP Face Inspector")
        self.root.geometry("720x560")

        # --- Top bar: open-file button + summary label ---
        top_bar = ctk.CTkFrame(self.root, fg_color="transparent")
        top_bar.pack(fill="x", padx=16, pady=(16, 8))

        self.btn_open = ctk.CTkButton(
            top_bar, text="📂  Open STEP / STP File",
            fg_color="#2e7d32", hover_color="#4caf50",
            height=36, font=ctk.CTkFont(size=14, weight="bold"),
            command=self.open_file_dialog)
        self.btn_open.pack(side="left")

        self.lbl_summary = ctk.CTkLabel(
            top_bar, text="No file loaded",
            font=ctk.CTkFont(size=13), text_color="gray")
        self.lbl_summary.pack(side="left", padx=(16, 0))

        # --- Result panel (scrollable text) ---
        self.txt_result = ctk.CTkTextbox(
            self.root, font=ctk.CTkFont(family="Consolas", size=12),
            wrap="none")
        self.txt_result.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self.txt_result.insert("1.0", "Click \"Open STEP / STP File\" to begin.")
        self.txt_result.configure(state="disabled")

    # ------------------------------------------------------------------
    def open_file_dialog(self):
        filepath = ctk.filedialog.askopenfilename(
            title="Select STEP/STP CAD Model",
            filetypes=[("STEP Files", "*.stp *.step")]
        )
        if not filepath:
            return

        try:
            result = inspect_faces(filepath)
        except ValueError as e:
            _mb.showerror("Unsupported File", str(e))
            return
        except Exception as e:
            _mb.showerror("Failed to Read File", f"Could not process this file:\n{e}")
            return

        self._render_result(filepath, result)

    def _render_result(self, filepath: str, result: dict):
        self.lbl_summary.configure(
            text=f"{filepath}  —  {result['total_faces']} faces",
            text_color="white")

        lines = []
        lines.append(f"File: {filepath}")
        lines.append(f"Total faces: {result['total_faces']}")
        lines.append("")
        lines.append("Face type breakdown:")
        for geom_type, count in sorted(result['counts'].items(), key=lambda kv: -kv[1]):
            lines.append(f"  {geom_type:<20} {count}")
        lines.append("")
        lines.append("Per-face detail:")
        for f in result['faces']:
            x, y, z = f['center']
            loc_str = f"X={x}, Y={y}, Z={z}" if x is not None else "location unknown"
            radius_str = f", r={f['radius']}" if f['radius'] is not None else ""
            lines.append(f"  [{f['index']:>4}] {f['type']:<20} {loc_str}{radius_str}")

        self.txt_result.configure(state="normal")
        self.txt_result.delete("1.0", "end")
        self.txt_result.insert("1.0", "\n".join(lines))
        self.txt_result.configure(state="disabled")

    def show(self):
        self.root.mainloop()


def main():
    app = FaceInspectorGUI()
    app.show()


if __name__ == "__main__":
    main()
