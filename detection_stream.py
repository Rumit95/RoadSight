"""Starts detector_worker.py as a separate process and hands back its results one at a time."""
import json
import os
import subprocess
import sys

import config

WORKER = os.path.join(config.ROOT, "detector_worker.py")
# Windows only: no console window, and a lower priority so the page and the map stay smooth while YOLO runs.
WINDOWS_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)


def stream_detections(video_path, confidence, frame_step):
    # Yields dicts: one {"type": "start"}, then one {"type": "frame"} per processed frame,
    # then {"type": "end"}. If the worker fails, it yields {"type": "error", "message": ...}.
    command = [
        sys.executable,
        WORKER,
        video_path,
        config.WEIGHTS,
        str(confidence),
        str(frame_step),
        str(config.IMAGE_SIZE),
        str(config.DISPLAY_WIDTH),
    ]
    # The worker prints UTF-8 text; without this, Windows may use a smaller character set.
    environment = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        env=environment,
        creationflags=WINDOWS_FLAGS,
    )

    last_log_lines = []
    try:
        for line in process.stdout:
            if line.startswith("{"):
                yield json.loads(line)
            else:
                last_log_lines = (last_log_lines + [line.strip()])[-15:]

        process.wait()
        if process.returncode != 0:
            yield {"type": "error", "message": "\n".join(last_log_lines) or "The detector stopped unexpectedly."}
    finally:
        # Runs when the video ends, or when Streamlit stops this script (for example on a new click).
        if process.poll() is None:
            process.kill()
