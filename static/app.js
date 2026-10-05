const elements = {
  connection: document.querySelector("#connection-state"),
  dot: document.querySelector("#status-dot"),
  video: document.querySelector("#video-feed"),
  browserVideo: document.querySelector("#browser-camera"),
  browserOverlay: document.querySelector("#browser-overlay"),
  cameraSelect: document.querySelector("#browser-camera-select"),
  empty: document.querySelector("#empty-state"),
  errorBox: document.querySelector("#error-box"),
  errorMessage: document.querySelector("#error-message"),
};

const uploadCanvas = document.createElement("canvas");
let browserStream = null;
let browserCameraStarting = null;
let browserCameraBlocked = false;
let currentStatus = null;
let overlayBoxes = [];
let overlayStates = new Map();
let overlayVersion = -1;
let overlayOptions = { show_candidates: true, show_confidence: true, show_ids: true };
let overlayFetchInProgress = false;
let frameUploadInProgress = false;
let lastFrameUploadAt = 0;
let cameraFpsFrames = 0;
let cameraFpsStartedAt = 0;
let mjpegFeedActive = false;

async function sendAction(action, payload = {}) {
  const response = await fetch(`/api/control/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(`Control request failed (${response.status})`);
  return response.json();
}

function setText(selector, value) {
  document.querySelector(selector).textContent = value;
}

function stopBrowserCamera() {
  if (browserStream) {
    for (const track of browserStream.getTracks()) track.stop();
    browserStream = null;
  }
  elements.browserVideo.pause();
  elements.browserVideo.srcObject = null;
  elements.browserVideo.hidden = true;
  elements.browserOverlay.hidden = true;
  elements.video.hidden = false;
  cameraFpsFrames = 0;
  cameraFpsStartedAt = 0;
  frameUploadInProgress = false;
  overlayStates.clear();
  overlayVersion = -1;
}

function startMjpegFeed() {
  elements.video.hidden = false;
  elements.browserVideo.hidden = true;
  elements.browserOverlay.hidden = true;
  if (!mjpegFeedActive) {
    elements.video.src = "/video_feed";
    mjpegFeedActive = true;
  }
}

function stopMjpegFeed() {
  if (mjpegFeedActive) {
    elements.video.removeAttribute("src");
    mjpegFeedActive = false;
  }
  elements.video.hidden = true;
}

async function loadBrowserCameras() {
  if (!navigator.mediaDevices?.enumerateDevices) return;
  const selectedDevice = elements.cameraSelect.value;
  const devices = await navigator.mediaDevices.enumerateDevices();
  elements.cameraSelect.replaceChildren(new Option("Default camera", ""));
  const cameras = devices.filter((device) => device.kind === "videoinput");
  cameras.forEach((device, index) => {
    elements.cameraSelect.add(new Option(device.label || `Camera ${index}`, device.deviceId));
  });
  if ([...elements.cameraSelect.options].some((option) => option.value === selectedDevice)) {
    elements.cameraSelect.value = selectedDevice;
  }
}

async function startBrowserCamera(status) {
  if (browserStream || browserCameraStarting || browserCameraBlocked) return;
  browserCameraStarting = (async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error("Browser camera access is unavailable. Open the dashboard on localhost.");
    }
    const width = status.camera_width || 1280;
    const height = status.camera_height || 720;
    const video = {
      width: { ideal: width },
      height: { ideal: height },
      frameRate: { ideal: 30, max: 60 },
    };
    if (elements.cameraSelect.value) video.deviceId = { exact: elements.cameraSelect.value };
    browserStream = await navigator.mediaDevices.getUserMedia({ audio: false, video });
    elements.browserVideo.srcObject = browserStream;
    await elements.browserVideo.play();
    elements.video.hidden = true;
    elements.browserVideo.hidden = false;
    elements.browserOverlay.hidden = false;
    elements.empty.classList.add("is-hidden");
    await loadBrowserCameras();
    elements.browserVideo.requestVideoFrameCallback(onBrowserVideoFrame);
  })();

  try {
    await browserCameraStarting;
  } catch (error) {
    stopBrowserCamera();
    browserCameraBlocked = true;
    showError(new Error(`Camera: ${error.message}`));
  } finally {
    browserCameraStarting = null;
  }
}

function overlayKey(item) {
  if (item.track_id != null) return `track:${item.track_id}`;
  const [left, top, right, bottom] = item.box;
  return `candidate:${item.class}:${Math.round((left + right) / 48)}:${Math.round((top + bottom) / 48)}`;
}

function getOverlayBox(state, now) {
  const elapsed = Math.max(0, now - state.transitionStartedAt);
  const progress = state.transitionDuration ? Math.min(elapsed / state.transitionDuration, 1) : 1;
  const easedProgress = progress * progress * (3 - 2 * progress);
  const predictionSeconds = Math.min(Math.max(elapsed - state.transitionDuration, 0), 80) / 1000;
  return state.startBox.map((value, index) =>
    value + (state.targetBox[index] - value) * easedProgress + state.velocity[index] * predictionSeconds,
  );
}

function updateOverlay(snapshot) {
  if (snapshot.version === overlayVersion && (snapshot.boxes?.length || overlayStates.size === 0)) return;
  const receivedAt = performance.now();
  const nextStates = new Map();
  overlayBoxes = snapshot.boxes || [];
  overlayOptions = snapshot;

  for (const item of overlayBoxes) {
    const key = overlayKey(item);
    const measuredBox = item.box.map(Number);
    const previous = overlayStates.get(key);
    let startBox = measuredBox;
    let targetBox = measuredBox;
    let velocity = [0, 0, 0, 0];
    let transitionDuration = 0;
    if (previous) {
      const elapsed = (receivedAt - previous.updatedAt) / 1000;
      if (elapsed > 0 && elapsed < 1) {
        startBox = getOverlayBox(previous, receivedAt);
        velocity = measuredBox.map((value, index) => {
          const measuredVelocity = (value - previous.measuredBox[index]) / elapsed;
          return previous.velocity[index] * 0.5 + measuredVelocity * 0.5;
        });
        targetBox = measuredBox.map((value, index) => value + velocity[index] * 0.04);
        transitionDuration = Math.min(120, Math.max(50, elapsed * 650));
      }
    }
    nextStates.set(key, {
      item,
      measuredBox,
      startBox,
      targetBox,
      velocity,
      transitionStartedAt: receivedAt,
      transitionDuration,
      updatedAt: receivedAt,
    });
  }

  overlayStates = nextStates;
  overlayVersion = snapshot.version;
}

function drawBrowserOverlay(now = performance.now()) {
  const video = elements.browserVideo;
  const canvas = elements.browserOverlay;
  if (!video.videoWidth || !video.videoHeight) return;
  if (canvas.width !== video.videoWidth || canvas.height !== video.videoHeight) {
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
  }
  const context = canvas.getContext("2d");
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.lineWidth = Math.max(2, canvas.width / 640);
  context.font = `${Math.max(14, canvas.width / 48)}px "IBM Plex Mono", monospace`;

  for (const state of overlayStates.values()) {
    const item = state.item;
    if (item.candidate_type && !overlayOptions.show_candidates) continue;
    const [rawX1, rawY1, rawX2, rawY2] = getOverlayBox(state, now);
    const x1 = Math.max(0, Math.min(canvas.width - 1, rawX1));
    const y1 = Math.max(0, Math.min(canvas.height - 1, rawY1));
    const x2 = Math.max(x1, Math.min(canvas.width, rawX2));
    const y2 = Math.max(y1, Math.min(canvas.height, rawY2));
    const color = item.candidate_type === "weak" ? "#f5b54b" : item.candidate_type ? "#58a8ff" : "#68d38b";
    context.strokeStyle = color;
    context.strokeRect(x1, y1, x2 - x1, y2 - y1);
    const label = [item.class, item.candidate_type?.toUpperCase(), overlayOptions.show_ids && item.track_id != null ? `#${item.track_id}` : null, overlayOptions.show_confidence ? `${item.confidence.toFixed(2)}` : null].filter(Boolean).join(" ");
    context.fillStyle = color;
    context.fillText(label, x1, Math.max(18, y1 - 6));
  }
  context.fillStyle = "#ffffff";
  context.fillText(`LIVE ${Number(document.querySelector("#video-fps").textContent).toFixed(0)} FPS  /  AI ${Number(currentStatus?.ai_fps || 0).toFixed(1)} FPS`, 12, 22);
}

function onBrowserVideoFrame(now) {
  if (!browserStream) return;
  cameraFpsFrames += 1;
  if (!cameraFpsStartedAt) cameraFpsStartedAt = now;
  const elapsed = now - cameraFpsStartedAt;
  if (elapsed >= 1000) {
    setText("#video-fps", (cameraFpsFrames * 1000 / elapsed).toFixed(1));
    cameraFpsFrames = 0;
    cameraFpsStartedAt = now;
  }

  drawBrowserOverlay(now);
  const uploadRate = Math.max(1, Number(currentStatus?.camera_ai_fps || 5));
  if (currentStatus?.ai_enabled && !currentStatus.paused && !frameUploadInProgress && now - lastFrameUploadAt >= 1000 / uploadRate) {
    const video = elements.browserVideo;
    uploadCanvas.width = video.videoWidth;
    uploadCanvas.height = video.videoHeight;
    uploadCanvas.getContext("2d").drawImage(video, 0, 0, uploadCanvas.width, uploadCanvas.height);
    frameUploadInProgress = true;
    lastFrameUploadAt = now;
    uploadCanvas.toBlob(async (blob) => {
      try {
        if (blob) {
          const response = await fetch("/api/browser-frame", {
            method: "POST",
            headers: { "Content-Type": "image/jpeg" },
            body: blob,
          });
          if (!response.ok && response.status !== 409) throw new Error(`Camera upload failed (${response.status})`);
        }
      } catch (error) {
        showError(error);
      } finally {
        frameUploadInProgress = false;
      }
    }, "image/jpeg", 0.78);
  }
  elements.browserVideo.requestVideoFrameCallback(onBrowserVideoFrame);
}

async function refreshStatus() {
  try {
    const response = await fetch("/api/status", { cache: "no-store" });
    if (!response.ok) throw new Error("Status unavailable");
    const status = await response.json();
    currentStatus = status;
    elements.connection.textContent = status.running ? "CONNECTED" : "RECONNECTING";
    elements.dot.classList.toggle("is-online", status.running);
    setText("#runtime-state", status.paused ? "PAUSED" : status.ended ? "ENDED" : status.running ? "PROCESSING" : "INITIALIZING");
    setText("#target-count", status.targets);
    setText("#candidate-count", status.candidates);
    setText("#crop-check-count", status.candidate_checks || 0);
    if (status.source_type !== "webcam") setText("#video-fps", Number(status.video_fps || 0).toFixed(1));
    setText("#ai-fps", Number(status.ai_fps || 0).toFixed(1));
    setText("#model-name", status.model || "—");
    setText("#source-label", status.source_label || status.source_type || "—");
    const sourceHelp = {
      file: `Using ${status.source_label}. Restart to replay.`,
      webcam: `Waiting for ${status.source_label || "USB webcam"}.`,
      picamera2: "Waiting for Raspberry Pi CSI camera.",
    };
    setText("#source-help", sourceHelp[status.source_type] || "Waiting for video source.");
    setText("#frame-label", `FRAME ${String(Math.max(0, status.frame_index)).padStart(6, "0")}`);
    setText("#feed-resolution", status.frame_index >= 0
      ? `${status.source_width}×${status.source_height} / SOURCE ${Number(status.source_fps || 0).toFixed(0)} FPS`
      : "WAITING FOR VIDEO");
    document.querySelector("#target-bar").style.width = `${Math.min(Number(status.targets) * 13, 100)}%`;
    document.querySelector("#ai-toggle").checked = Boolean(status.ai_enabled);
    document.querySelector("#candidates-toggle").checked = Boolean(status.show_candidates);
    document.querySelector("#confidence-toggle").checked = Boolean(status.show_confidence);
    document.querySelector("#ids-toggle").checked = Boolean(status.show_ids);
    document.querySelector(".record-indicator").classList.toggle("is-idle", !status.recording);
    setText("#recording-label", status.recording ? "OUTPUT RECORDING" : "PREVIEW ONLY");
    elements.cameraSelect.hidden = status.source_type !== "webcam";
    if (status.source_type === "webcam") {
      stopMjpegFeed();
      elements.video.hidden = true;
      elements.browserOverlay.hidden = !browserStream;
      elements.browserVideo.hidden = !browserStream;
      if (!browserStream) void startBrowserCamera(status);
    } else {
      stopBrowserCamera();
      startMjpegFeed();
    }
    elements.errorBox.hidden = !status.error;
    elements.errorMessage.textContent = status.error || "";
    elements.empty.classList.toggle("is-hidden", status.frame_index >= 0);
  } catch {
    elements.connection.textContent = "OFFLINE";
    elements.dot.classList.remove("is-online");
  }
}

async function refreshOverlay() {
  if (!browserStream || currentStatus?.source_type !== "webcam" || overlayFetchInProgress) return;
  overlayFetchInProgress = true;
  try {
    const response = await fetch("/api/overlay", { cache: "no-store" });
    if (response.ok) updateOverlay(await response.json());
  } catch {
    // The regular status poll reports connection failures.
  } finally {
    overlayFetchInProgress = false;
  }
}

document.querySelector("#start-button").addEventListener("click", () => {
  sendAction("start").catch(showError);
  if (currentStatus?.source_type === "webcam") {
    browserCameraBlocked = false;
    void startBrowserCamera(currentStatus);
  }
});
document.querySelector("#pause-button").addEventListener("click", () => sendAction("pause").catch(showError));
document.querySelector("#restart-button").addEventListener("click", () => sendAction("restart").catch(showError));
document.querySelector("#ai-toggle").addEventListener("change", (event) => {
  sendAction("ai", { enabled: event.target.checked }).catch(showError);
});

for (const [id, key] of [["candidates-toggle", "show_candidates"], ["confidence-toggle", "show_confidence"], ["ids-toggle", "show_ids"]]) {
  document.querySelector(`#${id}`).addEventListener("change", (event) => {
    sendAction("overlay", { [key]: event.target.checked }).catch(showError);
  });
}

function showError(error) {
  elements.errorBox.hidden = false;
  elements.errorMessage.textContent = error.message;
}

elements.video.addEventListener("load", () => elements.empty.classList.add("is-hidden"));
elements.video.addEventListener("error", () => elements.empty.classList.remove("is-hidden"));
elements.cameraSelect.addEventListener("change", async () => {
  stopBrowserCamera();
  browserCameraBlocked = false;
  await startBrowserCamera(currentStatus || {});
});

function updateClock() {
  setText("#clock", new Intl.DateTimeFormat("uk-UA", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(new Date()));
}

updateClock();
refreshStatus();
window.setInterval(updateClock, 1000);
window.setInterval(refreshStatus, 900);
window.setInterval(refreshOverlay, 100);