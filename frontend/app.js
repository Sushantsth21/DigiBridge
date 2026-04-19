/* ──────────────────────────────────────────────
   Digital Bridge  —  app.js  v2.0
   Features: #2 Live Status Ticker, #5 Multi-Portal, #6 Session Memory
────────────────────────────────────────────── */

// Covers: file://, localhost, 127.0.0.1 → point at dev backend.
// Non-local usage points to deployed server IP (supports both :80 and :8080 access patterns).
const DEPLOYED_HOST = "144.202.49.80";
const IS_LOCAL =
  window.location.protocol === "file:" ||
  window.location.hostname === "localhost" ||
  window.location.hostname === "127.0.0.1";

const API_BASE = IS_LOCAL
  ? "http://localhost:8000"
  : window.location.port === "8080"
    ? `http://${DEPLOYED_HOST}:8080`
    : `http://${DEPLOYED_HOST}`;

// ── DOM refs ──────────────────────────────────
const micBtn        = document.getElementById("mic-btn");
const micWrap       = document.getElementById("mic-wrap");
const micLabel      = document.getElementById("mic-label");
const transcriptBox = document.getElementById("transcript-box");
const statusTicker  = document.getElementById("status-ticker");
const resultCard    = document.getElementById("result-card");
const resultHeader  = document.getElementById("result-header");
const resultMessage = document.getElementById("result-message");
const resultImg     = document.getElementById("result-screenshot");
const ttsAudio      = document.getElementById("tts-audio");
const repeatBtn     = document.getElementById("repeat-btn");
const sessionDot    = document.getElementById("session-dot");
const sessionLabel  = document.getElementById("session-label");

// ── State ─────────────────────────────────────
let sessionId      = _getOrCreateSessionId();
let isProcessing   = false;
const FALLBACK_PORTAL = "hospital";

// ── Session ID (Feature #6) ───────────────────
function _getOrCreateSessionId() {
  let id = sessionStorage.getItem("db_session_id");
  if (!id) {
    id = "sess_" + Math.random().toString(36).slice(2, 10);
    sessionStorage.setItem("db_session_id", id);
  }
  return id;
}

// ── Check if session has a prior action ───────
async function checkSession() {
  try {
    const res = await fetch(`${API_BASE}/session/${sessionId}`);
    const data = await res.json();
    if (data.found) {
      sessionDot.classList.add("active");
      const action = data.last_action?.action || "action";
      const doctor = data.last_action?.doctor || data.last_action?.medication || "";
      sessionLabel.textContent = `Last: ${action}${doctor ? " — " + doctor : ""}`;
      repeatBtn.style.display = "block";
    } else {
      sessionLabel.textContent = "No session";
      repeatBtn.style.display = "none";
    }
  } catch (e) {
    console.warn("Session check failed:", e);
  }
}

// ── Speech Recognition ────────────────────────
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null;

if (!SpeechRecognition) {
  micLabel.textContent = "Voice not supported in this browser";
  micBtn.disabled = true;
} else {
  recognition = new SpeechRecognition();
  recognition.continuous = false;
  recognition.interimResults = true;
  recognition.lang = "en-US";

  recognition.onstart = () => {
    console.log("Recognition started");
    micBtn.classList.add("recording");
    micBtn.setAttribute("aria-pressed", "true");
    micWrap.classList.add("listening");
    micLabel.textContent = "Listening… speak now";
    transcriptBox.classList.remove("placeholder");
    transcriptBox.textContent = "";
    clearResults();
  };

  recognition.onresult = (event) => {
    let interim = "", final = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const t = event.results[i][0].transcript;
      event.results[i].isFinal ? (final += t) : (interim += t);
    }
    transcriptBox.textContent = final || interim;
  };

  recognition.onerror = (event) => {
    console.error("Speech error:", event.error);
    resetMic();
    showError(`Microphone error: ${event.error}. Please try again.`);
  };

  recognition.onend = () => {
    const text = transcriptBox.textContent.trim();
    resetMic();
    if (text && text.length > 2) {
      processVoice(text);
    } else {
      transcriptBox.textContent = "";
      transcriptBox.classList.add("placeholder");
      transcriptBox.textContent = "Your words will appear here…";
    }
  };
}

micBtn.addEventListener("click", () => {
  if (isProcessing) return;
  if (!recognition) return;
  try {
    recognition.start();
  } catch (e) {
    console.warn("Recognition already running");
  }
});

function resetMic() {
  micBtn.classList.remove("recording");
  micBtn.setAttribute("aria-pressed", "false");
  micWrap.classList.remove("listening");
  micLabel.textContent = "Press to speak";
}

// ── Repeat last action (Feature #6) ───────────
repeatBtn.addEventListener("click", () => {
  processVoice("same as last time", forceRepeat = true);
});

// ── Live Status Ticker (Feature #2) ───────────
let currentRequestId = null;
let sseSource = null;

function startStatusStream(requestId, attempt = 0) {
  currentRequestId = requestId;

  sseSource = new EventSource(`${API_BASE}/status-stream/${requestId}`);

  sseSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === "status") {
      addStatusStep(data.step, data.detail, "active");
    }
    if (data.type === "done") {
      document.querySelectorAll(".status-step.active").forEach(el => {
        el.classList.remove("active");
        el.classList.add("done");
        const spinner = el.querySelector(".spinner");
        if (spinner) spinner.replaceWith(Object.assign(document.createElement("span"), { textContent: "✓" }));
      });
      sseSource.close();
    }
    if (data.type === "timeout") { sseSource.close(); }
  };

  // 404 = POST hasn't created the queue yet; retry up to 5x
  sseSource.onerror = () => {
    sseSource.close();
    if (attempt < 5) {
      console.log(`SSE retry ${attempt + 1} for ${requestId}`);
      setTimeout(() => startStatusStream(requestId, attempt + 1), 200);
    } else {
      console.warn("SSE unavailable — status ticker disabled");
    }
  };
}

function addStatusStep(text, detail = "", state = "active") {
  const step = document.createElement("div");
  step.className = `status-step ${state}`;

  const spinner = document.createElement("div");
  spinner.className = "spinner";
  step.appendChild(spinner);

  const label = document.createElement("span");
  label.textContent = text + (detail ? ` (${detail})` : "");
  step.appendChild(label);

  statusTicker.appendChild(step);

  // Trigger animation
  requestAnimationFrame(() => {
    requestAnimationFrame(() => step.classList.add("visible"));
  });
}

// ── Main processing flow ───────────────────────
async function processVoice(transcript, forceRepeat = false) {
  if (isProcessing) return;
  isProcessing = true;
  micBtn.disabled = true;
  clearResults();

  addStatusStep("📡 Sending to Digital Bridge…", "", "active");

  // Generate requestId client-side — server will use this same ID for its SSE queue
  const requestId = "req_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);

  // Open SSE connection BEFORE the POST so we don't miss early events
  // Server creates the queue on POST arrival; SSE will retry until it exists
  startStatusStream(requestId);

  const payload = {
    transcript: forceRepeat ? "same as last time" : transcript,
    session_id: sessionId,
    // Backend can infer portal from intent; this is only a safe fallback.
    portal: FALLBACK_PORTAL,
  };

  try {
    const res = await fetch(`${API_BASE}/process-voice`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Request-ID": requestId,   // server reads this and keys its queue to it
      },
      body: JSON.stringify(payload),
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const data = await res.json();
    handleResponse(data);

  } catch (err) {
    console.error("API error:", err);
    showError("Could not reach the server. Please check your connection and that the backend is running on port 8000.");
  } finally {
    isProcessing = false;
    micBtn.disabled = false;
    checkSession();
  }
}

function handleResponse(data) {
  resultCard.style.display = "block";

  if (data.success) {
    resultCard.classList.remove("error");
    resultHeader.textContent = "✅ Done";
    resultMessage.textContent = data.message;

    // Show screenshot
    if (data.screenshot_b64) {
      resultImg.src = `data:image/png;base64,${data.screenshot_b64}`;
      resultImg.style.display = "block";
    }

    // Play ElevenLabs audio (Feature #2 / ElevenLabs)
    if (data.audio_b64) {
      const blob = _b64ToBlob(data.audio_b64, "audio/mpeg");
      const url = URL.createObjectURL(blob);
      ttsAudio.src = url;
      ttsAudio.play().catch(e => console.warn("Audio autoplay blocked:", e));
    }

    // Update session UI (Feature #6)
    sessionDot.classList.add("active");
    repeatBtn.style.display = "block";

  } else {
    resultCard.classList.add("error");
    resultHeader.textContent = "⚠️ Couldn't complete that";
    resultMessage.textContent = data.message;
    resultImg.style.display = "none";
  }

  resultCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function showError(msg) {
  resultCard.style.display = "block";
  resultCard.classList.add("error");
  resultHeader.textContent = "⚠️ Error";
  resultMessage.textContent = msg;
  resultImg.style.display = "none";
}

function clearResults() {
  resultCard.style.display = "none";
  resultCard.classList.remove("error");
  resultImg.style.display = "none";
  statusTicker.innerHTML = "";
  if (sseSource) { sseSource.close(); sseSource = null; }
}

// ── Utility ───────────────────────────────────
function _b64ToBlob(b64, mimeType) {
  const bytes = atob(b64);
  const arr = new Uint8Array(bytes.length);
  for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
  return new Blob([arr], { type: mimeType });
}

// ── Init ──────────────────────────────────────
checkSession();
console.log("Digital Bridge v2.0 ready | Session:", sessionId);