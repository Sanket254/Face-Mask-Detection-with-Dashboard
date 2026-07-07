# Face Mask Detection — Web App (FastAPI + HTML/CSS/JS)

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

