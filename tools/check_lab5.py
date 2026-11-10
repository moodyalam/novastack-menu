#!/usr/bin/env python3
"""Self-check for the Lecture 5 (Docker) labs.

Run from the root of your novastack-menu folder, with Docker running:

    uv run tools/check_lab5.py beginner
    uv run tools/check_lab5.py intermediate
    uv run tools/check_lab5.py advanced

(`python3 tools/check_lab5.py beginner` works too: it uses only the standard
library.) It prints PASS, FAIL or SKIP for each check, with a hint for every
FAIL. It starts and removes its own throw-away containers (names start with
`lab5check`), and never touches yours.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path.cwd()
IMAGE = "novastack-menu"
results: list[tuple[str, str, str]] = []


# ----------------------------------------------------------------- helpers
def report(status: str, title: str, hint: str = "") -> None:
    results.append((status, title, hint))
    print(f"{status:<5} {title}")
    if hint and status != "PASS":
        print(f"        hint: {hint}")


def run(cmd: list[str], cwd: Path | None = None, timeout: int = 300) -> tuple[int, str]:
    try:
        p = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except FileNotFoundError:
        return 127, f"{cmd[0]}: command not found"
    except subprocess.TimeoutExpired:
        return 124, "timed out"


def docker(*args: str, **kw) -> tuple[int, str]:
    return run(["docker", *args], **kw)


def docker_ready() -> bool:
    rc, _ = docker("info", timeout=30)
    return rc == 0


def http_get(url: str, tries: int = 20) -> tuple[int, str]:
    last = (0, "no answer")
    for _ in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, ""
        except Exception as e:  # not up yet
            last = (0, str(e))
            time.sleep(1)
    return last


def answers(path: Path) -> dict[str, str]:
    """Read `KEY: value` lines from an answer sheet."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        print(f"{path.name} isn't saved as UTF-8 (PowerShell's > writes UTF-16). Open it in VS Code and save it as UTF-8.")
        return out
    for line in text.splitlines():
        m = re.match(r"^\s*([A-Z]{1,3}\d?[a-z]?\d*):\s*(.*?)\s*$", line)
        if m and m.group(2) and not m.group(2).startswith("<"):
            out[m.group(1)] = m.group(2)
    return out


def number(text: str | None) -> float | None:
    if not text:
        return None
    m = re.search(r"\d+(?:\.\d+)?", text.replace(",", ""))
    return float(m.group()) if m else None


def dockerfile_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [ln.rstrip() for ln in path.read_text(encoding="utf-8").splitlines()]


def instr(lines: list[str], word: str) -> list[int]:
    return [i for i, ln in enumerate(lines) if ln.strip().upper().startswith(word + " ")]


def why_comments(lines: list[str]) -> int:
    return sum(1 for ln in lines if re.match(r"\s*#\s*why:\s*\S+", ln, re.I))


def run_app_container(image: str, env: dict[str, str] | None = None, port: int = 8000):
    """Start `image` on a random local port; return (name, base_url) or (name, None)."""
    name = "lab5check-app"
    docker("rm", "-f", name)
    cmd = ["run", "-d", "--name", name, "-p", f"127.0.0.1::{port}"]
    for k, v in (env or {}).items():
        cmd += ["-e", f"{k}={v}"]
    rc, out = docker(*cmd, image)
    if rc != 0:
        return name, None, out
    rc, out = docker("port", name, f"{port}/tcp")
    m = re.search(r":(\d+)\s*$", out.strip().splitlines()[0]) if rc == 0 and out.strip() else None
    return name, (f"http://127.0.0.1:{m.group(1)}" if m else None), out


def check_menu_service(image: str, title: str) -> None:
    name, base, out = run_app_container(image, {"MENU_TITLE": title})
    try:
        if not base:
            _, logs = docker("logs", name)
            report("FAIL", f"{image} starts and stays running",
                   "Run it yourself and read `docker logs`; is anything missing from the box? "
                   + logs.strip().splitlines()[-1][:100] if logs.strip() else out.strip()[:100])
            return
        code, body = http_get(base + "/")
        if code == 200 and f"{title} is open" in body:
            report("PASS", "The page reads its title from MENU_TITLE (-e)")
        else:
            report("FAIL", "The page reads its title from MENU_TITLE (-e)",
                   f"GET / gave {code}; expected a page whose heading says '{title} is open'. (Undo your Step 5 heading edit with `git restore templates/index.html`.) "
                   "Is the app listening on 0.0.0.0, and did the image install Flask?")
        code, body = http_get(base + "/menu", tries=3)
        try:
            n = len(json.loads(body))
        except Exception:
            n = -1
        report("PASS" if code == 200 and n == 18 else "FAIL", "/menu returns the 18 menu items",
               f"GET /menu gave {code} with {n} items.")
    finally:
        docker("rm", "-f", name)


# ---------------------------------------------------------------- beginner
def beginner() -> None:
    sheet = answers(ROOT / "lab5" / "BEGINNER.md")
    if not (ROOT / "lab5" / "BEGINNER.md").exists():
        report("FAIL", "Answer sheet lab5/BEGINNER.md exists", "Run this from the root of your novastack-menu folder.")
        return

    rc, out = docker("run", "--rm", "python:3.12-slim", "python", "-V")
    real = out.strip().splitlines()[-1] if rc == 0 and out.strip() else ""
    a1 = sheet.get("A1", "")
    report("PASS" if real and real.lower() in a1.lower() else "FAIL",
           "A1: the Python version in the python:3.12-slim container",
           f"Run `docker run --rm python:3.12-slim python -V` and paste what it prints (A1). It prints: {real or '?'}")

    rc, out = docker("run", "--rm", "nginx", "cat", "/etc/os-release")
    m = re.search(r'PRETTY_NAME="([^"]+)"', out)
    distro = m.group(1).split()[0].lower() if m else ""
    report("PASS" if distro and distro in sheet.get("A2", "").lower() else "FAIL",
           "A2: the Linux distribution inside the nginx container",
           "Use `docker exec` (or `docker run --rm nginx cat /etc/os-release`) and read PRETTY_NAME.")

    rc, out = docker("run", "--rm", "postgres:16", "postgres", "--version")
    m = re.search(r"(\d+)\.(\d+)", out)
    report("PASS" if m and m.group(1) == "16" and f"{m.group(1)}.{m.group(2)}" in sheet.get("A3", "") else "FAIL",
           "A3: the exact Postgres version in the postgres:16 image",
           f"Run `docker run --rm postgres:16 postgres --version`. It prints: {out.strip()[:60] or '?'}")

    report("PASS" if number(sheet.get("A4")) == 1 else "FAIL",
           "A4: the exit code of the container that forgot to install Flask",
           "Build Dockerfile.step3-saved-draft, run it, then look at `docker ps -a` (Exited (N)).")

    lines = dockerfile_lines(ROOT / "Dockerfile")
    ok = (lines and any(re.match(r"FROM\s+python:3\.12", ln, re.I) for ln in lines)
          and instr(lines, "COPY") and any("pip install" in ln for ln in lines) and instr(lines, "CMD"))
    report("PASS" if ok else "FAIL", "Your Dockerfile: FROM python:3.12, COPY, pip install, CMD",
           "Write a file called Dockerfile (not Dockerfile.step4) with those four kinds of line.")
    n = why_comments(lines)
    report("PASS" if n >= 3 else "FAIL", "Your Dockerfile has a `# why:` comment on at least 3 lines",
           f"Found {n}. Explain each line you keep, in your own words: `# why: ...`")

    rc, out = docker("image", "inspect", f"{IMAGE}:1.0-ready", "--format", "{{.Id}}")
    if rc != 0:
        report("FAIL", f"The image {IMAGE}:1.0-ready exists", f"Build it: docker build -t {IMAGE}:1.0-ready .")
        report("SKIP", "A5: your image ID matches")
        report("SKIP", "The service answers correctly in a container")
    else:
        report("PASS", f"The image {IMAGE}:1.0-ready exists")
        image_id = out.strip().split(":")[-1]
        a5 = sheet.get("A5", "").lower().replace("sha256:", "").strip()
        report("PASS" if len(a5) >= 12 and image_id.startswith(a5[:12]) else "FAIL",
               "A5: the first 12 characters of your image's ID",
               f"Run `docker images {IMAGE}` and copy the IMAGE ID of {IMAGE}:1.0-ready.")
        check_menu_service(f"{IMAGE}:1.0-ready", "Lab check")

    why = sheet.get("A6", "").lower()
    report("PASS" if len(why.split()) >= 6 and re.search(r"flask|install|depend|requirement|pip", why) else "FAIL",
           "A6: why the first container stopped, in your own words",
           "One or two sentences: what did the box not have, and where did the log say so?")

    user = sheet.get("HUB", "")
    if not user or user.lower() in ("none", "skip", "n/a"):
        report("SKIP", "(optional) Pushed to Docker Hub", "Add `HUB: <your Docker Hub username>` to the answer sheet to check it.")
    else:
        try:
            with urllib.request.urlopen(
                f"https://hub.docker.com/v2/repositories/{user}/{IMAGE}/tags/1.0-ready", timeout=10
            ) as r:
                report("PASS" if r.status == 200 else "FAIL", f"(optional) {user}/{IMAGE}:1.0-ready is on Docker Hub")
        except Exception:
            report("FAIL", f"(optional) {user}/{IMAGE}:1.0-ready is on Docker Hub",
                   "Push it (docker tag, docker push) and make sure the repository is public.")


# ------------------------------------------------------------ intermediate
def intermediate() -> None:
    sheet = answers(ROOT / "lab5" / "INTERMEDIATE.md")
    if not (ROOT / "lab5" / "INTERMEDIATE.md").exists():
        report("FAIL", "Answer sheet lab5/INTERMEDIATE.md exists", "Run this from the root of your novastack-menu folder.")
        return

    ignore = (ROOT / ".dockerignore")
    text = ignore.read_text(encoding="utf-8") if ignore.exists() else ""
    need = [".git", ".env"]
    missing = [n for n in need if not re.search(rf"^{re.escape(n)}\s*$", text, re.M)]
    report("PASS" if ignore.exists() and not missing else "FAIL", ".dockerignore keeps .git and .env out of the image",
           f"Create .dockerignore (see extras/dockerignore.example). Missing: {', '.join(missing) or 'the file'}")

    lines = dockerfile_lines(ROOT / "Dockerfile")
    copies = instr(lines, "COPY")
    runs = [i for i, ln in enumerate(lines) if "pip install" in ln]
    req = [i for i in copies if "requirements" in lines[i]]
    def copy_args(ln: str) -> list[str]:
        return [a for a in ln.split()[1:] if not a.startswith("--")]

    allc = [i for i in copies if copy_args(lines[i])[:1] == ["."]]
    ok = bool(req and runs and allc and req[0] < runs[0] < allc[0])
    report("PASS" if ok else "FAIL", "Dockerfile order: COPY requirements.txt, then pip install, then COPY . .",
           "Put what changes least first (see Step 5 of the demo).")
    report("PASS" if any(re.match(r"FROM\s+python:3\.12-slim", ln, re.I) for ln in lines) else "FAIL",
           "Base image is python:3.12-slim", "Use the slim variety, pinned to 3.12.")
    report("PASS" if instr(lines, "USER") else "FAIL", "Dockerfile switches to a non-root USER",
           "Create a user (useradd) after installing packages, then add a USER line before CMD.")
    n = why_comments(lines)
    report("PASS" if n >= 5 else "FAIL", "Dockerfile has a `# why:` comment on at least 5 lines",
           f"Found {n}. Explain each change you made (AI may draft; you must justify).")

    rc, out = docker("image", "inspect", f"{IMAGE}:2.0", "--format", "{{.Size}}")
    if rc != 0:
        report("FAIL", f"The image {IMAGE}:2.0 exists", f"Build it: docker build -t {IMAGE}:2.0 .")
        report("SKIP", "Image is small, runs as non-root and works")
    else:
        size_mb = int(out.strip()) / 1e6
        report("PASS" if size_mb < 300 else "FAIL", f"{IMAGE}:2.0 is under 300 MB (it is {size_mb:.0f} MB)",
               "The slim base should give about 225 MB. Did you build from python:3.12?")
        rc, uid = docker("run", "--rm", f"{IMAGE}:2.0", "id", "-u")
        report("PASS" if rc == 0 and uid.strip() not in ("", "0") else "FAIL", "The container does not run as root",
               "`docker run --rm novastack-menu:2.0 id -u` must not print 0.")
        check_menu_service(f"{IMAGE}:2.0", "Intermediate check")
        s2 = number(sheet.get("S2"))
        report("PASS" if s2 and abs(s2 - size_mb) <= 0.1 * size_mb else "FAIL",
               "S2: the size (MB) of your slim image matches `docker images`",
               f"Run `docker images {IMAGE}` and write the size of 2.0 in MB (you have {size_mb:.0f}).")

    s1, s2 = number(sheet.get("S1")), number(sheet.get("S2"))
    report("PASS" if s1 and s2 and s1 >= 2 * s2 else "FAIL",
           "S1: the image built FROM python:3.12 (not slim) is at least twice as big",
           "Build once with FROM python:3.12, note the size, then switch back to slim.")
    t1, t2 = number(sheet.get("T1")), number(sheet.get("T2"))
    report("PASS" if t1 and t2 and t2 < t1 else "FAIL", "T1/T2: your rebuild after an edit is faster with the cache-friendly order",
           "Record T1 (code copied first) and T2 (requirements first), in seconds.")

    # Hidden check: really measure caching on a throw-away copy of your build context.
    tmp = Path(tempfile.mkdtemp(prefix="lab5check-"))
    try:
        ctx = tmp / "ctx"
        shutil.copytree(ROOT, ctx, ignore=shutil.ignore_patterns(".git", ".venv", ".env", "__pycache__", "advanced", "lab5"))
        rc, _ = docker("build", "-q", "-t", "lab5check-cache", ".", cwd=ctx)
        if rc != 0:
            report("FAIL", "Your Dockerfile builds", "Run `docker build .` and read the first error.")
        else:
            app = ctx / "app.py"
            app.write_text(app.read_text(encoding="utf-8") + "\n# a harmless edit\n", encoding="utf-8")
            rc, out = docker("build", "--progress=plain", "-t", "lab5check-cache", ".", cwd=ctx)
            pip_lines = [ln for ln in out.splitlines() if "RUN" in ln and "pip install" in ln]
            cached = any(re.search(r"#\d+ CACHED", ln) for ln in out.splitlines()) and bool(pip_lines)
            # the step id of the pip install line appears again with CACHED
            ids = {re.match(r"#(\d+)", ln).group(1) for ln in pip_lines if re.match(r"#(\d+)", ln)}
            was_cached = any(re.match(rf"#{i} CACHED", ln) for ln in out.splitlines() for i in ids)
            report("PASS" if was_cached else "FAIL", "Hidden check: after a one-line edit, `pip install` is CACHED",
                   "Copy requirements.txt and install BEFORE copying the rest of the code.")
    finally:
        docker("rmi", "-f", "lab5check-cache")
        shutil.rmtree(tmp, ignore_errors=True)

    both = {"linux/amd64": "x86_64", "linux/arm64": "aarch64"}
    rc, _ = docker("image", "inspect", f"{IMAGE}:multi")
    if rc != 0:
        report("FAIL", f"{IMAGE}:multi built for amd64 and arm64",
               f"docker buildx build --platform linux/amd64,linux/arm64 -t {IMAGE}:multi .")
    else:
        bad = []
        for plat, mach in both.items():
            rc, out = docker("run", "--rm", "--platform", plat, f"{IMAGE}:multi", "python", "-c",
                             "import platform; print(platform.machine())")
            if rc != 0 or out.strip().splitlines()[-1:] != [mach]:
                bad.append(plat)
        report("PASS" if not bad else "FAIL", f"{IMAGE}:multi runs on both amd64 and arm64",
               f"Failed on {', '.join(bad)}. Rebuild with --platform linux/amd64,linux/arm64.")

    v1 = sheet.get("V1", "").strip().lower()
    if v1 in ("", "skip", "skipped", "n/a"):
        report("SKIP", "(optional) Docker Scout quickview", "Run `docker scout quickview` and write the vulnerability counts as `V1: ...`.")
    else:
        report("PASS" if re.search(r"\d", v1) else "FAIL", "V1: you recorded the Docker Scout counts",
               "Write the numbers, for example `V1: 0C 1H 4M 12L`.")


# ---------------------------------------------------------------- advanced
def compose(tmp: Path, *args: str, timeout: int = 300) -> tuple[int, str]:
    return docker("compose", "-p", "lab5check", *args, cwd=tmp, timeout=timeout)


def advanced() -> None:
    base = ROOT / "advanced"
    sheet = answers(ROOT / "lab5" / "ADVANCED.md")
    if not base.exists() or not (ROOT / "lab5" / "ADVANCED.md").exists():
        report("FAIL", "advanced/ and lab5/ADVANCED.md exist", "Run this from the root of your novastack-menu folder.")
        return

    env_path = base / ".env"
    env: dict[str, str] = {}
    if env_path.exists():
        for ln in env_path.read_text(encoding="utf-8").splitlines():
            if "=" in ln and not ln.lstrip().startswith("#"):
                k, v = ln.split("=", 1)
                env[k.strip()] = v.strip()
    pw = env.get("POSTGRES_PASSWORD", "")

    rc, out = run(["git", "check-ignore", "-q", "advanced/.env"], cwd=ROOT)
    rc2, tracked = run(["git", "ls-files", "advanced/.env"], cwd=ROOT)
    report("PASS" if env_path.exists() and rc == 0 and not tracked.strip() else "FAIL",
           ".env exists, is git-ignored and is not committed",
           "Copy .env.example to .env, and make sure .gitignore lists .env (git status must not show it).")
    report("PASS" if re.fullmatch(r"[A-Za-z0-9]{8,}", pw) and pw != "change-me" else "FAIL",
           "You chose your own password: at least 8 letters and digits only",
           "Edit POSTGRES_PASSWORD in advanced/.env. Letters and digits only, because it goes into a URL.")
    ex = (base / ".env.example")
    report("PASS" if ex.exists() and "change-me" in ex.read_text(encoding="utf-8") else "FAIL",
           ".env.example holds only a placeholder password", "Never put your real password in .env.example.")

    cf = base / "compose.yaml"
    if not cf.exists():
        report("FAIL", "advanced/compose.yaml exists", "Write it: services `app` and `db`.")
        return
    raw = cf.read_text(encoding="utf-8")
    report("PASS" if not re.search(r"^version:", raw, re.M) else "FAIL", "compose.yaml has no obsolete `version:` line",
           "Compose ignores it and warns: delete the line.")
    report("PASS" if not pw or pw not in raw else "FAIL", "The password is not written in compose.yaml",
           "Use env_file: .env or ${POSTGRES_PASSWORD}, never the value itself.")

    tmp = Path(tempfile.mkdtemp(prefix="lab5check-"))
    try:
        shutil.copytree(base, tmp / "advanced", ignore=shutil.ignore_patterns(".git", "__pycache__"))
        work = tmp / "advanced"
        rc, out = compose(work, "config", "--format", "json")
        try:
            cfg = json.loads(out[out.index("{"):])
        except Exception:
            report("FAIL", "compose.yaml is valid", out.strip()[:200])
            return
        svc = cfg.get("services", {})
        report("PASS" if {"app", "db"} <= set(svc) else "FAIL", "compose.yaml has services named `app` and `db`",
               "Use exactly those two service names.")
        if "app" not in svc or "db" not in svc:
            return
        db, app = svc["db"], svc["app"]
        report("PASS" if str(db.get("image", "")).startswith("postgres:16") else "FAIL", "db uses the official postgres:16 image",
               "image: postgres:16 (pin the major version).")
        vols = db.get("volumes", [])
        report("PASS" if any(v.get("type") == "volume" and v.get("target") == "/var/lib/postgresql/data" for v in vols) else "FAIL",
               "db keeps its data in a named volume at /var/lib/postgresql/data", "volumes: - pgdata:/var/lib/postgresql/data, and declare pgdata at the bottom.")
        report("PASS" if any(v.get("target") == "/docker-entrypoint-initdb.d" for v in vols) else "FAIL",
               "db loads the seed script from ./db/init", "Mount ./db/init at /docker-entrypoint-initdb.d.")
        test = " ".join(db.get("healthcheck", {}).get("test", []))
        report("PASS" if "pg_isready" in test else "FAIL", "db has a healthcheck using pg_isready", "healthcheck: test: [\"CMD-SHELL\", \"pg_isready ...\"]")
        dep = app.get("depends_on", {}).get("db", {})
        report("PASS" if dep.get("condition") == "service_healthy" else "FAIL", "app waits for db to be healthy",
               "depends_on: db: condition: service_healthy")
        url = (app.get("environment", {}) or {}).get("DATABASE_URL", "")
        report("PASS" if re.search(r"@db[:/]", url) else "FAIL", "DATABASE_URL reaches the database by service name (@db:5432)",
               "Inside Compose, use the service name `db`, not localhost.")

        # ---- run it for real, with its own project name, then test persistence
        rc, out = compose(work, "up", "-d", "--build", "--wait", timeout=600)
        if rc != 0:
            report("FAIL", "docker compose up -d starts both services",
                   "Stop your own stack first (`docker compose down` in advanced/) in case ports clash. " + out.strip()[-160:])
            compose(work, "down", "-v")
            return
        report("PASS", "docker compose up -d starts both services and they become healthy")

        def count() -> int:
            rc, out = compose(work, "port", "app", "8000")
            m = re.search(r":(\d+)\s*$", out.strip())
            if rc != 0 or not m:
                return -1
            code, body = http_get(f"http://127.0.0.1:{m.group(1)}/orders/count")
            try:
                return int(json.loads(body)["count"]) if code == 200 else -1
            except Exception:
                return -1

        n = count()
        report("PASS" if n == 200 else "FAIL", "/orders/count returns 200 (the seeded orders)",
               f"It returned {n}. Is the app container published on port 8000, and is the seed mounted?")

        user, dbname = env.get("POSTGRES_USER", "orders"), env.get("POSTGRES_DB", "orders")
        compose(work, "exec", "-T", "db", "psql", "-U", user, "-d", dbname, "-c",
                "INSERT INTO orders VALUES (201, 'C001', 1.00, 'paid', now());")
        compose(work, "down")
        rc, out = compose(work, "up", "-d", "--wait", timeout=600)
        n = count() if rc == 0 else -1
        report("PASS" if n == 201 else "FAIL", "Hidden check: data survives `down` (the row I added is still there)",
               f"Count after down and up was {n}, expected 201. Is the volume mounted at /var/lib/postgresql/data?")
        compose(work, "down", "-v")
        rc, out = compose(work, "up", "-d", "--wait", timeout=600)
        n = count() if rc == 0 else -1
        report("PASS" if n == 200 else "FAIL", "Hidden check: `down -v` wipes the volume and the seed runs again",
               f"Count after down -v and up was {n}, expected 200.")

        rc, imgs = compose(work, "config", "--images")
        leaked = False
        for img in imgs.split():
            if img.startswith("postgres"):
                continue
            _, hist = docker("history", "--no-trunc", img)
            _, insp = docker("image", "inspect", img)
            leaked = leaked or (bool(pw) and (pw in hist or pw in insp))
        report("PASS" if not leaked else "FAIL", "Your password is not baked into the app image",
               "Settings go in at run time (environment or env_file), never in the Dockerfile.")
    finally:
        compose(tmp / "advanced", "down", "-v")
        docker("rmi", "-f", "lab5check-app")
        shutil.rmtree(tmp, ignore_errors=True)

    seed = (base / "db" / "init" / "01_schema.sql").read_text(encoding="utf-8")
    failed = len(re.findall(r"'failed'", seed.split("VALUES", 1)[-1]))
    report("PASS" if re.match(r"\W*db\b", sheet.get("D1", "").strip().lower()) else "FAIL", "D1: the hostname the app uses to reach the database",
           "What is the Compose service name?")
    report("PASS" if number(sheet.get("D2")) == failed else "FAIL", "D2: how many orders have status 'failed'",
           "`docker compose exec db psql -U <user> -d <db> -c \"SELECT count(*) FROM orders WHERE status = 'failed';\"`")
    report("PASS" if number(sheet.get("D3")) == 201 and number(sheet.get("D4")) == 200 else "FAIL",
           "D3/D4: the row counts after `down` (D3) and after `down -v` (D4)",
           "Insert a row, `docker compose down`, `up -d`, count; then `down -v`, `up -d`, count.")
    report("PASS" if re.search(r"\b16(\.\d+)?\b", sheet.get("D5", "")) else "FAIL", "D5: the major version of Postgres in your db container",
           "`docker compose exec db postgres --version`")


def main() -> int:
    level = sys.argv[1] if len(sys.argv) > 1 else ""
    if level not in ("beginner", "intermediate", "advanced"):
        print(__doc__)
        return 2
    print(f"Lecture 5 lab self-check: {level}\n")
    if not docker_ready():
        report("FAIL", "Docker is running", "Start Docker Desktop and wait for 'Engine running', then run this again.")
    else:
        report("PASS", "Docker is running")
        {"beginner": beginner, "intermediate": intermediate, "advanced": advanced}[level]()
    p = sum(1 for r in results if r[0] == "PASS")
    f = sum(1 for r in results if r[0] == "FAIL")
    s = sum(1 for r in results if r[0] == "SKIP")
    print(f"\n{p} passed, {f} failed, {s} skipped")
    return 1 if f else 0


if __name__ == "__main__":
    sys.exit(main())
