import os
import glob
import numpy as np
import matplotlib.pyplot as plt
import pyart
import imageio
import boto3
from datetime import datetime, timedelta

# -----------------------------
# Configuration
# -----------------------------
TORONTO_RADAR = 'TOR'  # Toronto radar site
OUTPUT_GIF = 'toronto_radar.gif'
FRAMES = 5  # number of latest radar sweeps to include
TMP_DIR = 'radar_tmp'

# Create temporary folder
os.makedirs(TMP_DIR, exist_ok=True)

# AWS NEXRAD (Level 2) S3 Bucket
s3 = boto3.client('s3', region_name='us-east-1')  # NEXRAD data is public, no creds needed
BUCKET = 'noaa-nexrad-level2'

# -----------------------------
# 1. Find latest radar files
# -----------------------------
today = datetime.utcnow()
date_str = today.strftime('%Y/%m/%d')
prefix = f"{TORONTO_RADAR}/{today.strftime('%Y%m%d')}"

# List recent files
objects = s3.list_objects_v2(Bucket=BUCKET, Prefix=prefix, MaxKeys=20)
files = [obj['Key'] for obj in objects.get('Contents', []) if obj['Key'].endswith('.gz')]
files = sorted(files)[-FRAMES:]  # take last N sweeps

print("Files to download:", files)

# -----------------------------
# 2. Download files locally
# -----------------------------
local_files = []
for f in files:
    local_path = os.path.join(TMP_DIR, os.path.basename(f))
    if not os.path.exists(local_path):
        s3.download_file(BUCKET, f, local_path)
    local_files.append(local_path)

# -----------------------------
# 3. Create radar frames
# -----------------------------
images = []

for lf in local_files:
    radar = pyart.io.read_nexrad_archive(lf)
    display = pyart.graph.RadarMapDisplay(radar)
    
    fig = plt.figure(figsize=(5,3))
    ax = fig.add_subplot(111)
    
    # Plot reflectivity (dBZ)
    display.plot_ppi_map(
        'reflectivity', 0, ax=ax,
        title='', cmap='pyart_NWSRef', 
        colorbar_label='', mask_outside=True,
        min_lat=43.5, max_lat=45.0, min_lon=-80.0, max_lon=-78.0
    )
    
    plt.axis('off')
    fig.canvas.draw()
    
    # Save to buffer
    img_path = lf.replace('.gz', '.png')
    plt.savefig(img_path, bbox_inches='tight', pad_inches=0, transparent=True)
    plt.close(fig)
    
    images.append(imageio.imread(img_path))

# -----------------------------
# 4. Create animated GIF
# -----------------------------
imageio.mimsave(OUTPUT_GIF, images, duration=0.5)  # 0.5s per frame
print(f"Animated GIF saved: {OUTPUT_GIF}")
