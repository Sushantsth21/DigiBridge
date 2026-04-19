(() => {
  const IS_LOCAL_HOST = ["localhost", "127.0.0.1"].includes(window.location.hostname);
  const DEMO_STREAM_URL = `${window.location.protocol}//${window.location.hostname}${IS_LOCAL_HOST ? ":8000" : ""}/demo-stream`;

  const CURRENCY = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  });

  const STORAGE_KEY = "db_utility_portal_state_v1";

  const DEFAULT_STATE = {
    account: {
      accountNumber: "VPU-441-8820",
      customerName: "Jordan Miles",
      serviceAddress: "123 Main St, Valleyport, KY 41001",
      dueDate: "2026-05-05",
      currentBalance: 142.5,
      autopayEnabled: false,
    },
    payments: [
      {
        id: "VPU-2026-55510422",
        amount: 138.2,
        fee: 1.95,
        method: "Card",
        status: "Approved",
        timestamp: "2026-04-03T10:21:00",
      },
      {
        id: "VPU-2026-55476103",
        amount: 131.8,
        fee: 0,
        method: "ACH",
        status: "Approved",
        timestamp: "2026-03-05T09:48:00",
      },
    ],
  };

  function loadState() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) {
        return structuredClone(DEFAULT_STATE);
      }
      const parsed = JSON.parse(raw);
      return {
        account: { ...DEFAULT_STATE.account, ...(parsed.account || {}) },
        payments: Array.isArray(parsed.payments) ? parsed.payments : [...DEFAULT_STATE.payments],
      };
    } catch {
      return structuredClone(DEFAULT_STATE);
    }
  }

  function saveState(state) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }

  function qs(id) {
    return document.getElementById(id);
  }

  function genConfNumber() {
    return "VPU-2026-" + Math.floor(10000000 + Math.random() * 90000000);
  }

  function maskCard(cardNumber) {
    const digits = (cardNumber || "").replace(/\D/g, "");
    return digits.slice(-4) || "0000";
  }

  function nowIso() {
    return new Date().toISOString();
  }

  function renderSummary(state) {
    qs("sum-account").textContent = state.account.accountNumber;
    qs("sum-balance").textContent = CURRENCY.format(state.account.currentBalance);
    qs("sum-due").textContent = new Date(state.account.dueDate + "T12:00:00").toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });

    const paidThisCycle = state.payments
      .filter((p) => p.timestamp.startsWith("2026-04") && p.status === "Approved")
      .reduce((acc, p) => acc + Number(p.amount || 0), 0);
    qs("sum-paid-cycle").textContent = CURRENCY.format(paidThisCycle);

    qs("amount-input").value = state.account.currentBalance.toFixed(2);
    qs("account-input").value = state.account.accountNumber;
    qs("customer-name").textContent = state.account.customerName;
    qs("service-address").textContent = state.account.serviceAddress;
  }

  function renderHistory(state) {
    const body = qs("payments-body");
    body.innerHTML = "";

    for (const p of state.payments.slice().sort((a, b) => (a.timestamp < b.timestamp ? 1 : -1))) {
      const tr = document.createElement("tr");
      tr.innerHTML = [
        `<td>${new Date(p.timestamp).toLocaleString("en-US")}</td>`,
        `<td>${p.id}</td>`,
        `<td>${CURRENCY.format(p.amount)}</td>`,
        `<td>${CURRENCY.format(p.fee || 0)}</td>`,
        `<td>${p.method}</td>`,
        `<td><span class="status-pill ok">${p.status}</span></td>`,
      ].join("");
      body.appendChild(tr);
    }
  }

  function renderTotals() {
    const amount = parseFloat(qs("amount-input").value || "0");
    const method = document.querySelector("input[name='pay-method']:checked")?.value || "card";
    const fee = method === "card" ? 1.95 : 0;
    qs("fee-preview").textContent = CURRENCY.format(fee);
    qs("total-preview").textContent = CURRENCY.format(Math.max(0, amount) + fee);
  }

  function validateForm(state) {
    const amount = parseFloat(qs("amount-input").value || "0");
    const zip = qs("zip-input").value.trim();
    const account = qs("account-input").value.trim();
    const accepted = qs("terms-input").checked;
    const method = document.querySelector("input[name='pay-method']:checked")?.value || "card";

    if (!Number.isFinite(amount) || amount <= 0) {
      return "Enter a valid payment amount.";
    }
    if (amount > 500) {
      return "For demo safety, max payment is $500 per transaction.";
    }
    if (account !== state.account.accountNumber) {
      return "Account number does not match the active account.";
    }
    if (!/^\d{5}$/.test(zip)) {
      return "Enter a valid 5-digit billing ZIP.";
    }
    if (!accepted) {
      return "You must accept the payment terms.";
    }

    if (method === "card") {
      const card = qs("card-number").value.replace(/\D/g, "");
      const exp = qs("card-exp").value.trim();
      const cvv = qs("card-cvv").value.replace(/\D/g, "");
      if (card.length < 15) return "Card number looks incomplete.";
      if (!/^\d{2}\/\d{2}$/.test(exp)) return "Expiration must be in MM/YY format.";
      if (cvv.length < 3) return "CVV is required.";
    }

    return "";
  }

  function showToast(msg, kind = "ok") {
    const el = qs("toast");
    el.textContent = msg;
    el.className = `toast show ${kind}`;
    setTimeout(() => {
      el.className = "toast";
    }, 2400);
  }

  function setProcessing(isProcessing) {
    qs("pay-btn").disabled = isProcessing;
    qs("processing-overlay").style.display = isProcessing ? "flex" : "none";
  }

  function bind(state) {
    qs("reset-state").addEventListener("click", () => {
      localStorage.removeItem(STORAGE_KEY);
      window.location.reload();
    });

    for (const btn of document.querySelectorAll("[data-quick-amount]")) {
      btn.addEventListener("click", () => {
        const v = btn.getAttribute("data-quick-amount") || "0";
        qs("amount-input").value = v;
        renderTotals();
      });
    }

    for (const radio of document.querySelectorAll("input[name='pay-method']")) {
      radio.addEventListener("change", () => {
        const cardFields = qs("card-fields");
        cardFields.style.display = radio.value === "card" ? "grid" : "none";
        renderTotals();
      });
    }

    qs("amount-input").addEventListener("input", renderTotals);

    qs("pay-btn").addEventListener("click", () => {
      const error = validateForm(state);
      if (error) {
        showToast(error, "error");
        return;
      }

      const method = document.querySelector("input[name='pay-method']:checked")?.value || "card";
      const amount = parseFloat(qs("amount-input").value || "0");
      const fee = method === "card" ? 1.95 : 0;
      const cardLast4 = maskCard(qs("card-number").value);

      const payment = {
        id: genConfNumber(),
        amount,
        fee,
        method: method === "card" ? "Card" : "ACH",
        cardLast4,
        status: "Approved",
        timestamp: nowIso(),
      };

      setProcessing(true);
      setTimeout(() => {
        state.payments.unshift(payment);
        state.account.currentBalance = Math.max(0, state.account.currentBalance - amount);
        saveState(state);

        const p = new URLSearchParams({
          amount: amount.toFixed(2),
          fee: fee.toFixed(2),
          total: (amount + fee).toFixed(2),
          conf: payment.id,
          method: payment.method,
          last4: payment.cardLast4,
          account: state.account.accountNumber,
          balance: state.account.currentBalance.toFixed(2),
          at: payment.timestamp,
        });

        window.location.href = "success.html?" + p.toString();
      }, 1400);
    });
  }

  function initPortal() {
    const state = loadState();
    renderSummary(state);
    renderHistory(state);
    renderTotals();
    bind(state);
  }

  function initSuccess() {
    const p = new URLSearchParams(window.location.search);
    const state = loadState();

    qs("receipt-conf").textContent = p.get("conf") || genConfNumber();
    qs("receipt-amount").textContent = CURRENCY.format(Number(p.get("amount") || 0));
    qs("receipt-fee").textContent = CURRENCY.format(Number(p.get("fee") || 0));
    qs("receipt-total").textContent = CURRENCY.format(Number(p.get("total") || 0));
    qs("receipt-account").textContent = p.get("account") || state.account.accountNumber;
    qs("receipt-method").textContent = `${p.get("method") || "Card"} ending in ${p.get("last4") || "0000"}`;
    qs("receipt-remaining").textContent = CURRENCY.format(Number(p.get("balance") || state.account.currentBalance));

    const at = p.get("at") || new Date().toISOString();
    qs("receipt-time").textContent = new Date(at).toLocaleString("en-US");

    const row = qs("recent-row");
    const last = state.payments[0];
    if (last) {
      row.innerHTML = [
        `<td>${last.id}</td>`,
        `<td>${new Date(last.timestamp).toLocaleString("en-US")}</td>`,
        `<td>${CURRENCY.format(last.amount)}</td>`,
        `<td>${last.method}</td>`,
      ].join("");
    }
  }

  function connectRealtimeDemo() {
    try {
      const source = new EventSource(DEMO_STREAM_URL);
      source.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type !== "demo_step") return;
        if (data.portal !== "utility") return;

        const step = (data.step || "").toLowerCase();
        const detail = String(data.detail || "");

        if (step.includes("filling amount")) {
          const amountInput = qs("amount-input");
          if (amountInput) {
            amountInput.value = detail;
            amountInput.dispatchEvent(new Event("input", { bubbles: true }));
          }
        }

        if (step.includes("clicking submit payment")) {
          const onSuccessPage = window.location.pathname.endsWith("/success.html");
          if (!onSuccessPage) qs("pay-btn")?.click();
        }
      };
    } catch {
      // Realtime visualization is optional for manual browsing.
    }
  }

  window.utilityPortalApp = {
    initPortal,
    initSuccess,
  };

  connectRealtimeDemo();
})();
