# DigiBridge

Voice-driven portal automation powered by FastAPI, Playwright, and real-time status streaming.

## What It Does

DigiBridge listens to a spoken request, converts it to structured intent, and executes an automation flow against one of three portal categories:

- Hospital
- Pharmacy
- Utility

The app also supports:

- Live request status updates through Server-Sent Events (SSE)
- Session memory (repeat previous action)
- Screenshot confirmation for completed actions
- Optional ElevenLabs voice response playback

The dummy environment now ships as a unified multi-function portal (single site) that supports all three workflows.

## Frontend (Updated)

The frontend has been refreshed with a responsive two-panel layout and improved visual hierarchy:

- Left panel: product context and feature chips
- Right panel: voice command console with mic control, transcript, status feed, and result card
- Sticky identity with automatic portal routing from voice intent (no manual portal picker)
- Session badge + repeat-last control

The JavaScript integration points remain the same (`id`s and required classes are preserved), so existing backend behavior is unchanged.

## Quick Start (Docker)

### 1. Set environment variables

Create a `.env` file in the project root:

```bash
GEMINI_API_KEY=your_gemini_key
ELEVENLABS_API_KEY=your_elevenlabs_key
ELEVENLABS_VOICE_ID=EXAVITQu4vr4xnSDxMaL
CLAUDE_API_KEY=
PORTAL_BASE_URL=http://dummy-portal
PORTAL_SITE_CONFIG_PATH=/app/backend/portal_sites.json
```

### 2. Build and start services

```bash
docker compose up --build
```

### 3. Open the app

- API health: http://localhost:8000/health
- Frontend: http://localhost:8000/frontend/
- Unified dummy portal: http://localhost:8080/
- Shared success page: http://localhost:8080/success.html

## Run Against Real Websites

DigiBridge supports real-site automation using intent-based portal routing and URL/selector profiles.

### 1. Create your site profile

```bash
cp backend/portal_sites.example.json backend/portal_sites.json
```

For each portal entry, configure:

- `urls`: list of candidate URLs (first reachable URL is used)
- `selectors`: CSS selectors used by the automator
- `success_url_pattern`: Playwright URL glob to verify completion

### 2. Ensure config path is available in backend container

```bash
PORTAL_SITE_CONFIG_PATH=/app/backend/portal_sites.json
```

If needed, override base URL:

```bash
PORTAL_BASE_URL=https://your-domain.example.com
```

### 3. Restart

```bash
docker compose up --build
```

### 4. Validate selectors before voice automation

```bash
curl http://localhost:8000/automation/validate/hospital
curl http://localhost:8000/automation/validate/pharmacy
curl http://localhost:8000/automation/validate/utility
```

Validation response includes:

- `reachable` and `reached_url`
- selector-level `found` results
- `missing_selectors`
- `screenshot_b64`

## API Endpoints

- `POST /process-voice`: process a transcript and run automation
- `GET /status-stream/{request_id}`: SSE request progress updates
- `GET /session/{session_id}`: fetch last session action
- `GET /automation/validate/{portal}`: selector/URL profile validation
- `GET /health`: service health check

## Project Structure

```text
backend/
  automation.py
  intent_parser.py
  llm_parser.py
  main.py
  portal_sites.example.json
  portal_sites.json
frontend/
  index.html
  app.js
dummy_portal/
  hospital/
  pharmacy/
  utility/
Dockerfile
docker-compose.yml
```

## Notes and Limitations

- Some real portals enforce CAPTCHA, MFA, or anti-bot controls; full automation may fail without manual or session-assisted steps.
- Chromium automation is memory-sensitive; give Docker enough memory on low-tier VPS instances.
- Keep API keys in environment variables only. Do not commit `.env`.
