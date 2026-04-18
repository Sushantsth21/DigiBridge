# ──────────────────────────────────────────────
# Digital Bridge  —  Dockerfile
# Target: Vultr Cloud Compute (Ubuntu 22.04)
# Playwright Chromium + FastAPI + Uvicorn
# ──────────────────────────────────────────────

FROM python:3.11-slim-bookworm

# ── System deps for Playwright Chromium ───────
# These are the libraries Chromium needs on a headless Linux VPS.
# Installing them explicitly prevents "missing shared lib" crashes on Vultr.
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Chromium runtime
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libdbus-1-3 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 \
    libpango-1.0-0 libcairo2 libatspi2.0-0 libx11-6 libx11-xcb1 \
    libxcb1 libxext6 libxcursor1 libxi6 libxtst6 \
    # Font support (renders pages correctly)
    fonts-liberation fonts-noto-color-emoji \
    # Utility
    curl ca-certificates \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Python deps ───────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Install Playwright + Chromium only ────────
# --with-deps is intentionally skipped here because we installed
# all deps manually above (gives us full control on Vultr).
RUN python -m playwright install chromium

# ── Copy source ───────────────────────────────
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# ── Expose port ───────────────────────────────
EXPOSE 8000

# ── Run ───────────────────────────────────────
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
