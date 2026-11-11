#!/usr/bin/env python3
"""Self-check for the Lecture 6 (CI/CD) labs.

Run from the root of your novastack-menu folder:

    uv run tools/check_lab6.py beginner
    uv run tools/check_lab6.py intermediate
    uv run tools/check_lab6.py advanced --repo ../novastack-orders

(`python3 tools/check_lab6.py beginner` works too: it uses only the standard
library.) It prints PASS, FAIL or SKIP for each check, with a hint for every
FAIL. It reads three things:

- your answer sheet in lab6/ and your workflow files;
- your Git history (it never changes it);
- your fork on GitHub, through the GitHub CLI (`gh`), if it is installed and
  logged in. Without `gh` those checks SKIP: look at the Actions tab instead.

Hidden checks run your tests in a temporary copy of what is on your `main`
branch, so commit, merge and `git pull` before you check. `--offline` skips
every GitHub check.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path.cwd()
SHA = re.compile(r"^[0-9a-f]{40}$")
results: list[tuple[str, str, str]] = []
OFFLINE = False


# ----------------------------------------------------------------- helpers
def report(status: str, title: str, hint: str = "") -> None:
    results.append((status, title, hint))
    print(f"{status:<5} {title}")
    if hint and status != "PASS":
        print(f"        hint: {hint}")


def ok(passed: bool, title: str, hint: str = "") -> None:
    report("PASS" if passed else "FAIL", title, hint)


def run(
    cmd: list[str],
    cwd: Path | None = None,
    timeout: int = 300,
    env: dict[str, str] | None = None,
) -> tuple[int, str]:
    full_env = None
    if env:
        full_env = {**os.environ, **env}
    try:
        p = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            env=full_env,
            check=False,
        )
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except FileNotFoundError:
        return 127, f"{cmd[0]}: command not found"
    except subprocess.TimeoutExpired:
        return 124, "timed out"


def answers(path: Path) -> dict[str, str]:
    """Read `KEY: value` lines from an answer sheet."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        print(
            f"{path.name} isn't saved as UTF-8 (PowerShell 5's > writes UTF-16). "
            "Open it in VS Code and save it as UTF-8."
        )
        return out
    for line in text.splitlines():
        m = re.match(r"^\s*([A-Z]{1,7}\d?)(?:\s*\([^)]*\))?:\s*(.*?)\s*$", line)
        if m and m.group(2) and not m.group(2).startswith("<"):
            out[m.group(1)] = m.group(2).strip("`")
    return out


def number(text: str | None) -> float | None:
    if not text:
        return None
    m = re.search(r"\d+(?:\.\d+)?", text.replace(",", ""))
    return float(m.group()) if m else None


def words(text: str | None) -> int:
    return len((text or "").split())


# ------------------------------------------------- a tiny YAML reader
# The standard library has no YAML parser. Workflow files use a small part of
# YAML (maps, lists, [a, b] lists, | blocks, comments), and this reads that part.
def _strip_comment(s: str) -> str:
    quote = None
    for i, ch in enumerate(s):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "'\"" and (i == 0 or s[i - 1] in " :-[,{"):
            quote = ch
        elif ch == "#" and (i == 0 or s[i - 1] in " \t"):
            return s[:i].rstrip()
    return s.rstrip()


def _scalar(s: str):
    s = s.strip()
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        return [_scalar(x) for x in inner.split(",")] if inner else []
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"":
        return s[1:-1]
    return s


_KEY = re.compile(r"""^("[^"]*"|'[^']*'|[^\s#'"\[\]{},][^:]*?)\s*:(?:\s+(.*)|$)""")


def _tokens(text: str) -> list[list]:
    raw = text.replace("\t", "  ").splitlines()
    toks: list[list] = []
    i = 0
    while i < len(raw):
        line = raw[i]
        content = _strip_comment(line).strip()
        i += 1
        if not content or content == "---":
            continue
        indent = len(line) - len(line.lstrip(" "))
        block = None
        if re.search(r"(?:^-|:)\s*[|>][-+]?\d?$", content):
            body: list[str] = []
            while i < len(raw) and (
                not raw[i].strip() or len(raw[i]) - len(raw[i].lstrip(" ")) > indent
            ):
                body.append(raw[i])
                i += 1
            pad = min(
                (len(b) - len(b.lstrip(" ")) for b in body if b.strip()), default=0
            )
            block = "\n".join(b[pad:] for b in body).strip("\n")
            content = re.sub(r"\s*[|>][-+]?\d?$", "", content)
        toks.append([indent, content, block])
    return toks


def _parse(toks: list[list], pos: int, indent: int):
    if pos >= len(toks):
        return None, pos
    if toks[pos][1] == "-" or toks[pos][1].startswith("- "):
        items = []
        while pos < len(toks) and toks[pos][0] == indent and (
            toks[pos][1] == "-" or toks[pos][1].startswith("- ")
        ):
            ind, content, block = toks[pos]
            rest = content[1:].lstrip()
            if block is not None and not _KEY.match(rest):
                items.append(block)
                pos += 1
            elif not rest:
                pos += 1
                if pos < len(toks) and toks[pos][0] > indent:
                    val, pos = _parse(toks, pos, toks[pos][0])
                else:
                    val = None
                items.append(val)
            elif _KEY.match(rest) and not rest.startswith(("[", "{")):
                col = ind + len(content) - len(rest)
                toks[pos] = [col, rest, block]
                val, pos = _parse(toks, pos, col)
                items.append(val)
            else:
                items.append(_scalar(rest))
                pos += 1
        return items, pos
    out: dict = {}
    while pos < len(toks) and toks[pos][0] == indent:
        ind, content, block = toks[pos]
        if content.startswith("- "):
            break
        m = _KEY.match(content)
        if not m:
            raise ValueError(f"can't read the line {content!r}")
        key = _scalar(m.group(1))
        rest = (m.group(2) or "").strip()
        pos += 1
        if block is not None:
            out[key] = block
        elif rest:
            out[key] = _scalar(rest)
        elif pos < len(toks) and (
            toks[pos][0] > indent
            or (toks[pos][0] == indent and toks[pos][1].startswith("-"))
        ):
            out[key], pos = _parse(toks, pos, toks[pos][0])
        else:
            out[key] = None
    return out, pos


def read_yaml(path: Path) -> dict:
    toks = _tokens(path.read_text(encoding="utf-8-sig"))
    if not toks:
        return {}
    data, pos = _parse(toks, 0, toks[0][0])
    if pos != len(toks) or not isinstance(data, dict):
        near = toks[min(pos, len(toks) - 1)][1]
        raise ValueError(f"check the indentation near {near!r}")
    return data


# ------------------------------------------------- workflow helpers
def events(wf: dict) -> dict:
    """{'push': {...settings...}, 'pull_request': {...}} for the `on:` key."""
    on = wf.get("on", wf.get("true"))
    if isinstance(on, str):
        return {on: {}}
    if isinstance(on, list):
        return {str(e): {} for e in on}
    if isinstance(on, dict):
        return {k: (v if isinstance(v, dict) else {}) for k, v in on.items()}
    return {}


def jobs(wf: dict) -> dict:
    j = wf.get("jobs")
    return j if isinstance(j, dict) else {}


def steps(job: dict) -> list[dict]:
    s = job.get("steps") if isinstance(job, dict) else None
    return [x for x in s if isinstance(x, dict)] if isinstance(s, list) else []


def runs(job: dict) -> list[str]:
    return [str(s["run"]) for s in steps(job) if s.get("run")]


def uses(job: dict) -> list[str]:
    return [str(s["uses"]) for s in steps(job) if s.get("uses")]


def job_events(wf: dict, job: dict) -> set[str]:
    evs = set(events(wf))
    cond = str(job.get("if", "")) if isinstance(job, dict) else ""
    eq = re.findall(r"github\.event_name\s*==\s*['\"](\w+)['\"]", cond)
    ne = re.findall(r"github\.event_name\s*!=\s*['\"](\w+)['\"]", cond)
    if eq:
        evs &= set(eq)
    return evs - set(ne)


def pytest_lines(job: dict) -> list[str]:
    out = []
    for r in runs(job):
        out += [ln for ln in r.splitlines() if re.search(r"\bpytest\b", ln)]
    return out


def is_smoke(line: str) -> bool:
    return bool(re.search(r"-m\s*['\"]?smoke\b", line))


def is_full(line: str) -> bool:
    return not re.search(r"(^|\s)-m(\s|['\"]|$)|-k\s|::", line)


def all_uses(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8-sig")
    found = re.findall(r"^\s*(?:-\s+)?uses:\s*['\"]?([^\s'\"#]+)", text, re.MULTILINE)
    return found


def why_comments(path: Path) -> int:
    text = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    return len(re.findall(r"#\s*why:\s*\S+", text, re.IGNORECASE))


def load_workflow(path: Path, title: str) -> dict | None:
    if not path.exists():
        ok(False, title, f"Create {path.relative_to(path.parents[2])}.")
        return None
    try:
        wf = read_yaml(path)
    except (ValueError, UnicodeDecodeError) as e:
        ok(False, title, f"{path.name} isn't valid YAML here: {e}. Spaces, not tabs.")
        return None
    ok(bool(jobs(wf)), title, "The file needs a `jobs:` section.")
    return wf if jobs(wf) else None


def top_permissions_read(wf: dict) -> bool:
    perms = wf.get("permissions")
    return isinstance(perms, dict) and perms.get("contents") == "read"


# ------------------------------------------------- git helpers
def git(root: Path, *args: str) -> tuple[int, str]:
    return run(["git", *args], cwd=root)


def has_branch(root: Path, name: str) -> bool:
    for ref in (f"refs/heads/{name}", f"refs/remotes/origin/{name}"):
        if git(root, "rev-parse", "--verify", "--quiet", ref)[0] == 0:
            return True
    return False


def main_ref(root: Path) -> str:
    if git(root, "rev-parse", "--verify", "--quiet", "refs/heads/main")[0] == 0:
        return "main"
    return "HEAD"


def show(root: Path, ref: str, path: str) -> str | None:
    rc, out = git(root, "show", f"{ref}:{path}")
    return out if rc == 0 else None


def export(root: Path, ref: str, dest: Path) -> bool:
    """Copy the files of `ref` (not your working folder) into dest."""
    tar = dest.parent / "export.tar"
    rc, _ = git(root, "archive", "--format=tar", "-o", str(tar), ref)
    if rc != 0:
        return False
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar) as t:
        if sys.version_info >= (3, 12):
            t.extractall(dest, filter="data")
        else:  # pragma: no cover
            t.extractall(dest)
    tar.unlink()
    return True


def github_repo(root: Path) -> str | None:
    rc, out = git(root, "remote", "get-url", "origin")
    m = re.search(r"github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?/?$", out.strip())
    return f"{m.group(1)}/{m.group(2)}" if rc == 0 and m else None


# ------------------------------------------------- GitHub helpers (gh)
_gh_state: list[str | None] = []


def gh_problem() -> str | None:
    """None if `gh` can be used; otherwise why not (used as a SKIP hint)."""
    if not _gh_state:
        if OFFLINE:
            _gh_state.append("--offline was given.")
        elif not shutil.which("gh"):
            _gh_state.append(
                "Install the GitHub CLI (https://cli.github.com) and run "
                "`gh auth login`, or check this yourself on your fork's Actions tab."
            )
        elif run(["gh", "auth", "status"], timeout=30)[0] != 0:
            _gh_state.append("Run `gh auth login` first.")
        else:
            _gh_state.append(None)
    return _gh_state[0]


def gh_api(path: str):
    rc, out = run(["gh", "api", "-H", "Accept: application/vnd.github+json", path],
                  timeout=60)
    if rc != 0:
        return None, out.strip()[-200:]
    try:
        return json.loads(out), ""
    except json.JSONDecodeError:
        return None, out.strip()[:200]


def workflow_runs(repo: str, workflow: str | None = None) -> list[dict]:
    base = f"repos/{repo}/actions"
    path = f"{base}/workflows/{workflow}/runs" if workflow else f"{base}/runs"
    data, _ = gh_api(path + "?per_page=100")
    found = (data or {}).get("workflow_runs", []) if isinstance(data, dict) else []
    return sorted(found, key=lambda r: r.get("created_at", ""))


def red_then_green(found: list[dict], event: str | None = None) -> bool:
    seen_red = False
    for r in found:
        if event and r.get("event") != event:
            continue
        if r.get("conclusion") == "failure":
            seen_red = True
        elif r.get("conclusion") == "success" and seen_red:
            return True
    return False


def merged_heads(repo: str) -> set[str]:
    data, _ = gh_api(f"repos/{repo}/pulls?state=closed&per_page=100")
    if not isinstance(data, list):
        return set()
    return {p["head"]["ref"] for p in data if p.get("merged_at")}


def main_rules(repo: str) -> tuple[set[str], set[str]]:
    """(rule types, required check names) that apply to main."""
    data, _ = gh_api(f"repos/{repo}/rules/branches/main")
    types: set[str] = set()
    checks: set[str] = set()
    for rule in data if isinstance(data, list) else []:
        types.add(rule.get("type", ""))
        params = rule.get("parameters") or {}
        for c in params.get("required_status_checks", []):
            checks.add(c.get("context", ""))
    return types, checks


def github_fork(root: Path, what: str) -> str | None:
    """The owner/name of the fork, or None (after a SKIP or FAIL line)."""
    problem = gh_problem()
    if problem:
        report("SKIP", f"GitHub checks for your {what} fork", problem)
        return None
    repo = github_repo(root)
    if not repo:
        report("FAIL", f"`origin` points at your {what} fork on GitHub",
               "`git remote -v` should show github.com/<you>/... as origin.")
        return None
    if repo.lower().startswith("novastack-hq/"):
        report("FAIL", f"`origin` points at your own {what} fork",
               f"origin is {repo}, the team's repository. Fork it and clone "
               "your fork (or `git remote set-url origin <your fork's URL>`).")
        return None
    data, err = gh_api(f"repos/{repo}")
    if data is None:
        report("FAIL", f"GitHub can see your fork {repo}", err)
        return None
    report("PASS", f"Your fork on GitHub: {repo}")
    return repo


# ------------------------------------------------- running tests in a copy
def interpreter(candidates: list[Path], need: str) -> list[str] | None:
    names = [c / ".venv" / "bin" / "python" for c in candidates]
    names += [c / ".venv" / "Scripts" / "python.exe" for c in candidates]
    names.append(Path(sys.executable))
    for py in names:
        if py.exists() and run([str(py), "-c", f"import {need}"], timeout=60)[0] == 0:
            return [str(py)]
    if shutil.which("uv"):
        return ["uv", "run", "--frozen", "--quiet", "python"]
    return None


def pytest_in(copy: Path, py: list[str], *args: str,
              src: bool = False) -> tuple[int, str]:
    env = {"PYTHONDONTWRITEBYTECODE": "1"}
    if src:
        env["PYTHONPATH"] = str(copy / "src")
    return run([*py, "-m", "pytest", "-p", "no:cacheprovider", *args],
               cwd=copy, env=env, timeout=600)


def summary(out: str) -> str:
    lines = [ln for ln in out.strip().splitlines() if ln.strip()]
    return lines[-1].strip("= ") if lines else "(no output)"


def count(out: str, word: str) -> int:
    m = re.search(rf"(\d+) {word}", out)
    return int(m.group(1)) if m else 0


def collected(out: str) -> int:
    m = re.search(r"(\d+)(?:/\d+)? tests? collected", out)
    return int(m.group(1)) if m else -1


# ------------------------------------------------- Part 0 (all levels)
def exercise() -> None:
    path = ROOT / ".github" / "workflows" / "exercise.yml"
    if not path.exists():
        report("SKIP", "(optional) Part 0: .github/workflows/exercise.yml",
               "Do the warm-up (ORD-384) if you have ten minutes.")
        return
    text = path.read_text(encoding="utf-8-sig")
    try:
        evs = events(read_yaml(path))
    except ValueError:
        evs = {}
    need = {
        "no ____ left": not re.search(r":\s*____", text),
        "on: push": "push" in evs,
        "runs-on: ubuntu-latest": bool(re.search(r"runs-on:\s*ubuntu-latest", text)),
        "pip install -r exercise/requirements.txt": bool(
            re.search(r"pip install .*-r\s+exercise/requirements\.txt", text)
        ),
        "python -m pytest exercise": bool(re.search(r"pytest\s+exercise", text)),
    }
    missing = [k for k, v in need.items() if not v]
    ok(not missing, "(optional) Part 0: the exercise workflow is finished",
       "Still missing: " + "; ".join(missing))


# ---------------------------------------------------------------- beginner
def bad_menu(copy: Path) -> None:
    menu_path = copy / "menu.json"
    menu = json.loads(menu_path.read_text(encoding="utf-8"))
    menu[0]["price"] = "5.2O"  # letter O, like Mei's 4.5O
    menu_path.write_text(json.dumps(menu, indent=2, ensure_ascii=False),
                         encoding="utf-8")


def hidden_price_check(ref: str, tmp: Path) -> None:
    """Your tests must pass on main and fail on a copy with a bad price."""
    clean, broken = tmp / "clean", tmp / "broken"
    if not export(ROOT, ref, clean):
        ok(False, "Hidden check: your tests catch a bad price",
           "Commit your work first (git couldn't export main).")
        return
    shutil.copytree(clean, broken)
    bad_menu(broken)
    py = interpreter([ROOT], "flask, pytest")
    if not py:
        report("SKIP", "Hidden check: your tests catch a bad price",
               "Run `uv sync` (or pip install -r requirements-dev.txt) first.")
        return
    rc1, out1 = pytest_in(clean, py, "tests")
    ok(rc1 == 0, "Hidden check: your tests pass on main's menu",
       f"On a copy of main: {summary(out1)}")
    rc2, out2 = pytest_in(broken, py, "tests")
    ok(rc2 == 1 and count(out2, "failed") >= 1,
       "Hidden check: your tests fail when a price is '5.2O' (letter O)",
       f"I broke M01's price in a copy and ran your tests: {summary(out2)}. "
       "Add the price test from Step 2 (it must check every item).")


def beginner() -> None:
    sheet_path = ROOT / "lab6" / "BEGINNER.md"
    if not sheet_path.exists():
        ok(False, "Answer sheet lab6/BEGINNER.md exists",
           "Run this from the root of your novastack-menu folder.")
        return
    sheet = answers(sheet_path)
    exercise()

    # ---- the answer sheet
    ok(number(sheet.get("B1")) == 5,
       "B1: how many tests passed on your laptop before you added one",
       "Run `uv run pytest` on a fresh `main` and read the last line.")
    tests_now = (ROOT / "tests" / "test_menu.py")
    test_text = tests_now.read_text(encoding="utf-8") if tests_now.exists() else ""
    b2 = sheet.get("B2", "").split("::")[-1].split()[0] if sheet.get("B2") else ""
    ok(bool(b2) and "price" in b2.lower() and f"def {b2}(" in test_text,
       "B2: the name of the test that went red on Mei's change",
       "Copy the test's name from the FAILED line of the log (after the ::).")
    ok("ubuntu" in sheet.get("B3", "").lower(),
       "B3: the operating system GitHub's machine ran",
       "Open a run, click the job, expand `Set up job` and find the "
       "operating system's name.")
    ok("gh013" in sheet.get("B4", "").lower(),
       "B4: the rule-violation code GitHub gave for the refused push",
       "Scroll up in the terminal to the `remote: error:` line after `git push`.")
    ok(sheet.get("B5", "").strip().strip("`'\"").lower() == "test",
       "B5: the name of the check your ruleset requires",
       "It is the job's name in ci.yml (the key under `jobs:`).")
    b6 = sheet.get("B6", "").lower()
    ok(words(b6) >= 6 and bool(re.search(r"test|check|name|spell|review|human", b6)),
       "B6: why no test caught the spelling mistake, in your own words",
       "One or two sentences: what do the tests look at, and what don't they?")

    # ---- the workflow file (working folder)
    wf = load_workflow(ROOT / ".github" / "workflows" / "ci.yml",
                       ".github/workflows/ci.yml exists and has jobs")
    if wf:
        evs = events(wf)
        push = evs.get("push", {}) or {}
        branches = push.get("branches") if isinstance(push, dict) else None
        main_ok = branches is None or "main" in (
            branches if isinstance(branches, list) else [branches]
        )
        ok("pull_request" in evs and "push" in evs and main_ok,
           "ci.yml runs on every pull request and on a push to main",
           "on: pull_request:, and push: with branches: [main].")
        ok(top_permissions_read(wf),
           "ci.yml lets the job only read the repository (permissions)",
           "Add `permissions:` with `contents: read` at the top level.")
        job = jobs(wf).get("test")
        ok(isinstance(job, dict),
           "ci.yml has a job called `test` (the name the ruleset asks for)",
           "Name the job `test` under `jobs:`.")
        job = job if isinstance(job, dict) else {}
        ok(any(u.startswith("actions/checkout@") for u in uses(job))
           and any(u.startswith("astral-sh/setup-uv@") for u in uses(job)),
           "The test job checks out the code and installs uv",
           "Steps: uses: actions/checkout@..., then uses: astral-sh/setup-uv@...")
        ok(any(re.search(r"\buv sync\b", r) for r in runs(job))
           and bool(pytest_lines(job)),
           "The test job runs `uv sync` and then pytest",
           "run: uv sync --locked, then run: uv run pytest.")

    # ---- Git: branches and what is on main
    ok(has_branch(ROOT, "price-test") and has_branch(ROOT, "autumn-special"),
       "Your branches price-test and autumn-special exist",
       "Make each change on its own branch: `git switch -c price-test`.")
    ref = main_ref(ROOT)
    ok(show(ROOT, ref, ".github/workflows/ci.yml") is not None,
       "ci.yml is merged into main",
       "Merge the add-ci pull request on GitHub, then `git switch main` "
       "and `git pull`.")
    menu_text = show(ROOT, ref, "menu.json")
    try:
        menu = json.loads(menu_text or "[]")
    except json.JSONDecodeError:
        menu = []
    d05 = [m for m in menu if isinstance(m, dict) and m.get("sku") == "D05"]
    ok(bool(d05) and d05[0].get("price") == "4.50"
       and d05[0].get("name") == "Pumpkin spice latte",
       "main has the autumn special D05, spelt right, at 4.50",
       "Merge autumn-special after both fixes (price, then spelling), "
       "then `git pull` on main.")

    tmp = Path(tempfile.mkdtemp(prefix="lab6check-"))
    try:
        hidden_price_check(ref, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # ---- GitHub
    repo = github_fork(ROOT, "novastack-menu")
    if not repo:
        return
    found = workflow_runs(repo, "ci.yml")
    ok(bool(found), "GitHub Actions ran ci.yml in your fork",
       "Enable workflows on your fork's Actions tab, then push.")
    ok(red_then_green(found),
       "Your fork has a red ci.yml run followed by a green one",
       "Push Mei's change (red), then the fix (green), on autumn-special.")
    on_main = [r for r in found if r.get("head_branch") == "main"
               and r.get("event") == "push"]
    ok(bool(on_main) and on_main[-1].get("conclusion") == "success",
       "The latest ci.yml run on main is green",
       "Open the Actions tab, click the latest run on main and read the log.")
    heads = merged_heads(repo)
    ok({"price-test", "autumn-special"} <= heads,
       "price-test and autumn-special were merged by pull requests in your fork",
       f"Merged so far: {', '.join(sorted(heads)) or 'none'}. Open each pull "
       "request with base repository = your fork.")
    types, checks = main_rules(repo)
    ok("pull_request" in types and "test" in checks,
       "A ruleset on main needs a pull request and the `test` check",
       "Settings, Rules, Rulesets, New branch ruleset (protect-main).")


# ------------------------------------------------------------ intermediate
def intermediate() -> None:
    sheet_path = ROOT / "lab6" / "INTERMEDIATE.md"
    if not sheet_path.exists():
        ok(False, "Answer sheet lab6/INTERMEDIATE.md exists",
           "Run this from the root of your novastack-menu folder.")
        return
    sheet = answers(sheet_path)
    exercise()
    path = ROOT / ".github" / "workflows" / "ci.yml"
    wf = load_workflow(path, ".github/workflows/ci.yml exists and has jobs")
    if not wf:
        return
    all_jobs = jobs(wf)
    lint, test = all_jobs.get("lint"), all_jobs.get("test")
    lint = lint if isinstance(lint, dict) else {}
    test = test if isinstance(test, dict) else {}

    lint_cmds = [r for r in runs(lint) if re.search(r"\bruff\b.*\bcheck\b", r)]
    ok(bool(lint_cmds), "A job called `lint` runs `ruff check`",
       "Add a second job, `lint`, whose last step runs `uv run ruff check ...`.")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    pinned = bool(re.search(r"^\s*['\"]ruff", pyproject, re.MULTILINE)) or any(
        re.search(r"uvx\s+ruff@\d", c) for c in lint_cmds
    )
    ok(pinned, "Ruff's version is pinned (in uv.lock, or uvx ruff@<version>)",
       "`uv add --dev ruff` puts it in the dev group and locks the version.")

    matrix = (test.get("strategy") or {}).get("matrix") if test else None
    versions: list[str] = []
    if isinstance(matrix, dict):
        for v in matrix.values():
            if isinstance(v, list):
                versions += [str(x) for x in v]
    test_text = json.dumps(test)
    ok({"3.12", "3.13"} <= set(versions) and "matrix." in test_text,
       "The test job runs on Python 3.12 and 3.13 (a matrix that is used)",
       "strategy: matrix: python-version: [\"3.12\", \"3.13\"], and use "
       "${{ matrix.python-version }} (e.g. env: UV_PYTHON: ...).")
    ok(any("uv sync --locked" in r for r in runs(test)) and bool(pytest_lines(test)),
       "The test job runs `uv sync --locked` and pytest",
       "--locked fails the job if uv.lock is out of date with pyproject.toml.")

    writes = [
        name for name, job in all_jobs.items()
        if isinstance(job, dict) and "write" in json.dumps(job.get("permissions"))
        and not any("docker push" in r for r in runs(job))
    ]
    ok(top_permissions_read(wf) and "write" not in json.dumps(wf.get("permissions"))
       and not writes,
       "Least privilege: contents: read, and no job asks to write",
       f"Top-level `permissions: contents: read`. Jobs asking to write: "
       f"{', '.join(writes) or 'none'}.")

    conc = wf.get("concurrency")
    conc = conc if isinstance(conc, dict) else {}
    cancel = str(conc.get("cancel-in-progress", "")).lower()
    ok(bool(conc.get("group"))
       and (cancel == "true" or "pull_request" in cancel),
       "concurrency: a new push cancels the older run of the same branch",
       "concurrency: group: ${{ github.workflow }}-${{ github.ref }}, "
       "cancel-in-progress: true")

    n = why_comments(path)
    ok(n >= 5, "ci.yml has a `# why:` comment for at least 5 changes",
       f"Found {n}. One per change: lint, cache, matrix, permissions, pins, "
       "concurrency.")

    # hidden: every `uses:` is pinned to a full commit SHA
    used = all_uses(path)
    loose = [u for u in used if not SHA.match(u.rsplit("@", 1)[-1])]
    ok(bool(used) and not loose,
       "Hidden check: every `uses:` is pinned to a 40-character commit SHA",
       f"Not pinned: {', '.join(loose) or 'no uses: found'}. Write "
       "owner/action@<full SHA> # vX.Y.Z")
    checkout = [u.rsplit("@", 1)[-1] for u in used if u.startswith("actions/checkout@")]
    s1 = sheet.get("S1", "").strip().lower()
    ok(bool(SHA.match(s1)) and s1 in checkout,
       "S1: the SHA you pinned actions/checkout to",
       "Paste the 40 characters after `actions/checkout@` in your ci.yml.")

    # hidden: your lint command really passes (if Ruff is installed locally)
    ruff = None
    for c in (ROOT / ".venv" / "bin" / "ruff", ROOT / ".venv" / "Scripts" / "ruff.exe"):
        if c.exists():
            ruff = str(c)
    if lint_cmds and not ruff:
        report("SKIP", "Hidden check: your lint command passes on main",
               "`uv add --dev ruff` then `uv sync`, so I can run it.")
    elif lint_cmds:
        args = re.split(r"\bruff\s+check\b", lint_cmds[0].splitlines()[-1])[-1].split()
        tmp = Path(tempfile.mkdtemp(prefix="lab6check-"))
        try:
            if export(ROOT, main_ref(ROOT), tmp / "main"):
                rc, out = run([ruff, "check", "--no-cache", *(args or ["."])],
                              cwd=tmp / "main")
                ok(rc == 0, "Hidden check: your lint command passes on main",
                   f"`ruff check {' '.join(args)}` said: {summary(out)}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # ---- answer sheet
    t1, t2 = number(sheet.get("T1")), number(sheet.get("T2"))
    ok(bool(t1 and t2), "T1/T2: the test job's time on a first run and a repeat run",
       "Read the job's duration on the run's summary page, in seconds.")
    ok("cache" in sheet.get("C1", "").lower(),
       "C1: a line from the setup-uv step's log about the cache",
       "Expand the setup-uv step of the repeat run and copy the cache line.")
    ok(number(sheet.get("M1")) == len(versions) and len(versions) >= 2,
       "M1: how many test jobs your matrix makes",
       "One job per Python version in the matrix.")
    r1 = sheet.get("R1", "").lower()
    ok("lint" in r1 and "test" in r1,
       "R1: the checks your ruleset requires",
       "Write the check names as GitHub shows them, e.g. lint, test (3.12).")
    filled = sum(1 for k in ("W1", "W2", "W3", "W4", "W5", "W6")
                 if words(sheet.get(k)) >= 5)
    ok(filled >= 5, "W1-W6: why you made each change (at least five answered)",
       f"{filled} answered with 5 or more words. AI may draft; you must justify.")

    # ---- GitHub
    repo = github_fork(ROOT, "novastack-menu")
    if not repo:
        return
    found = [r for r in workflow_runs(repo, "ci.yml")
             if r.get("head_branch") == "main" and r.get("event") == "push"]
    latest = found[-1] if found else {}
    ok(latest.get("conclusion") == "success", "The latest ci.yml run on main is green",
       "Merge your pull request, then look at the Actions tab.")
    if latest:
        data, _ = gh_api(f"repos/{repo}/actions/runs/{latest['id']}/jobs")
        names = [j.get("name", "") for j in (data or {}).get("jobs", [])]
        ok("lint" in names and sum(n.startswith("test") for n in names) >= 2,
           "That run had a lint job and one test job per Python version",
           f"Jobs in the run: {', '.join(names) or 'none'}.")
    _, checks = main_rules(repo)
    ok("lint" in checks and any(c.startswith("test") for c in checks),
       "Your ruleset on main requires lint and the test checks",
       f"Required now: {', '.join(sorted(checks)) or 'none'}. Edit protect-main "
       "and add the checks (each must have run once).")
    real = []
    for u in used:
        name, _, ref = u.rpartition("@")
        if SHA.match(ref):
            owner_repo = "/".join(name.split("/")[:2])
            data, _ = gh_api(f"repos/{owner_repo}/commits/{ref}")
            real.append(bool(data))
    ok(bool(real) and all(real), "Each pinned SHA is a real commit of that action",
       "Copy the SHA from the action's release page (Tags), not from memory.")


# ---------------------------------------------------------------- advanced
HIDDEN_TEST = '''
"""Hidden lab check: the ORD-317 baskets (written by check_lab6.py)."""

from novastack_orders.domain.customer import LoyaltyTier
from novastack_orders.pricing.calculator import PriceCalculator
from tests.factories import WEDNESDAY_LUNCH, gbp, make_basket, make_customer

BASKET = (("M01", 1), ("S01", 1), ("D01", 1), ("D02", 1))


def _price(tier):
    customer = make_customer(tier=tier)
    calc = PriceCalculator.default()
    return calc.calculate(make_basket(*BASKET), customer, WEDNESDAY_LUNCH)


def test_lab6_silver_loyalty_once():
    result = _price(LoyaltyTier.SILVER)
    assert result.discount_codes().count("LOYALTY") == 1
    assert result.total == gbp("7.29")


def test_lab6_gold_loyalty_once():
    result = _price(LoyaltyTier.GOLD)
    assert result.discount_codes().count("LOYALTY") == 1
    assert result.total == gbp("6.88")
'''


def hidden_orders_checks(orders: Path, ref: str, tmp: Path,
                         sheet: dict[str, str]) -> None:
    """Run the suite, and two baskets of mine, on a copy of main."""
    copy = tmp / "orders"
    if not export(orders, ref, copy):
        ok(False, "Hidden check: the suite on main", "Commit your work first.")
        return
    py = interpreter([orders, ROOT], "pytest")
    if not py:
        report("SKIP", "Hidden checks: the suite on main",
               "Run `uv sync` in your Orders clone first.")
        return
    _, out = pytest_in(copy, py, "--collect-only", src=True)
    total = collected(out)
    _, out = pytest_in(copy, py, "--collect-only", "-m", "smoke", src=True)
    smoke = collected(out)
    rc, out = pytest_in(copy, py, src=True)
    ok(rc == 0 and count(out, "passed") == total and total >= 218,
       "Hidden check: the full suite on main passes, with nothing xfailed",
       f"On a copy of main: {summary(out)}")
    hidden = copy / "tests" / "test_lab6_hidden.py"
    hidden.write_text(HIDDEN_TEST, encoding="utf-8")
    rc, out = pytest_in(copy, py, "tests/test_lab6_hidden.py", src=True)
    ok(rc == 0,
       "Hidden check: Silver pays 7.29 and Gold 6.88 for Grace's basket",
       f"{summary(out)}. Apply the loyalty discount once, after promotions.")
    ok(number(sheet.get("O1")) == smoke,
       "O1: how many tests `uv run pytest -m smoke` selects",
       "Add up passed and xfailed on the summary line (not deselected).")
    ok(number(sheet.get("O3")) == total, "O3: how many tests the full suite has",
       "Run `uv run pytest` and add up the summary line.")


def advanced(orders: Path | None) -> None:
    sheet_path = ROOT / "lab6" / "ADVANCED.md"
    if not sheet_path.exists():
        ok(False, "Answer sheet lab6/ADVANCED.md exists",
           "Run this from the root of your novastack-menu folder.")
        return
    sheet = answers(sheet_path)
    exercise()
    if orders is None:
        ok(False, "--repo points at your clone of novastack-orders",
           "uv run tools/check_lab6.py advanced --repo ../novastack-orders")
        return
    orders = orders.expanduser().resolve()
    pyproject = orders / "pyproject.toml"
    is_orders = pyproject.exists() and (
        'name = "novastack-orders"' in pyproject.read_text(encoding="utf-8")
    )
    ok(is_orders, f"--repo is a novastack-orders clone ({orders})",
       "Give the folder you cloned your Orders fork into.")
    if not is_orders:
        return

    # ---- the workflow (all files in .github/workflows)
    wf_dir = orders / ".github" / "workflows"
    files = sorted([*wf_dir.glob("*.yml"), *wf_dir.glob("*.yaml")])
    parsed: list[tuple[Path, dict]] = []
    for f in files:
        try:
            parsed.append((f, read_yaml(f)))
        except (ValueError, UnicodeDecodeError) as e:
            ok(False, f"{f.name} is valid YAML", str(e))
    ok(bool(parsed), "Orders has a workflow in .github/workflows/",
       "Create .github/workflows/ci.yml in your Orders clone.")
    if parsed:
        smoke_on_push = full_on_pr = full_on_push = filtered = False
        locked = setup_uv = perms = True
        for _, wf in parsed:
            push = events(wf).get("push")
            if isinstance(push, dict) and (push.get("branches") or push.get("paths")):
                filtered = True
            perms = perms and top_permissions_read(wf)
            for job in jobs(wf).values():
                if not isinstance(job, dict) or not pytest_lines(job):
                    continue
                evs = job_events(wf, job)
                lines = pytest_lines(job)
                smoke_on_push |= "push" in evs and any(is_smoke(ln) for ln in lines)
                full_on_pr |= "pull_request" in evs and any(is_full(ln) for ln in lines)
                full_on_push |= "push" in evs and any(is_full(ln) for ln in lines)
                locked = locked and any("uv sync --locked" in r for r in runs(job))
                setup_uv = setup_uv and any(u.startswith("astral-sh/setup-uv@")
                                            for u in uses(job))
        ok(smoke_on_push and not filtered,
           "ADR 0004: every push runs the smoke tier (pytest -m smoke)",
           "A job that runs on push (all branches) with `uv run pytest -m smoke`.")
        ok(full_on_pr, "ADR 0004: pull requests run the full suite",
           "A job that runs on pull_request with plain `uv run pytest`.")
        ok(not full_on_push,
           "ADR 0004: a push alone doesn't run the full suite",
           "Limit the full-suite job with if: github.event_name == 'pull_request'.")
        ok(locked and setup_uv, "Every test job installs uv and runs uv sync --locked",
           "uses: astral-sh/setup-uv@..., then run: uv sync --locked.")
        ok(perms, "Every workflow file sets permissions: contents: read",
           "Least privilege: the jobs only need to read the code.")

    # ---- what is on main
    ref = main_ref(orders)
    test_file = "tests/unit/pricing/test_calculator.py"
    main_tests = show(orders, ref, test_file) or ""
    marker = re.search(r"xfail\([^)]*ORD-317", main_tests)
    ok("def test_loyalty_discount_applied_once" in main_tests and not marker,
       "On main, Dan's ORD-317 test is still there and its xfail marker is gone",
       "Fix the bug AND delete the @pytest.mark.xfail line (keep the test). "
       "Merge, then `git pull`.")

    tmp = Path(tempfile.mkdtemp(prefix="lab6check-"))
    try:
        hidden_orders_checks(orders, ref, tmp, sheet)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    ok("xpass(strict)" in sheet.get("O2", "").lower().replace(" ", ""),
       "O2: what pytest printed when the fix was in but the marker wasn't gone",
       "Read the FAILURES section: the word in square brackets.")
    filled = sum(1 for k in ("W1", "W2", "W3") if words(sheet.get(k)) >= 6)
    ok(filled == 3, "W1-W3: your design reasons, in your own words",
       f"{filled} of 3 answered with 6 or more words.")

    # ---- GitHub: the Orders fork
    repo = github_fork(orders, "novastack-orders")
    if repo:
        found = workflow_runs(repo)
        ok(any(r.get("event") == "push" and r.get("conclusion") == "success"
               for r in found),
           "Orders: a push run is green", "Push a branch and watch the smoke job.")
        ok(red_then_green(found, "pull_request"),
           "Orders: a pull request went red (XPASS(strict)) and then green",
           "Push the fix alone first; then remove the marker in a second commit.")
        heads = merged_heads(repo)
        ok(bool(heads), "Orders: your fix was merged by a pull request in your fork",
           "Open the pull request with base repository = your fork, then merge.")

    # ---- optional: publish the menu image
    publish = sheet.get("PUBLISH", "").strip().lower()
    if publish not in ("yes", "y"):
        report("SKIP", "(optional) The menu image is published to ghcr.io",
               "Write `PUBLISH: yes` in lab6/ADVANCED.md to check it.")
        return
    menu_ci = ROOT / ".github" / "workflows" / "ci.yml"
    wf = None
    if menu_ci.exists():
        try:
            wf = read_yaml(menu_ci)
        except (ValueError, UnicodeDecodeError):
            wf = None
    job = jobs(wf or {}).get("publish")
    ok(isinstance(job, dict) and job.get("needs") in ("test", ["test"])
       and "packages" in json.dumps(job.get("permissions")),
       "(optional) The menu's ci.yml has a publish job that needs test",
       "Copy extras/ci.step6.yml to .github/workflows/ci.yml (Demo 3).")
    problem = gh_problem()
    menu_repo = github_repo(ROOT)
    if problem or not menu_repo:
        report("SKIP", "(optional) The menu image is published to ghcr.io",
               problem or "origin isn't a GitHub fork.")
        return
    owner = menu_repo.split("/")[0]
    data, err = gh_api(f"users/{owner}/packages/container/novastack-menu")
    if data is None and ("scope" in err.lower() or "403" in err):
        report("SKIP", "(optional) The menu image is published to ghcr.io",
               "Run `gh auth refresh -s read:packages`, then check again.")
    else:
        ok(data is not None, "(optional) The menu image is published to ghcr.io",
           "Merge to main and wait for the publish job; see Demo 3.")


def main() -> int:
    global OFFLINE
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("level", choices=["beginner", "intermediate", "advanced"])
    parser.add_argument("--repo", type=Path, help="your novastack-orders clone")
    parser.add_argument("--offline", action="store_true",
                        help="skip every check that asks GitHub")
    args = parser.parse_args()
    OFFLINE = args.offline
    print(f"Lecture 6 lab self-check: {args.level}\n")
    if not (ROOT / "app.py").exists() or not (ROOT / "menu.json").exists():
        report("FAIL", "Run from the root of your novastack-menu folder",
               "cd into the folder that holds app.py and menu.json.")
    elif git(ROOT, "rev-parse", "--git-dir")[0] != 0:
        report("FAIL", "This folder is a Git repository",
               "Clone your fork with `git clone`, don't download a ZIP.")
    elif args.level == "advanced":
        advanced(args.repo)
    else:
        {"beginner": beginner, "intermediate": intermediate}[args.level]()
    p = sum(1 for r in results if r[0] == "PASS")
    f = sum(1 for r in results if r[0] == "FAIL")
    s = sum(1 for r in results if r[0] == "SKIP")
    print(f"\n{p} passed, {f} failed, {s} skipped")
    return 1 if f else 0


if __name__ == "__main__":
    sys.exit(main())
