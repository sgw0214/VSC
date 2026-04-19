# English Line Drill (Web MVP)

Mobile-first English conversation memorization app for A2 to B1 learners.

## Quick start (recommended)

One-time setup + background run:

```bat
run_app.bat
```

Stop background server:

```bat
stop_app_background.bat
```

Or from terminal:

```powershell
.\run_app.ps1
```

Useful options:

```powershell
.\run_app.ps1 -SetupOnly
.\run_app.ps1 -NoBrowser
.\run_app.ps1 -Port 8080
```

## Phone-first use (no repeated script on phone)

1. Run once on PC: `run_app.bat` (background mode)
2. Open the app URL on your phone (same Wi-Fi).
3. Install to home screen (PWA install).
4. From then on, open from phone home icon.

If backend is not reachable, the app automatically switches to `Offline Phone Mode` and keeps review progress in phone local storage.

## Included in this build

- 20 dialogue draft sets in `data/dialogues_seed.json`
- FastAPI + SQLite backend with seed, queue, and review APIs
- PWA frontend with Today, Practice, Review screens
- SRS-style review scheduling with score `0-5`

## Run locally

1. Create and activate a Python environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Start API + web app:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

4. Open:

```text
http://localhost:8000
```

For same-network mobile access, replace `localhost` with your PC LAN IP.

## API quick reference

- `GET /api/health`
- `GET /api/dialogues?limit=20&level=A2&scene=Office`
- `GET /api/dialogues/{dialogue_id}`
- `GET /api/scenes`
- `GET /api/review/next?limit=10`
- `POST /api/review/attempt`
- `GET /api/stats`

## Key files

- `app/main.py`: API routes and app bootstrap
- `app/models.py`: SQLite models
- `app/seed.py`: initial dialogue seeding
- `data/dialogues_seed.json`: 20 dialogue sets
- `static/index.html`: MVP UI
- `static/app.js`: client logic
- `static/styles.css`: responsive styling
