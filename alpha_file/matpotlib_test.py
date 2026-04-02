import trimesh
import tkinter as tk
from tkinter import filedialog

def open_3d_viewer():
    # Hide the ugly default tkinter window
    root = tk.Tk()
    root.withdraw()
    
    # Pop up the file selector
    filepath = filedialog.askopenfilename(
        title="Select STL Reference File",
        filetypes=[("STL Files", "*.stl"), ("All Files", "*.*")]
    )
    
    if filepath:
        print(f"Loading: {filepath}")
        try:
            # Load the mesh
            mesh = trimesh.load(filepath)
            
            # .show() opens a dedicated 3D window where you can drag to rotate and scroll to zoom!
            mesh.show()
        except Exception as e:
            print(f"Error loading file: {e}")
    else:
        print("Canceled.")

if __name__ == "__main__":
    open_3d_viewer()