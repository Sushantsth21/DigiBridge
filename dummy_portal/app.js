(() => {
  const IS_LOCAL_HOST = ["localhost", "127.0.0.1"].includes(window.location.hostname);
  const STREAM_URL = `${window.location.protocol}//${window.location.hostname}${IS_LOCAL_HOST ? ":8000" : ""}/demo-stream`;
  const LOGIN_KEY = "db_unified_portal_logged_in";

  const qs = (id) => document.getElementById(id);

  function appendFeed(message, kind = "") {
    const feed = qs("demo-feed");
    if (!feed) return;
    const line = document.createElement("div");
    line.className = `feed-line ${kind}`.trim();
    line.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
    feed.prepend(line);
  }

  function setLoggedIn(loggedIn) {
    localStorage.setItem(LOGIN_KEY, loggedIn ? "1" : "0");
    const status = qs("session-status");
    if (status) {
      status.textContent = loggedIn ? "Login: Completed" : "Login: Not completed";
    }
  }

  function isLoggedIn() {
    return localStorage.getItem(LOGIN_KEY) === "1";
  }

  function ensureLogin() {
    if (isLoggedIn()) return true;
    alert("Hospital flow requires login first. Click 'Sign In'.");
    appendFeed("Hospital submit blocked: login required", "warn");
    return false;
  }

  function toSuccess(params) {
    window.location.href = `success.html?${new URLSearchParams(params).toString()}`;
  }

  function login() {
    setLoggedIn(true);
    appendFeed("Hospital login completed", "ok");
  }

  function submitHospital() {
    const doctor = (qs("doctor-input")?.value || "").trim().toLowerCase();
    const date = (qs("date-input")?.value || "").trim();
    if (!ensureLogin()) return;
    if (!doctor || !date) {
      alert("Please provide doctor and date.");
      return;
    }

    const conf = "HSP-" + Math.floor(100000 + Math.random() * 900000);
    appendFeed(`Hospital request submitted for Dr. ${doctor} on ${date}`, "ok");
    toSuccess({ type: "hospital", conf, doctor, date, at: new Date().toISOString() });
  }

  function submitPharmacy() {
    const medication = (qs("medication-input")?.value || "").trim();
    const quantity = Number((qs("quantity-input")?.value || "0").trim());
    if (!medication) {
      alert("Please provide medication.");
      return;
    }
    if (![30, 60, 90].includes(quantity)) {
      alert("Quantity must be 30, 60, or 90.");
      return;
    }

    const conf = "RXD-" + Math.floor(100000 + Math.random() * 900000);
    appendFeed(`Pharmacy refill submitted for ${medication} (${quantity}-day)`, "ok");
    toSuccess({ type: "pharmacy", conf, medication, quantity: String(quantity), at: new Date().toISOString() });
  }

  function submitUtility() {
    const amount = Number((qs("amount-input")?.value || "0").trim());
    const account = (qs("account-input")?.value || "").trim();
    const zip = (qs("zip-input")?.value || "").trim();

    if (!Number.isFinite(amount) || amount <= 0) {
      alert("Enter a valid amount.");
      return;
    }
    if (amount > 500) {
      alert("Maximum demo payment is $500.");
      return;
    }
    if (!account) {
      alert("Enter account number.");
      return;
    }
    if (!/^\d{5}$/.test(zip)) {
      alert("Billing ZIP must be 5 digits.");
      return;
    }

    const conf = "VPU-" + Math.floor(10000000 + Math.random() * 90000000);
    appendFeed(`Utility payment submitted: $${amount.toFixed(2)} (${account})`, "ok");
    toSuccess({ type: "utility", conf, amount: amount.toFixed(2), account, zip, at: new Date().toISOString() });
  }

  function connectStream() {
    try {
      const source = new EventSource(STREAM_URL);
      source.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type !== "demo_step") return;

        const step = String(data.step || "");
        const detail = String(data.detail || "");
        const portal = String(data.portal || "unknown");
        appendFeed(`${portal}: ${step}${detail ? ` (${detail})` : ""}`);

        const s = step.toLowerCase();
        if (s.includes("clicking sign in")) {
          login();
        }
        if (s.includes("filling doctor")) {
          const input = qs("doctor-input");
          if (input) input.value = detail;
        }
        if (s.includes("filling date")) {
          const input = qs("date-input");
          if (input) input.value = detail;
        }
        if (s.includes("clicking submit request")) {
          if (!window.location.pathname.endsWith("/success.html")) submitHospital();
        }
        if (s.includes("filling medication")) {
          const input = qs("medication-input");
          if (input) input.value = detail;
        }
        if (s.includes("filling days supply")) {
          const input = qs("quantity-input");
          if (input) input.value = detail;
        }
        if (s.includes("clicking submit refill")) {
          if (!window.location.pathname.endsWith("/success.html")) submitPharmacy();
        }
        if (s.includes("filling amount")) {
          const input = qs("amount-input");
          if (input) input.value = detail;
        }
        if (s.includes("clicking submit payment")) {
          if (!window.location.pathname.endsWith("/success.html")) submitUtility();
        }
      };
    } catch {
      appendFeed("Realtime stream unavailable", "warn");
    }
  }

  function clearFeed() {
    const feed = qs("demo-feed");
    if (feed) feed.innerHTML = "";
  }

  setLoggedIn(isLoggedIn());
  appendFeed("Unified portal ready");
  connectStream();

  window.unifiedPortal = {
    login,
    submitHospital,
    submitPharmacy,
    submitUtility,
    clearFeed,
  };
})();
