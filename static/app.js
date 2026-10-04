const elements = {
  connection: document.querySelector("#connection-state"),
  dot: document.querySelector("#status-dot"),
  video: document.querySelector("#video-feed"),
  empty: document.querySelector("#empty-state"),
  errorBox: document.querySelector("#error-box"),
  errorMessage: document.querySelector("#error-message"),
};

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

async function refreshStatus() {
  try {
    const response = await fetch("/api/status", { cache: "no-store" });
    if (!response.ok) throw new Error("Status unavailable");
    const status = await response.json();
    elements.connection.textContent = status.running ? "CONNECTED" : "RECONNECTING";
    elements.dot.classList.toggle("is-online", status.running);
    setText("#runtime-state", status.paused ? "PAUSED" : status.ended ? "ENDED" : status.running ? "PROCESSING" : "INITIALIZING");
    setText("#target-count", status.targets);
    setText("#candidate-count", status.candidates);
    setText("#crop-check-count", status.candidate_checks || 0);
    setText("#video-fps", Number(status.video_fps || 0).toFixed(1));
    setText("#ai-fps", Number(status.ai_fps || 0).toFixed(1));
    setText("#model-name", status.model || "—");
    setText("#frame-label", `FRAME ${String(Math.max(0, status.frame_index)).padStart(6, "0")}`);
    setText("#feed-resolution", status.frame_index >= 0 ? "LIVE / MJPEG" : "WAITING FOR VIDEO");
    document.querySelector("#target-bar").style.width = `${Math.min(Number(status.targets) * 13, 100)}%`;
    document.querySelector("#ai-toggle").checked = Boolean(status.ai_enabled);
    document.querySelector("#candidates-toggle").checked = Boolean(status.show_candidates);
    document.querySelector("#confidence-toggle").checked = Boolean(status.show_confidence);
    document.querySelector("#ids-toggle").checked = Boolean(status.show_ids);
    elements.errorBox.hidden = !status.error;
    elements.errorMessage.textContent = status.error || "";
    elements.empty.classList.toggle("is-hidden", status.frame_index >= 0);
  } catch {
    elements.connection.textContent = "OFFLINE";
    elements.dot.classList.remove("is-online");
  }
}

document.querySelector("#start-button").addEventListener("click", () => sendAction("start").catch(showError));
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

function updateClock() {
  setText("#clock", new Intl.DateTimeFormat("uk-UA", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(new Date()));
}

updateClock();
refreshStatus();
window.setInterval(updateClock, 1000);
window.setInterval(refreshStatus, 900);