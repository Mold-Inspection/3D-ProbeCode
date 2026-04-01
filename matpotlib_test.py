import trimesh
import matplotlib.pyplot as plt
from matplotlib.widgets import Button
from matplotlib.colors import LinearSegmentedColormap
import numpy as np

# 1. โหลดไฟล์ .STL
mesh = trimesh.load('bottom clamping plate_pcs2b.stl')

# ดึงข้อมูลพิกัดทั้งหมด
x = mesh.vertices[:, 0]
y = mesh.vertices[:, 1]
z = mesh.vertices[:, 2]
triangles = mesh.faces

# คำนวณความลึกของแต่ละแกนสำหรับทำสี
x_faces = np.mean(x[triangles], axis=1) # ความลึกแนวแกน X (สำหรับ Left/Right)
y_faces = np.mean(y[triangles], axis=1) # ความลึกแนวแกน Y (สำหรับ Front/Back)
z_faces = np.mean(z[triangles], axis=1) # ความลึกแนวแกน Z (สำหรับ Top/Bottom)

# --- สร้างชุดสี (Colormap) ---
# เปลี่ยนสีตรงนี้: จากฟ้า (ลึกสุด) ไล่ไปหาส้ม (ตื้นสุด/พื้นผิว)
colors = ["skyblue", "orange"]
custom_cmap = LinearSegmentedColormap.from_list("depth_color", colors)
custom_cmap_r = custom_cmap.reversed() # ชุดสีแบบกลับด้าน สำหรับมุมมองฝั่งตรงข้าม

# 2. สร้างหน้าต่างกราฟ 2D 
fig, ax = plt.subplots(figsize=(11, 9))
plt.subplots_adjust(bottom=0.2, right=0.85) 

# สร้างพื้นที่สำหรับแถบสี
cax = fig.add_axes([0.88, 0.25, 0.03, 0.5]) 

# ฟังก์ชันสำหรับวาดภาพตาม 6 มุมมองมาตรฐาน
def draw_view(view_type):
    ax.clear()
    cax.clear() 
    
    if view_type == 'Top':
        tpc = ax.tripcolor(x, y, triangles, facecolors=z_faces, cmap=custom_cmap, edgecolors='none')
        ax.set_title('Top View', fontsize=16)
        
    elif view_type == 'Bottom':
        # มองจากด้านใต้ พลิกแกน X
        tpc = ax.tripcolor(-x, y, triangles, facecolors=z_faces, cmap=custom_cmap_r, edgecolors='none')
        ax.set_title('Bottom View', fontsize=16)
        
    elif view_type == 'Front':
        # มองเข้าหาแกน Y
        tpc = ax.tripcolor(x, z, triangles, facecolors=y_faces, cmap=custom_cmap_r, edgecolors='none')
        ax.set_title('Front View', fontsize=16)
        
    elif view_type == 'Back':
        # มองเข้าหาแกน -Y ต้องพลิกแกน X
        tpc = ax.tripcolor(-x, z, triangles, facecolors=y_faces, cmap=custom_cmap, edgecolors='none')
        ax.set_title('Back View', fontsize=16)
        
    elif view_type == 'Left':
        # มองเข้าหาแกน X
        tpc = ax.tripcolor(y, z, triangles, facecolors=x_faces, cmap=custom_cmap_r, edgecolors='none')
        ax.set_title('Left Side View', fontsize=16)
        
    elif view_type == 'Right':
        # มองเข้าหาแกน -X ต้องพลิกแกน Y
        tpc = ax.tripcolor(-y, z, triangles, facecolors=x_faces, cmap=custom_cmap, edgecolors='none')
        ax.set_title('Right Side View', fontsize=16)

    ax.set_aspect('equal') 
    ax.axis('off')
    
    # วาดแถบสี
    cbar = fig.colorbar(tpc, cax=cax)
    cbar.set_label('Depth (Units)', fontsize=12)
    fig.canvas.draw_idle() 

# วาดครั้งแรก
draw_view('Top')

# --- ฟังก์ชัน: ซูมและเลื่อน (Pan & Zoom) ---
def on_scroll(event):
    if event.inaxes != ax: return 
    base_scale = 1.2 
    if event.button == 'up': scale_factor = 1 / base_scale
    elif event.button == 'down': scale_factor = base_scale
    else: scale_factor = 1

    xdata, ydata = event.xdata, event.ydata
    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    new_width = (xlim[1] - xlim[0]) * scale_factor
    new_height = (ylim[1] - ylim[0]) * scale_factor
    relx = (xlim[1] - xdata) / (xlim[1] - xlim[0])
    rely = (ylim[1] - ydata) / (ylim[1] - ylim[0])
    ax.set_xlim([xdata - new_width * (1 - relx), xdata + new_width * relx])
    ax.set_ylim([ydata - new_height * (1 - rely), ydata + new_height * rely])
    fig.canvas.draw_idle()

drag_state = {'is_dragging': False, 'x': 0, 'y': 0, 'xlim': None, 'ylim': None}

def on_press(event):
    if event.inaxes != ax: return
    if event.button == 1: 
        drag_state['is_dragging'] = True
        drag_state['x'], drag_state['y'] = event.x, event.y
        drag_state['xlim'], drag_state['ylim'] = ax.get_xlim(), ax.get_ylim()

def on_release(event):
    if event.button == 1: drag_state['is_dragging'] = False

def on_motion(event):
    if not drag_state['is_dragging'] or event.inaxes != ax: return
    dx_pixel, dy_pixel = event.x - drag_state['x'], event.y - drag_state['y']
    inv = ax.transData.inverted()
    p0 = inv.transform((0, 0))
    p1 = inv.transform((dx_pixel, dy_pixel))
    dx_data, dy_data = p1[0] - p0[0], p1[1] - p0[1]
    ax.set_xlim(drag_state['xlim'][0] - dx_data, drag_state['xlim'][1] - dx_data)
    ax.set_ylim(drag_state['ylim'][0] - dy_data, drag_state['ylim'][1] - dy_data)
    fig.canvas.draw_idle()

fig.canvas.mpl_connect('scroll_event', on_scroll)
fig.canvas.mpl_connect('button_press_event', on_press)
fig.canvas.mpl_connect('button_release_event', on_release)
fig.canvas.mpl_connect('motion_notify_event', on_motion)


# 3. สร้างปุ่มกดทั้ง 6 มุมมอง (จัดเป็น 2 แถว)
bw, bh = 0.12, 0.05 # กว้าง, สูง ของปุ่ม
y_row1, y_row2 = 0.10, 0.03 # ตำแหน่ง Y (แถวบน, แถวล่าง)
x_col1, x_col2, x_col3 = 0.15, 0.35, 0.55 # ตำแหน่ง X (คอลัมน์ซ้าย, กลาง, ขวา)

ax_top = plt.axes([x_col1, y_row1, bw, bh])
ax_under = plt.axes([x_col1, y_row2, bw, bh])

ax_front = plt.axes([x_col2, y_row1, bw, bh])
ax_back = plt.axes([x_col2, y_row2, bw, bh])

ax_left = plt.axes([x_col3, y_row1, bw, bh])
ax_right = plt.axes([x_col3, y_row2, bw, bh])

btn_top = Button(ax_top, 'Top')
btn_under = Button(ax_under, 'Bottom')
btn_front = Button(ax_front, 'Front')
btn_back = Button(ax_back, 'Back')
btn_left = Button(ax_left, 'Left')
btn_right = Button(ax_right, 'Right')

# เชื่อมปุ่มเข้ากับฟังก์ชัน
btn_top.on_clicked(lambda event: draw_view('Top'))
btn_under.on_clicked(lambda event: draw_view('Bottom'))
btn_front.on_clicked(lambda event: draw_view('Front'))
btn_back.on_clicked(lambda event: draw_view('Back'))
btn_left.on_clicked(lambda event: draw_view('Left'))
btn_right.on_clicked(lambda event: draw_view('Right'))

plt.show()