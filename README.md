# GOTHAM

A Flask-based SOCMINT (Social Media Intelligence) platform for open-source investigations. GOTHAM aggregates data from multiple OSINT tools and APIs into an interactive graph, providing a unified interface for subject profiling.

## Features

- **Username investigation** — runs Maigret and Sherlock across hundreds of platforms
- **Email lookup** — checks email against known services via Holehe
- **Phone lookup** — Moriarty and WhatsApp presence checks
- **Domain / IP enrichment** — Shodan integration
- **Google dorks** — automated dork queries via DuckDuckGo
- **Platform screenshot capture** — headless Firefox screenshots of found profiles, screened by Gemini AI
- **Camera sweep** — discovers open cameras via Insecam/FOFA, with face detection and subject matching
- **Yandex reverse image search** — finds matching images from avatars
- **Interactive graph** — nodes and edges visualising all discovered connections
- **PDF report export** — generates a formatted investigative report per case
- **Multi-user** — account registration and login with session management

## Requirements

- Python 3.11+
- Firefox + [geckodriver](https://github.com/mozilla/geckodriver/releases) (placed at `.venv/bin/geckodriver`)
- **Argus** sidecar API running at `http://172.16.128.144:8000` — handles Holehe, Moriarty, WhatsApp, Telegram, Yandex image search, and face recognition. Update `OSINT_API` in `src/server.py` to match your deployment.
- Gemini API key (optional — enables AI screenshot screening)
- Shodan API key (optional — enables IP/domain enrichment)

## Setup

### 1. Clone and create virtual environment

```bash
git clone <repo-url>
cd GOTHAM
python -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

Sherlock is installed as an editable package directly from its Git repository (see `requirements.txt`). If the editable install fails, run:

```bash
pip install git+https://github.com/sherlock-project/sherlock.git
```

### 3. Configure environment

Copy the example env file and fill in your keys:

```bash
cp src/.env.example src/.env
```

`src/.env`:
```
GEMINI=your_gemini_api_key_here
SHODAN_KEY=your_shodan_api_key_here
```

### 4. Install geckodriver

Download geckodriver for your platform from [Mozilla releases](https://github.com/mozilla/geckodriver/releases) and place the binary at:

```
.venv/bin/geckodriver
```

### 5. Run

```bash
python src/server.py
```

The server starts on `http://0.0.0.0:5000`. Register an account on first use.

## Nix

If you use Nix, a `shell.nix` is provided:

```bash
nix-shell
```

This drops you into a shell with system dependencies available. Still create the Python venv inside it.

## Project Structure

```
GOTHAM/
├── src/
│   ├── server.py        # Flask application — all routes and OSINT logic
│   └── .env.example     # Environment variable template
├── templates/           # Jinja2 HTML templates
├── static/              # Static assets (background image, etc.)
├── generate_docs.py     # PDF documentation generator
├── requirements.txt     # Python dependencies
├── shell.nix            # Nix development shell
└── LICENSE
```

Runtime directories created automatically (gitignored):
- `cases/` — per-case screenshots and report data
- `shots/` — platform screenshot cache

## Notes

- The secret key in `server.py` (`gotham-dev-key-change-in-prod`) must be changed for any non-local deployment.
- Case data and the SQLite database (`gotham.db`) are local-only and not committed.
- The Argus sidecar URL (`OSINT_API`) is hardcoded to a local network address — update it to match your environment.
