"""
Detection worker for the Face Mask Detection system.

This wraps the original detection/saving logic (from your simplesave.py
script) inside a controllable class so FastAPI can start/stop it and
stream frames over HTTP instead of using cv2.imshow().

The core detection + saving logic below is intentionally left almost
identical to your original script -- only the parts needed to turn it
into a start/stop-able background worker (instead of a blocking `while
True` loop with cv2.imshow) have changed.
"""

import os
import time
import sqlite3
import threading
import warnings
from datetime import datetime

import cv2
import torch

# YOLOv5's own code (models/common.py) calls a deprecated torch.cuda.amp
# API on every inference call. It's harmless (doubly so on CPU), but it
# fires once per frame and floods the terminal. Silence just this one.
warnings.filterwarnings(
    "ignore",
    message=r".*torch\.cuda\.amp\.autocast\(args\.\.\.\) is deprecated.*",
    category=FutureWarning,
)

# YOLOv5 checkpoints (like best.pt) are pickled model objects, not just
# tensors. Newer torch versions default torch.load() to weights_only=True,
# which blocks unpickling those objects. This patch restores the old
# behavior globally for this process -- safe here since best.pt is your
# own trained, trusted checkpoint.
_original_torch_load = torch.load
def _patched_load(*args, **kwargs):
    kwargs.setdefault("weights_only", False)
    return _original_torch_load(*args, **kwargs)
torch.load = _patched_load

# ---------------------------------------------------------------------------
# CONFIG -- paths are relative to this file, so the project works no
# matter whose machine it's cloned onto. Expected layout:
#
#   backend/
#     detector.py            <- this file
#     yolov5/                <- your cloned YOLOv5 repo (yolov5/.git removed)
#       runs/train/retrain_mask_model5/weights/best.pt
#     NoMaskImages/           <- created automatically, gitignored
#
# If your weights end up somewhere else, just change WEIGHTS_PATH below.
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

MODEL_REPO = os.path.join(BASE_DIR, "yolov5")
WEIGHTS_PATH = os.path.join(
    MODEL_REPO, "runs", "train", "retrain_mask_model5", "weights", "best.pt"
)
SAVE_DIR = os.path.join(BASE_DIR, "NoMaskImages")

# DB now lives next to this file (backend/log.db) so the API and the
# worker thread always agree on where it is.
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "log.db")

os.makedirs(SAVE_DIR, exist_ok=True)

class_names = ['NoMask', 'Mask']


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        image_name TEXT,
        date TEXT,
        time TEXT,
        location TEXT
    )
    """)
    conn.commit()
    conn.close()


class DetectionWorker:
    """Runs the webcam + YOLOv5 loop on a background thread.

    start() / stop() replace the old `while True` + cv2.imshow loop.
    The latest annotated frame is kept in memory (as JPEG bytes) so the
    FastAPI /video_feed endpoint can stream it to the browser (MJPEG),
    instead of opening a native OpenCV window.
    """

    def __init__(self):
        self.model = None
        self.cap = None
        self.thread = None
        self.running = False

        self._frame_lock = threading.Lock()
        self.latest_frame = None  # JPEG-encoded bytes of the last frame

        # Same interval logic as your original script
        self.save_interval = 200  # frames
        self.frame_count = 0
        self.last_saved_frame = -self.save_interval

    # -- model -------------------------------------------------------
    def load_model(self):
        if self.model is None:
            self.model = torch.hub.load(
                MODEL_REPO,
                'custom',
                path=WEIGHTS_PATH,
                source='local'
            )

    # -- lifecycle -----------------------------------------------------
    def start(self):
        if self.running:
            return {"status": "already_running"}

        self.load_model()

        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            return {"status": "error", "message": "Could not open webcam"}

        self.running = True
        self.frame_count = 0
        self.last_saved_frame = -self.save_interval

        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        return {"status": "started"}

    def stop(self):
        self.running = False
        if self.thread is not None:
            self.thread.join(timeout=2)
            self.thread = None
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        with self._frame_lock:
            self.latest_frame = None
        return {"status": "stopped"}

    # -- main loop (same detection/saving logic as simplesave.py) -----
    def _run(self):
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                break

            self.frame_count += 1

            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.model(rgb_frame)
            detections = results.xyxy[0]

            no_mask_detected = False

            for *xyxy, conf, cls in detections:
                label_idx = int(cls.item())
                label = class_names[label_idx]

                x1, y1, x2, y2 = map(int, xyxy)

                color = (0, 255, 0) if label == "Mask" else (0, 0, 255)

                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(frame, f"{label} ({conf.item()*100:.1f}%)",
                            (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.7,
                            (255, 255, 255),
                            2)

                if label == "NoMask":
                    no_mask_detected = True

            if no_mask_detected and (self.frame_count - self.last_saved_frame >= self.save_interval):
                filename = f"no_mask_{int(time.time())}.jpg"
                save_path = os.path.join(SAVE_DIR, filename)

                cv2.imwrite(save_path, frame)

                now = datetime.now()
                date = now.strftime("%Y-%m-%d")
                time_now = now.strftime("%H:%M:%S")
                location = "SJT-417"

                # Open a fresh connection here since this runs on the
                # worker thread (sqlite3 connections aren't safe to
                # share across threads by default).
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO logs (image_name, date, time, location) VALUES (?, ?, ?, ?)",
                    (filename, date, time_now, location)
                )
                conn.commit()
                conn.close()

                self.last_saved_frame = self.frame_count

            # Encode the annotated frame as JPEG for the MJPEG stream
            ok, buffer = cv2.imencode('.jpg', frame)
            if ok:
                with self._frame_lock:
                    self.latest_frame = buffer.tobytes()

        self.running = False

    def get_frame(self):
        with self._frame_lock:
            return self.latest_frame


# Single shared worker instance used by the FastAPI app
worker = DetectionWorker()
