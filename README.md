# VoicePay

A premium, voice-first prototype for Touch 'n Go-style money transfers. Speak it, confirm it, send it.

## Stack

- **Backend** — FastAPI (Python). Voice-command parsing, fraud check, mock wallet.
- **Frontend** — Vanilla HTML / CSS / JS with the Web Speech API. No build step.

## Quickstart

```bash
# from the repo root
pip install fastapi uvicorn

# run the API + frontend on http://localhost:8000
uvicorn backend.main:app --reload --port 8000
```

Then open http://localhost:8000 — the FastAPI server mounts the `frontend/` directory, so API and UI share an origin.

API docs: http://localhost:8000/docs

## Demo PIN

`1234` (tap `?` on the PIN pad as a hint).

## Try saying

- "Send RM50 to Ali for lunch"
- "Hantar 20 ringgit kat mak"
- "Send 75 ringgit to Siti"

Voice recognition uses the browser's Web Speech API — Chrome / Edge work best. If unsupported, the typed input still works.
