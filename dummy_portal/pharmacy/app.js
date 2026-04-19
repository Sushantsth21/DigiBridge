(() => {
  const KEY = "db_pharmacy_demo_state_v2";
  const IS_LOCAL_HOST = ["localhost", "127.0.0.1"].includes(window.location.hostname);
  const DEMO_STREAM_URL = `${window.location.protocol}//${window.location.hostname}${IS_LOCAL_HOST ? ":8000" : ""}/demo-stream`;

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
    return "RXD-" + Math.floor(100000 + Math.random() * 900000);
  }

  function etaDate(days = 7) {
    const d = new Date();
    d.setDate(d.getDate() + days);
    return d.toISOString().slice(0, 10);
  }

  function renderTable() {
    const state = load();
    const rows = Array.isArray(state.refills) ? state.refills : [];
    const body = document.getElementById("refill-body");
    if (!body) return;
    body.innerHTML = "";
    for (const r of rows.slice(0, 10)) {
      const cls = r.status === "Shipped" ? "ok" : "warn";
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${r.conf}</td><td>${r.medication}</td><td>${r.quantity}-day</td><td><span class="pill ${cls}">${r.status}</span></td><td>${r.eta}</td>`;
      body.appendChild(tr);
    }
  }

  function submitRefill() {
    const med = (document.getElementById("medication-input")?.value || "").trim();
    const qty = Number((document.getElementById("quantity-input")?.value || "0").trim());
    if (!med) {
      alert("Please enter a medication name.");
      return;
    }
    if (![30, 60, 90].includes(qty)) {
      alert("Days supply must be 30, 60, or 90.");
      return;
    }

    const conf = genId();
    const eta = etaDate(7);
    const state = load();
    const refills = Array.isArray(state.refills) ? state.refills : [];
    refills.unshift({ conf, medication: med, quantity: qty, status: "Processing", eta, at: new Date().toISOString() });
    save({ refills: refills.slice(0, 10) });

    const params = new URLSearchParams({ conf, medication: med, quantity: String(qty), eta, at: new Date().toISOString() });
    window.location.href = "success.html?" + params.toString();
  }

  function initSuccess() {
    const p = new URLSearchParams(window.location.search);
    document.getElementById("conf-num").textContent = p.get("conf") || genId();
    const med = p.get("medication") || "medication";
    document.getElementById("med-display").textContent = med.charAt(0).toUpperCase() + med.slice(1) + " - as prescribed";
    document.getElementById("qty-display").textContent = (p.get("quantity") || "90") + "-day supply";
    document.getElementById("delivery-date").textContent = p.get("eta") || etaDate(7);
    document.getElementById("submitted-time").textContent = new Date(p.get("at") || new Date().toISOString()).toLocaleString("en-US");
  }

  function connectRealtimeDemo() {
    try {
      const source = new EventSource(DEMO_STREAM_URL);
      source.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type !== "demo_step") return;
        if (data.portal !== "pharmacy") return;

        const step = (data.step || "").toLowerCase();
        const detail = String(data.detail || "");

        if (step.includes("filling medication")) {
          const input = document.getElementById("medication-input");
          if (input) input.value = detail;
        }
        if (step.includes("filling days supply")) {
          const input = document.getElementById("quantity-input");
          if (input) input.value = detail;
        }
        if (step.includes("clicking submit refill")) {
          const onSuccessPage = window.location.pathname.endsWith("/success.html");
          if (!onSuccessPage) submitRefill();
        }
      };
    } catch {
      // Realtime visualization is optional for manual browsing.
    }
  }

  renderTable();
  window.submitRefill = submitRefill;
  window.pharmacyPortalApp = { initSuccess };
  connectRealtimeDemo();
})();
