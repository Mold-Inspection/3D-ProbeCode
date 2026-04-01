import ezdxf
import matplotlib.pyplot as plt
import numpy as np

def view_3d_dxf(filename):
    try:
        doc = ezdxf.readfile(filename)
        msp = doc.modelspace()
    except Exception as e:
        print("Error:", e)
        return

    fig = plt.figure(figsize=(8, 8))
    ax = fig.add_subplot(111, projection='3d')

    for e in msp:

        # -------- LINE --------
        if e.dxftype() == 'LINE':
            s = e.dxf.start
            e_ = e.dxf.end
            ax.plot([s.x, e_.x], [s.y, e_.y], [s.z, e_.z])

        # -------- CIRCLE (REAL 3D SUPPORT) --------
        elif e.dxftype() == 'CIRCLE':
            center = np.array(e.dxf.center)
            r = e.dxf.radius

            normal = np.array(
                e.dxf.extrusion if e.dxf.hasattr("extrusion") else (0, 0, 1)
            )
            normal = normal / np.linalg.norm(normal)

            # find perpendicular vectors
            if abs(normal[2]) < 0.9:
                ref = np.array([0, 0, 1])
            else:
                ref = np.array([1, 0, 0])

            u = np.cross(normal, ref)
            u /= np.linalg.norm(u)
            v = np.cross(normal, u)

            theta = np.linspace(0, 2*np.pi, 60)

            circle = np.array([
                center + r * (np.cos(t)*u + np.sin(t)*v)
                for t in theta
            ])

            ax.plot(circle[:,0], circle[:,1], circle[:,2])

        # -------- ARC --------
        elif e.dxftype() == 'ARC':
            center = np.array(e.dxf.center)
            r = e.dxf.radius

            start = np.deg2rad(e.dxf.start_angle)
            end = np.deg2rad(e.dxf.end_angle)

            theta = np.linspace(start, end, 50)

            x = center[0] + r * np.cos(theta)
            y = center[1] + r * np.sin(theta)
            z = np.full_like(x, center[2])

            ax.plot(x, y, z)

        # -------- 3DFACE --------
        elif e.dxftype() == '3DFACE':
            pts = [e.dxf.vtx0, e.dxf.vtx1, e.dxf.vtx2, e.dxf.vtx3]
            for i in range(4):
                p1 = pts[i]
                p2 = pts[(i+1)%4]
                ax.plot([p1.x, p2.x], [p1.y, p2.y], [p1.z, p2.z])

    ax.set_xlabel('X')
    ax.set_ylabel('Y')
    ax.set_zlabel('Z')
    ax.set_title(f'DXF Viewer: {filename}')

    plt.show()


# 🔥 RUN HERE
view_3d_dxf("cube.dxf")