(() => {
  const KEY = "db_hospital_demo_state_v2";
  const DEMO_STREAM_URL = `${window.location.protocol}//${window.location.hostname}:8000/demo-stream`;

  function load() {
    try {
      return JSON.parse(localStorage.getItem(KEY) || "{}") || {};
    } catch {
      return {};
    }
  }

  function save(state) {
    localStorage.setItem(KEY, JSON.stringify(state));
  }

  function genId() {
    return "VC-2026-" + Math.floor(100000 + Math.random() * 900000);
  }

  function renderTable() {
    const state = load();
    const rows = Array.isArray(state.appts) ? state.appts : [];
    const body = document.getElementById("appt-body");
    if (!body) return;
    body.innerHTML = "";
    for (const a of rows.slice(0, 8)) {
      const tr = document.createElement("tr");
      const cls = a.status === "Confirmed" ? "ok" : "warn";
      tr.innerHTML = `<td>${a.date}</td><td>Dr. ${a.doctor}</td><td>${a.type}</td><td><span class="pill ${cls}">${a.status}</span></td><td>${a.conf}</td>`;
      body.appendChild(tr);
    }
  }

  function doLogin() {
    const login = document.getElementById("login-panel");
    const portal = document.getElementById("portal-panel");
    if (login) login.style.display = "none";
    if (portal) portal.style.display = "block";
    renderTable();
  }

  function submitAppointment() {
    const doctor = (document.getElementById("doctor-input")?.value || "").trim().toLowerCase();
    const date = (document.getElementById("date-input")?.value || "").trim();
    if (!doctor || !date) {
      alert("Please provide doctor and preferred date.");
      return;
    }

    const conf = genId();
    const state = load();
    const appts = Array.isArray(state.appts) ? state.appts : [];
    appts.unshift({ conf, doctor: doctor.charAt(0).toUpperCase() + doctor.slice(1), date, type: "New Appointment", status: "Pending Confirmation", at: new Date().toISOString() });
    save({ appts: appts.slice(0, 10) });

    const params = new URLSearchParams({ conf, doctor, date, at: new Date().toISOString() });
    window.location.href = "success.html?" + params.toString();
  }

  function initSuccess() {
    const p = new URLSearchParams(window.location.search);
    const conf = p.get("conf") || genId();
    const doctor = p.get("doctor") || "smith";
    const date = p.get("date") || "";
    const at = p.get("at") || new Date().toISOString();

    document.getElementById("conf-num").textContent = conf;
    document.getElementById("doc-display").textContent = "Dr. " + doctor.charAt(0).toUpperCase() + doctor.slice(1) + ", MD";
    if (date) {
      const d = new Date(date + "T12:00:00");
      document.getElementById("date-display").textContent = d.toLocaleDateString("en-US", { weekday: "long", year: "numeric", month: "long", day: "numeric" });
    }
    document.getElementById("submitted-time").textContent = new Date(at).toLocaleString("en-US");
  }

  function connectRealtimeDemo() {
    try {
      const source = new EventSource(DEMO_STREAM_URL);
      source.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type !== "demo_step") return;
        if (data.portal !== "hospital") return;

        const step = (data.step || "").toLowerCase();
        const detail = String(data.detail || "");

        if (step.includes("filling doctor")) {
          const input = document.getElementById("doctor-input");
          if (input) input.value = detail;
        }
        if (step.includes("filling date")) {
          const input = document.getElementById("date-input");
          if (input) input.value = detail;
        }
        if (step.includes("clicking sign in")) {
          if (document.getElementById("login-panel")?.style.display !== "none") {
            doLogin();
          }
        }
        if (step.includes("clicking submit request")) {
          const onSuccessPage = window.location.pathname.endsWith("/success.html");
          if (!onSuccessPage) submitAppointment();
        }
      };
    } catch {
      // Realtime visualization is optional for manual browsing.
    }
  }

  window.doLogin = doLogin;
  window.submitAppointment = submitAppointment;
  window.hospitalPortalApp = { initSuccess };
  connectRealtimeDemo();
})();
