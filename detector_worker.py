"""Runs the YOLO model on a video and prints one JSON line per processed frame.

This is a separate program on purpose: PyTorch crashes when it is imported inside Streamlit on
this PC, so Streamlit starts this script (detection_stream.py) and only reads its output.

Usage: python detector_worker.py video weights confidence frame_step image_size display_width
"""
import base64
import json
import sys
import time

import cv2
from ultralytics import YOLO

import model_adapter


def send(message):
    print(json.dumps(message), flush=True)


def encode_picture(image, display_width):
    # Shrinks the picture and turns it into text so it can travel through the pipe.
    height, width = image.shape[:2]
    if width > display_width:
        image = cv2.resize(image, (display_width, int(height * display_width / width)))
    ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return base64.b64encode(buffer).decode("ascii")


def main():
    video_path, weights = sys.argv[1], sys.argv[2]
    confidence = float(sys.argv[3])
    frame_step = int(sys.argv[4])
    image_size = int(sys.argv[5])
    display_width = int(sys.argv[6])

    capture = cv2.VideoCapture(video_path)
    if not capture.isOpened():
        sys.exit(f"Could not open the video: {video_path}")

    fps = capture.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 0:
        fps = 30
    total_frames = max(int(capture.get(cv2.CAP_PROP_FRAME_COUNT)), 0)

    model = YOLO(weights)
    send({"type": "start", "fps": fps, "total_frames": total_frames, "duration_s": total_frames / fps})

    clock_start = time.time()
    frame_number = 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break

        if frame_number % frame_step == 0:
            time_s = frame_number / fps
            # Do not run ahead of the video: wait if the model is faster than real time.
            wait = time_s - (time.time() - clock_start)
            if wait > 0:
                time.sleep(wait)

            result = model.predict(frame, conf=confidence, imgsz=image_size, verbose=False)[0]
            detections = model_adapter.read_detections(model, result)

            send(
                {
                    "type": "frame",
                    "frame": frame_number,
                    "time_s": time_s,
                    "detections": detections,
                    "image": encode_picture(result.plot(), display_width),
                }
            )
        frame_number = frame_number + 1

    send({"type": "end"})


if __name__ == "__main__":
    main()
