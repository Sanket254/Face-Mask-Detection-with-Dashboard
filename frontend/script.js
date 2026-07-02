// ============================================================================
// SENTRY — Mask Compliance Monitor — frontend logic
// ============================================================================

// ---------------------------------------------------------------------------
// IMPORTANT: this is the ONE place you need to change the backend URL.
// - Local dev:      "http://127.0.0.1:8000"
// - After deploy:   "https://your-backend.onrender.com"  (no trailing slash)
// ---------------------------------------------------------------------------
const API_BASE_URL = "http://127.0.0.1:8000";

// ---------------------------------------------------------------------------
// Element references
// ---------------------------------------------------------------------------
const startBtn = document.getElementById("startBtn");
const stopBtn = document.getElementById("stopBtn");
const feedImg = document.getElementById("feedImg");
const viewport = document.getElementById("viewport");
const viewportEmpty = document.getElementById("viewportEmpty");
const recIndicator = document.getElementById("recIndicator");

const connChip = document.getElementById("connChip");
const connLabel = document.getElementById("connLabel");
const camChip = document.getElementById("camChip");
const camLabel = document.getElementById("camLabel");
const clockChip = document.getElementById("clockChip");

const alertBanner = document.getElementById("alertBanner");
const alertText = document.getElementById("alertText");

const dateFilter = document.getElementById("dateFilter");
const locationFilter = document.getElementById("locationFilter");
const refreshBtn = document.getElementById("refreshBtn");

const logTableBody = document.getElementById("logTableBody");
const tableEmpty = document.getElementById("tableEmpty");
const entryCount = document.getElementById("entryCount");

const lightbox = document.getElementById("lightbox");
const lightboxImg = document.getElementById("lightboxImg");
const lightboxClose = document.getElementById("lightboxClose");

let lastKnownEntryId = null;
let violatorsPollTimer = null;

// ---------------------------------------------------------------------------
// Clock
// ---------------------------------------------------------------------------
function tickClock() {
  const now = new Date();
  clockChip.textContent = now.toLocaleTimeString([], { hour12: false });
}
setInterval(tickClock, 1000);
tickClock();

// ---------------------------------------------------------------------------
// Backend connectivity + running status
// ---------------------------------------------------------------------------
async function pollStatus() {
  try {
    const res = await fetch(`${API_BASE_URL}/status`);
    if (!res.ok) throw new Error("bad status");
    const data = await res.json();

    setConnected(true);
    setCameraRunning(data.running);
  } catch (err) {
    setConnected(false);
  }
}

function setConnected(isConnected) {
  connChip.classList.toggle("online", isConnected);
  connChip.classList.toggle("offline", !isConnected);
  connLabel.textContent = isConnected ? "Backend Online" : "Backend Unreachable";
}

function setCameraRunning(isRunning) {
  camChip.classList.toggle("live", isRunning);
  camChip.classList.toggle("offline", !isRunning);
  camLabel.textContent = isRunning ? "Camera Live" : "Camera Idle";

  startBtn.disabled = isRunning;
  stopBtn.disabled = !isRunning;
  recIndicator.classList.toggle("visible", isRunning);

  if (isRunning) {
    feedImg.src = `${API_BASE_URL}/video_feed?t=${Date.now()}`;
    feedImg.style.display = "block";
    viewportEmpty.style.display = "none";
  } else {
    feedImg.removeAttribute("src");
    feedImg.style.display = "none";
    viewportEmpty.style.display = "block";
  }
}

// ---------------------------------------------------------------------------
// Start / Stop
// ---------------------------------------------------------------------------
startBtn.addEventListener("click", async () => {
  startBtn.disabled = true;
  camLabel.textContent = "Starting…";
  try {
    const res = await fetch(`${API_BASE_URL}/start`, { method: "POST" });

    let data = null;
    try {
      data = await res.json();
    } catch {
      // response wasn't JSON (e.g. a raw 500 traceback page) -- fall through
    }

    if (!res.ok) {
      const detail = data?.detail || data?.message;
      alert(
        `Backend returned an error (HTTP ${res.status}).` +
        (detail ? `\n\n${detail}` : "\n\nCheck the uvicorn terminal for the full traceback.")
      );
      startBtn.disabled = false;
      return;
    }

    if (data?.status === "error") {
      alert(`Could not start camera: ${data.message || "unknown error"}`);
      startBtn.disabled = false;
      return;
    }

    setCameraRunning(true);
  } catch (err) {
    // This only fires on an actual network failure (backend down, wrong
    // URL/port, CORS block) -- not on 4xx/5xx responses, which are
    // handled above.
    alert("Could not reach the backend. Is it running?");
    startBtn.disabled = false;
  }
});

stopBtn.addEventListener("click", async () => {
  stopBtn.disabled = true;
  try {
    await fetch(`${API_BASE_URL}/stop`, { method: "POST" });
  } catch (err) {
    // ignore -- we still reflect stopped state locally
  }
  setCameraRunning(false);
});

// ---------------------------------------------------------------------------
// Filters
// ---------------------------------------------------------------------------
async function loadFilterOptions() {
  try {
    const [datesRes, locationsRes] = await Promise.all([
      fetch(`${API_BASE_URL}/filters/dates`),
      fetch(`${API_BASE_URL}/filters/locations`),
    ]);
    const dates = await datesRes.json();
    const locations = await locationsRes.json();

    fillSelect(dateFilter, dates);
    fillSelect(locationFilter, locations);
  } catch (err) {
    // backend not reachable yet -- filters just stay at "All"
  }
}

function fillSelect(selectEl, values) {
  const current = selectEl.value;
  selectEl.innerHTML = `<option value="All">All</option>`;
  values.forEach((v) => {
    const opt = document.createElement("option");
    opt.value = v;
    opt.textContent = v;
    selectEl.appendChild(opt);
  });
  if ([...selectEl.options].some((o) => o.value === current)) {
    selectEl.value = current;
  }
}

dateFilter.addEventListener("change", loadViolators);
locationFilter.addEventListener("change", loadViolators);
refreshBtn.addEventListener("click", () => {
  loadFilterOptions();
  loadViolators();
});

const deleteAllBtn = document.getElementById("deleteAllBtn");
deleteAllBtn.addEventListener("click", async () => {
  if (!confirm("Delete ALL violation entries and images? This cannot be undone.")) return;
  if (!confirm("Really sure? Everything in the log will be permanently gone.")) return;

  try {
    const res = await fetch(`${API_BASE_URL}/violators`, { method: "DELETE" });
    const data = await res.json();
    if (data.status !== "deleted_all") {
      alert("Something went wrong deleting entries.");
      return;
    }
    loadViolators();
  } catch (err) {
    alert("Could not reach the backend to delete entries.");
  }
});

// ---------------------------------------------------------------------------
// Violation log
// ---------------------------------------------------------------------------
async function loadViolators() {
  const params = new URLSearchParams();
  if (dateFilter.value && dateFilter.value !== "All") params.set("date", dateFilter.value);
  if (locationFilter.value && locationFilter.value !== "All") params.set("location", locationFilter.value);

  try {
    const res = await fetch(`${API_BASE_URL}/violators?${params.toString()}`);
    const rows = await res.json();
    renderTable(rows);
    checkForNewViolation(rows);
  } catch (err) {
    // leave existing table as-is if the backend is briefly unreachable
  }
}

function renderTable(rows) {
  entryCount.textContent = `${rows.length} entr${rows.length === 1 ? "y" : "ies"}`;
  logTableBody.innerHTML = "";
  tableEmpty.classList.toggle("visible", rows.length === 0);

  rows.forEach((row) => {
    const tr = document.createElement("tr");

    const imgUrl = `${API_BASE_URL}/images/${encodeURIComponent(row.image_name)}`;

    tr.innerHTML = `
      <td><img class="thumb" src="${imgUrl}" alt="${row.image_name}" loading="lazy"></td>
      <td class="mono-cell">${row.image_name}</td>
      <td class="mono-cell">${row.date}</td>
      <td class="mono-cell">${row.time}</td>
      <td><span class="loc-tag">${row.location}</span></td>
      <td><button class="btn-delete" title="Delete this entry">🗑</button></td>
    `;

    tr.querySelector(".thumb").addEventListener("click", () => openLightbox(imgUrl));
    tr.querySelector(".btn-delete").addEventListener("click", () => deleteViolator(row.id, row.image_name));
    logTableBody.appendChild(tr);
  });
}

async function deleteViolator(id, imageName) {
  const confirmed = confirm(`Delete this entry (${imageName})? This removes it from the log and deletes the saved image. This can't be undone.`);
  if (!confirmed) return;

  try {
    const res = await fetch(`${API_BASE_URL}/violators/${id}`, { method: "DELETE" });
    const data = await res.json();
    if (data.status === "error") {
      alert(`Could not delete: ${data.message}`);
      return;
    }
    loadViolators();
  } catch (err) {
    alert("Could not reach the backend to delete this entry.");
  }
}

function checkForNewViolation(rows) {
  if (rows.length === 0) return;
  const newestId = rows[0].id;

  if (lastKnownEntryId !== null && newestId !== lastKnownEntryId) {
    flashViolationAlert(rows[0]);
  }
  lastKnownEntryId = newestId;
}

function flashViolationAlert(row) {
  alertBanner.classList.add("violation");
  alertText.textContent = `Violation detected — ${row.image_name} @ ${row.time} (${row.location})`;
  viewport.classList.add("alert");

  setTimeout(() => {
    alertBanner.classList.remove("violation");
    alertText.textContent = "Monitoring for violations…";
    viewport.classList.remove("alert");
  }, 4000);
}

// ---------------------------------------------------------------------------
// Lightbox
// ---------------------------------------------------------------------------
function openLightbox(src) {
  lightboxImg.src = src;
  lightbox.classList.add("open");
}
function closeLightbox() {
  lightbox.classList.remove("open");
  lightboxImg.src = "";
}
lightboxClose.addEventListener("click", closeLightbox);
lightbox.addEventListener("click", (e) => {
  if (e.target === lightbox) closeLightbox();
});

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------
async function init() {
  await pollStatus();
  await loadFilterOptions();
  await loadViolators();

  setInterval(pollStatus, 4000);
  setInterval(loadViolators, 5000);
}

init();
