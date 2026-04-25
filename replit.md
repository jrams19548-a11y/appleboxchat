# AppleBox Chat

AppleBox Chat is a real-time communication platform built with Python and Flask featuring chat channels, DMs, voice calling (WebRTC), Discord-style server voice channels (mesh WebRTC) with camera video and screen sharing, 1-on-1 video calls and screen sharing in DMs, profile customization, an admin panel, polls, and integrated games.

## Tech Stack

- **Backend:** Python 3.12, Flask, Flask-SocketIO, Flask-Login
- **Real-time:** Flask-SocketIO (WebSockets via threading async mode)
- **Storage:** Flat-file storage in `data/` (JSON / TXT)
- **Encryption:** Cryptography (AES-GCM) for password protection

## Project Structure

- `main.py` — main Flask application, routes, and SocketIO handlers
- `profanity_filter.py` — profanity filtering helpers
- `data/` — flat-file persistence (users, channels, polls, configs, etc.)
- `static/` — images, uploads, emojis, favicon
- `templates/` — Jinja2 HTML templates (login, channel, profile, games, etc.)
- `requirements.txt` / `Pipfile` — Python dependencies

## Replit Setup

- Workflow `Start application` runs `python main.py` and binds to `0.0.0.0:5000` (webview).
- The Flask-SocketIO development server is used in dev; `allow_unsafe_werkzeug=True` is set so the dev server can host WebSockets behind the Replit proxy.
- Deployment target is `vm` (always-on) since the app maintains in-memory state and uses local flat-file storage that wouldn't survive autoscale spin-down.
- Production run command: `python main.py`.

## Notes

- Chat history and user data live in `data/` — back this up if needed.
- Default admin/owner usernames referenced in code: `jesseramsey`, `Killua`.
