# Face Mask Detection — Web App (FastAPI + HTML/CSS/JS)

This merges your two Streamlit apps (live camera + violator dashboard) into
one web frontend, backed by a FastAPI server. Your detection/saving logic
from `simplesave.py` is preserved almost line-for-line inside
`backend/detector.py` — it's just wrapped in a class so it can be
started/stopped from a button instead of running as a blocking script.

## 1. Directory structure

Put things exactly like this (or adjust the paths in `detector.py` /
`script.js` if you rename anything):

```
FaceMaskDetection/
├── backend/
│   ├── main.py          <- FastAPI app (routes)
│   ├── detector.py       <- your detection/saving logic, start/stop-able
│   ├── requirements.txt
│   └── log.db            <- created automatically on first run
│
└── frontend/
    ├── index.html
    ├── style.css
    └── script.js
```

Your existing `yolov5/` repo and `best.pt` weights, and the
`NoMaskImages/` folder, can stay exactly where they already are on disk —
`detector.py` points at them via `MODEL_REPO`, `WEIGHTS_PATH`, and
`SAVE_DIR` at the top of the file, same as your original script.

## 2. What to install (step by step, VS Code)

1. **Install Python 3.10 or 3.11** if you don't already have it (avoid
   3.12+ for now — some torch/YOLOv5 builds lag behind).
2. **Open the `FaceMaskDetection` folder in VS Code**
   (`File > Open Folder…`).
3. **Install the Python extension** in VS Code if you don't have it
   (Ms-Python.python) — gives you linting + the interpreter picker.
4. **Create a virtual environment** (Terminal in VS Code, from the
   `FaceMaskDetection/backend` folder):
   ```
   python -m venv venv
   venv\Scripts\activate        (Windows)
   source venv/bin/activate     (Mac/Linux)
   ```
5. **Install backend dependencies:**
   ```
   pip install -r requirements.txt
   ```
   Note: this installs the CPU build of torch by default. If you trained
   with CUDA and want GPU inference locally too, install torch separately
   first using the command from https://pytorch.org/get-started/locally/
   for your CUDA version, *then* run the line above.
6. **Live Server extension (optional, for the frontend)** — install
   "Live Server" by Ritwick Dey in VS Code so you can right-click
   `index.html` → "Open with Live Server" instead of double-clicking the
   file. Not required, but avoids some browser quirks with fetch() on
   `file://` URLs.

## 3. Running it

**Backend** (from `FaceMaskDetection/backend`, venv activated):
```
uvicorn main:app --reload --port 8000
```
Leave this terminal running. First `/start` call will take a few seconds
while YOLOv5 loads the model.

**Frontend**: open `frontend/index.html` directly in your browser, or use
Live Server. It talks to the backend at `http://127.0.0.1:8000` by
default — see the note below.

## 4. The one thing you flagged: hardcoded URL + CORS

Both are already handled in this version:

- **CORS**: `backend/main.py` adds `CORSMiddleware` with
  `allow_origins=["*"]`. That's fine for local development. When you
  deploy the frontend (e.g. to Netlify), tighten this to your actual
  frontend URL, e.g.:
  ```python
  allow_origins=["https://your-app.netlify.app"]
  ```
- **Frontend URL**: instead of scattering `127.0.0.1:8000` through the
  code, there's a single constant at the top of `frontend/script.js`:
  ```js
  const API_BASE_URL = "http://127.0.0.1:8000";
  ```
  When you deploy the backend to Render, change this one line to your
  Render URL (something like `https://facemask-backend.onrender.com`)
  and redeploy the frontend. That's the only edit needed.

## 5. Notes on what changed vs. your Streamlit code

- `cv2.imshow(...)` is gone (can't show a native OpenCV window from a
  web server) — instead each annotated frame is JPEG-encoded and served
  as an MJPEG stream at `/video_feed`, which the frontend shows in an
  `<img>` tag. This is the standard way to pipe an OpenCV loop into a
  browser.
- The `while True` capture loop now runs on a background thread
  (`DetectionWorker._run` in `detector.py`) so the FastAPI server stays
  responsive to `/start`, `/stop`, and `/violators` requests while it's
  running.
- Detection thresholds, save interval (200 frames), label logic, box
  drawing, and the DB schema/insert logic are unchanged from your
  original script.
- The dashboard's "Filter by Date" / "Filter by Location" dropdowns are
  now driven by `/filters/dates` and `/filters/locations`, which just
  return the distinct values already in `log.db`.

## 6. Deployment (when you're ready)

- **Backend → Render**: push the `backend/` folder as its own repo (or
  subfolder with a root directory setting), add a `Start Command` of
  `uvicorn main:app --host 0.0.0.0 --port $PORT`. Note that Render's
  free/standard web services don't have a physical webcam attached, so
  `/start` will only work if you're running the backend on a machine
  that actually has the camera (e.g. locally, or on a device at
  SJT-417). If the deployed goal is "view the dashboard remotely," that
  works fine over Render — it's only live camera capture that needs to
  run on hardware with a webcam.
- **Frontend → Netlify**: drag-and-drop the `frontend/` folder in
  Netlify's deploy UI, or connect the repo. Just remember to update
  `API_BASE_URL` in `script.js` to your Render backend URL first.
