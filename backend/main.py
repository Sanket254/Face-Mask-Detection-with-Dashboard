"""
FastAPI backend for the Face Mask Detection dashboard.

Endpoints
---------
POST /start              -> starts the webcam + detection loop
POST /stop                -> stops it
GET  /status               -> {"running": bool}
GET  /video_feed          -> MJPEG live video stream (use as <img src="...">)
GET  /violators             -> list of logged no-mask events (filterable)
GET  /filters/dates       -> distinct dates in the log, for the date filter
GET  /filters/locations   -> distinct locations in the log
GET  /images/<filename>   -> serves saved violation images (static mount)

Run with:
    uvicorn main:app --reload --port 8000
"""

import os
import sqlite3
import time

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from detector import worker, init_db, DB_PATH, SAVE_DIR

app = FastAPI(title="Face Mask Detection API")

# NOTE: allow_origins=["*"] is convenient for local development.
# When you deploy the frontend somewhere real, replace "*" with your
# actual frontend origin(s), e.g. ["https://your-frontend.netlify.app"].
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

# Serves saved violation images at /images/<filename>
app.mount("/images", StaticFiles(directory=SAVE_DIR), name="images")


@app.on_event("shutdown")
def release_camera_on_shutdown():
    # If Ctrl+C happens while detection is running, make sure the webcam
    # handle actually gets released -- otherwise the next `Start Detection`
    # can fail with a "device busy" error.
    if worker.running:
        worker.stop()


@app.get("/status")
def status():
    return {"running": worker.running}


@app.post("/start")
def start_detection():
    return worker.start()


@app.post("/stop")
def stop_detection():
    return worker.stop()


def _mjpeg_generator():
    try:
        while True:
            frame = worker.get_frame()
            if frame is not None:
                yield (
                    b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n'
                )
            else:
                # Nothing to show yet (not running) -- avoid a tight busy loop
                time.sleep(0.1)
            time.sleep(0.03)
    except GeneratorExit:
        # Browser tab closed or server is shutting down mid-stream. This
        # is expected any time the live feed is open when you stop
        # uvicorn -- just exit quietly instead of letting it bubble up
        # as a traceback.
        return


@app.get("/video_feed")
def video_feed():
    return StreamingResponse(
        _mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/violators")
def get_violators(
    date: str = Query(default=None),
    location: str = Query(default=None),
):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = "SELECT * FROM logs WHERE 1=1"
    params = []

    if date and date != "All":
        query += " AND date = ?"
        params.append(date)
    if location and location != "All":
        query += " AND location = ?"
        params.append(location)

    query += " ORDER BY id DESC"

    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


@app.get("/filters/dates")
def get_dates():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT date FROM logs ORDER BY date DESC")
    dates = [r[0] for r in cursor.fetchall()]
    conn.close()
    return dates


@app.get("/filters/locations")
def get_locations():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT location FROM logs")
    locations = [r[0] for r in cursor.fetchall()]
    conn.close()
    return locations


@app.delete("/violators/{entry_id}")
def delete_violator(entry_id: int):
    """Delete a log entry AND its saved image file, same as the delete
    button in the original Streamlit dashboard."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT image_name FROM logs WHERE id = ?", (entry_id,))
    row = cursor.fetchone()

    if row is None:
        conn.close()
        return {"status": "error", "message": f"No entry with id {entry_id}"}

    image_name = row[0]
    cursor.execute("DELETE FROM logs WHERE id = ?", (entry_id,))
    conn.commit()
    conn.close()

    image_path = os.path.join(SAVE_DIR, image_name)
    if os.path.exists(image_path):
        try:
            os.remove(image_path)
        except OSError as e:
            # DB row is already gone at this point; report it but don't
            # fail the whole request over a stray file.
            return {"status": "partial", "message": f"Row deleted, but file removal failed: {e}"}

    return {"status": "deleted", "id": entry_id, "image_name": image_name}


@app.delete("/violators")
def delete_all_violators():
    """Delete every log entry AND every saved image file. Irreversible."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT image_name FROM logs")
    image_names = [r[0] for r in cursor.fetchall()]

    cursor.execute("DELETE FROM logs")
    conn.commit()
    conn.close()

    images_removed = 0
    images_failed = []
    for name in image_names:
        path = os.path.join(SAVE_DIR, name)
        if os.path.exists(path):
            try:
                os.remove(path)
                images_removed += 1
            except OSError:
                images_failed.append(name)

    return {
        "status": "deleted_all",
        "entries_removed": len(image_names),
        "images_removed": images_removed,
        "images_failed": images_failed,
    }
