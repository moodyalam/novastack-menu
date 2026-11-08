# novastack-menu

NovaStack's menu service: a tiny Flask web app used in **Lecture 5 (Docker)** of
*Mastering CS Technical Competencies*. It is deliberately small: one file of
code, one dependency.

| Route | What it returns |
|---|---|
| `/` | A menu page: the heading `NovaStack menu is open` (the title comes from the `MENU_TITLE` environment variable), a card per item, and which system and machine it's running on |
| `/menu` | The NovaStack menu as JSON (18 items) |
| `/health` | `{"status": "ok"}` |

## Files

| File | Used in |
|---|---|
| `app.py`, `menu.json` | The service itself |
| `pyproject.toml`, `uv.lock`, `.python-version` | Running it **on your laptop** with uv (`uv run app.py`) |
| `requirements.txt` | The same dependency (`flask==3.1.3`) for the **Dockerfiles** (`pip install -r requirements.txt`) |
| `Dockerfile.step3-saved-draft` | **Step 3**: an AI-style first draft that forgets to install Flask |
| `Dockerfile.step4` | **Step 4**: the simple fix |
| `Dockerfile.step5` | **Step 5**: the cached version (copy it to `Dockerfile` if you skipped Step 5: Compose builds `Dockerfile`) |
| `compose.yaml`, `db/init/01_menu.sql`, `.env.example` | **Step 6**: the service plus a Postgres 16 database |
| `extras/dockerignore.example` | Step 5 and the Intermediate lab: copy to `.dockerignore` |
| `lab5/`, `tools/check_lab5.py` | The Lecture 5 labs: answer sheets and the self-check (`uv run tools/check_lab5.py beginner`) |
| `exercise/` | Exercise ORD-371 (Part 0 of each lab): an unfinished Dockerfile and a page that won't load |
| `advanced/` | The Advanced lab starter: a service that counts orders in Postgres, plus 200 seeded orders. You write `compose.yaml` |
| `.devcontainer/` | A fallback for GitHub Codespaces (Docker inside the codespace) |

## Run it with Docker

macOS / Linux (on Windows PowerShell use `Copy-Item` for `cp` and `curl.exe` for `curl`):

```bash
cp Dockerfile.step5 Dockerfile
docker build -t novastack-menu:1.0 .
docker run -d --name menu -p 8000:8000 novastack-menu:1.0
curl localhost:8000/menu
```

Build a different Dockerfile with `-f`, for example
`docker build -f Dockerfile.step4 -t novastack-menu:1.0 .`.

## With a database (Compose)

```bash
cp .env.example .env
docker compose up -d
docker compose exec db psql -U menu -c "SELECT count(*) FROM items;"
docker compose down
```

`.env` holds the database password and is **git-ignored**. Edit it before you
start; never commit it. `docker compose down -v` also deletes the database's
volume.

## Run it on your laptop (without Docker)

```bash
uv sync
uv run app.py
```

`uv sync` creates `.venv/` in this folder (Python 3.12 and Flask, from `uv.lock`);
`uv run app.py` uses it (and creates it first if you skipped `uv sync`). Open
<http://localhost:8000> and stop it with `Ctrl+C`. Without uv:
`python -m venv .venv`, then `.venv/bin/pip install -r requirements.txt`
(Windows: `.venv\Scripts\pip`), then `.venv/bin/python app.py`.

Flask is then installed in `.venv` **on your laptop only**. A Docker image never
sees it: the image installs its own (that's Step 3's lesson).
