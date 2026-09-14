import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg
import numpy as np
from moviepy.editor import VideoFileClip, VideoClip, clips_array

# CONFIG FILES HERE: 
vid_file = "coffee_test1.mp4"
csv_file = "03-09_16-57.csv"
start_time = "2026-03-09 17:03:47" # has to match csv timestamp format

# cols to render, display name, and line color
datasets = {
    "PM1.0": ("PM1.0 Levels", "#0d6efd"),
    "PM2.5": ("PM2.5 Levels", "#dc3545"),
    "PM4.0": ("PM4.0 Levels", "#198754"),
    "PM10.0": ("PM10.0 Levels", "#ffc107"),
    "Humidity": ("Humidity (%)", "#0dcaf0"),
    "Temperature": ("Temperature (C)", "#fd7e14"),
    "VOC": ("VOC Levels", "#6610f2"),
    "NOx": ("NOx Levels", "#d63384"),
    "CO2": ("CO2 (ppm)", "#20c997")
}

print(f"loading data from {csv_file}...")
df = pd.read_csv(csv_file)

# clean up spaces in col names just in case
df.columns = df.columns.str.strip()

# convert time col to datetime
time_col = df.columns[0]
df[time_col] = pd.to_datetime(df[time_col])

# figure out relative seconds from when the vid started
start_dt = pd.to_datetime(start_time)
df['rel_secs'] = (df[time_col] - start_dt).dt.total_seconds()

# drop data from before the video started
df = df[df['rel_secs'] >= 0].copy()

# start handling the video
main_vid = VideoFileClip(vid_file)
duration = main_vid.duration
fps = main_vid.fps

# dark mode looks better
plt.style.use('dark_background') 

for col_name, (disp_name, color) in datasets.items():
    print(f"rendering {disp_name}...")
    
    if col_name not in df.columns:
        print(f"skipped {col_name}, not in csv")
        continue

    # lock y-axis so it doesn't bounce around
    y_min = df[col_name].min()
    y_max = df[col_name].max()
    padding = (y_max - y_min) * 0.05
    if padding == 0: padding = 1

    # make figure
    fig, ax = plt.subplots(figsize=(6, 4), dpi=100)
    canvas = FigureCanvasAgg(fig)

    # frame generator for moviepy
    def draw_frame(t):
        ax.clear()
        
        # draw the line and fill under it
        ax.plot(df['rel_secs'], df[col_name], color=color, linewidth=2)
        ax.fill_between(df['rel_secs'], df[col_name], color=color, alpha=0.2)
        
        # red tracking line
        ax.axvline(x=t, color='red', linewidth=2)
        
        ax.set_ylim(y_min - padding, y_max + padding)
        
        # sliding 20 sec window
        if t > 10:
            ax.set_xlim(t - 10, t + 10)
        else:
            ax.set_xlim(0, 20)
            
        ax.set_title(disp_name, fontsize=14, pad=10)
        ax.set_xlabel("time (secs)", fontsize=10)
        ax.grid(True, linestyle='--', alpha=0.3)
        fig.tight_layout()

        # convert fig to rgb array
        canvas.draw()
        frame = np.frombuffer(canvas.tostring_rgb(), dtype='uint8')
        frame = frame.reshape(fig.canvas.get_width_height()[::-1] + (3,))
        return frame

    # stitch the graph and video together
    graph_clip = VideoClip(draw_frame, duration=duration)
    graph_clip = graph_clip.resize(height=main_vid.h)

    final_vid = clips_array([[main_vid, graph_clip]])

    # export it
    out_name = f"output_{col_name.replace('.', '')}.mp4"
    final_vid.write_videofile(out_name, fps=fps, codec="libx264", audio_codec="aac")

    # clean up ram
    plt.close(fig)

main_vid.close()
print("done processing everything!")