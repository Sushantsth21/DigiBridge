# DigiBridge

Voice-driven portal automation with FastAPI + Playwright.

## Run with Dummy Portals (default)

1. Start services:

```bash
docker compose up --build
```

2. Open frontend:

- Backend API: http://localhost:8000
- Dummy portals: http://localhost:8080

The backend uses dummy portal defaults out of the box.

## Run Against Real Websites

DigiBridge supports real website automation via configurable per-portal URLs and CSS selectors.

### 1. Create a site profile

Copy the example profile and edit it for your real websites:

```bash
cp backend/portal_sites.example.json backend/portal_sites.json
```

Update each portal entry:

- `urls`: one or more target page URLs (first reachable URL is used)
- `selectors`: CSS selectors for inputs/buttons
- `success_url_pattern`: Playwright URL glob used after submit

### 2. Mount profile path into backend

Set this environment variable for the backend service:

```bash
PORTAL_SITE_CONFIG_PATH=/app/backend/portal_sites.json
```

If needed, also point base URL:

```bash
PORTAL_BASE_URL=https://your-domain.example.com
```

### 3. Restart services

```bash
docker compose up --build
```

### 4. Validate selectors before running voice automation

Use the profile validator endpoint:

```bash
curl http://localhost:8000/automation/validate/utility
curl http://localhost:8000/automation/validate/pharmacy
curl http://localhost:8000/automation/validate/hospital
```

The response includes:

- `reachable` and `reached_url`
- per-selector `found` status
- `missing_selectors`
- `screenshot_b64` for quick visual debugging

## Notes for Real Sites

- Many real portals use MFA/CAPTCHA and anti-bot protections; fully unattended automation may not be possible.
- You may need authenticated session bootstrapping for protected pages.
- Start by validating selectors manually in browser devtools.

## Config Keys

Portal profile JSON supports:

- `urls`: list of URL strings
- `selectors.login_button` (hospital only optional)
- `selectors.doctor_input`
- `selectors.date_input`
- `selectors.submit_button`
- `selectors.medication_input`
- `selectors.quantity_input`
- `selectors.amount_input`
- `success_url_pattern`