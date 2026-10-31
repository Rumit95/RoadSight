"""Downloads short KITTI drives (camera frames plus GPS for every frame) and makes demo files.

For each drive it writes demo/kitti_drive_<number>.mp4 (left color camera, 10 frames per second)
and demo/kitti_drive_<number>.csv (frame, time_s, latitude, longitude for every frame).

    python download_kitti_demo.py              the default 15 available drives
    python download_kitti_demo.py 0002 0011    other drives recorded on 2011-09-26

Each zip is 300 to 900 MB. It is deleted after the camera and GPS files are taken out of it.

KITTI data by Geiger, Lenz, Stiller and Urtasun, "Vision meets Robotics: The KITTI Dataset", IJRR 2013.
Licence CC BY-NC-SA 3.0: non-commercial use with attribution. Do not publish the files.
"""
import os
import socket
import sys
import tempfile
import zipfile

import cv2
import numpy as np
import requests

import config

BASE_URL = "https://s3.eu-central-1.amazonaws.com/avg-kitti/raw_data"
DATE = "2011_09_26"
FPS = 10  # KITTI records 10 frames per second
DEFAULT_DRIVES = [
    "0001", "0002", "0005", "0009", "0011", "0013", "0014", "0015",
    "0017", "0018", "0019", "0020", "0022", "0023", "0027",
]

# IPv6 connects hang on some corporate networks, so force IPv4.
_getaddrinfo = socket.getaddrinfo
socket.getaddrinfo = lambda host, port, family=0, *a, **k: _getaddrinfo(host, port, socket.AF_INET, *a, **k)


def download(url, path):
    with requests.get(url, stream=True, timeout=60) as response:
        if response.status_code == 404:
            print(f"  drive archive not found (404): {url}")
            return False
        response.raise_for_status()
        total_mb = int(response.headers.get("Content-Length", 0)) // (1024 * 1024)
        megabytes = 0
        with open(path, "wb") as zip_file:
            for chunk in response.iter_content(1024 * 1024):
                zip_file.write(chunk)
                megabytes = megabytes + 1
                if megabytes % 100 == 0:
                    print(f"  downloaded {megabytes} of {total_mb} MB")
    return True


def make_demo_files(zip_path, drive):
    folder = f"{DATE}/{DATE}_drive_{drive}_sync"
    video_path = os.path.join(config.DEMO_DIR, f"kitti_drive_{drive}.mp4")
    csv_path = os.path.join(config.DEMO_DIR, f"kitti_drive_{drive}.csv")

    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
        image_names = sorted(n for n in names if n.startswith(f"{folder}/image_02/data/") and n.endswith(".png"))
        gps_names = sorted(n for n in names if n.startswith(f"{folder}/oxts/data/") and n.endswith(".txt"))
        if len(image_names) == 0 or len(image_names) != len(gps_names):
            sys.exit(f"Unexpected zip content: {len(image_names)} images and {len(gps_names)} GPS files.")

        writer = None
        csv_lines = ["frame,time_s,latitude,longitude"]
        for frame_number, (image_name, gps_name) in enumerate(zip(image_names, gps_names)):
            image = cv2.imdecode(np.frombuffer(archive.read(image_name), np.uint8), cv2.IMREAD_COLOR)
            if writer is None:
                height, width = image.shape[:2]
                writer = cv2.VideoWriter(video_path, cv2.VideoWriter_fourcc(*"mp4v"), FPS, (width, height))
            writer.write(image)

            # The first two numbers of a KITTI GPS record are latitude and longitude.
            values = archive.read(gps_name).decode().split()
            csv_lines.append(f"{frame_number},{frame_number / FPS},{values[0]},{values[1]}")
        writer.release()

    with open(csv_path, "w") as csv_file:
        csv_file.write("\n".join(csv_lines) + "\n")
    print(f"  wrote {len(image_names)} frames ({len(image_names) / FPS:.1f} s) to {video_path}")
    print(f"  wrote their GPS positions to {csv_path}")


def main():
    drives = sys.argv[1:] or DEFAULT_DRIVES
    os.makedirs(config.DEMO_DIR, exist_ok=True)

    for drive in drives:
        # The csv file is written last, so it only exists when the drive finished.
        if os.path.exists(os.path.join(config.DEMO_DIR, f"kitti_drive_{drive}.csv")):
            print(f"Drive {drive}: already done, skipping")
            continue
        print(f"Drive {drive}: downloading")
        url = f"{BASE_URL}/{DATE}_drive_{drive}/{DATE}_drive_{drive}_sync.zip"
        with tempfile.TemporaryDirectory() as temp_folder:
            zip_path = os.path.join(temp_folder, f"drive_{drive}.zip")
            if not download(url, zip_path):
                continue
            make_demo_files(zip_path, drive)


if __name__ == "__main__":
    main()
