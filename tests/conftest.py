"""Result tracking for verification checks.

Tests marked ``@pytest.mark.verification("SEC-01", "security")`` are tracked
checks. Evidence recorded with pytest's built-in ``record_property`` fixture
(e.g. ``record_property("tickets_on_server", 1)``) is captured next to each
outcome.

Pass ``--verification-report DIR`` to write:

- ``DIR/verification-results.json``: the full machine-readable record
- ``DIR/verification-results.md``: a human-readable report
- ``DIR/history.jsonl``: one appended summary line per run, so results are
  tracked over time

Without the option nothing is written, so a plain ``pytest`` stays side-effect free.
"""

from __future__ import annotations

import datetime as _dt
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

_RESULTS = pytest.StashKey[List[Dict[str, Any]]]()
_CATEGORY_ORDER = ["security", "idempotency", "integrity"]


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--verification-report",
        metavar="DIR",
        default=None,
        help="write tracked verification results (JSON, Markdown, history) to DIR",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "verification(check_id, category): a tracked check recorded by --verification-report",
    )
    config.stash[_RESULTS] = []


@pytest.fixture
def report_dir(request: pytest.FixtureRequest) -> Optional[Path]:
    """The --verification-report directory, or None when not reporting."""
    value = request.config.getoption("--verification-report")
    if value is None:
        return None
    path = Path(value)
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo) -> Any:
    outcome = yield
    rep = outcome.get_result()
    marker = item.get_closest_marker("verification")
    if marker is None:
        return
    # One record per test: the call phase, or setup if it never got there.
    if not (rep.when == "call" or (rep.when == "setup" and not rep.passed)):
        return
    check_id, category = marker.args
    callspec = getattr(item, "callspec", None)
    if callspec is not None:
        check_id = f"{check_id}[{callspec.id}]"
    doc = (getattr(item, "function", None).__doc__ or "").strip()
    failure = None
    if rep.failed:
        crash = getattr(rep.longrepr, "reprcrash", None)
        failure = crash.message if crash else str(rep.longrepr)[-500:]
    item.config.stash[_RESULTS].append(
        {
            "id": check_id,
            "category": category,
            "test": item.nodeid,
            "claim": doc.split("\n\n")[0].replace("\n", " "),
            "outcome": "error" if rep.when == "setup" and rep.failed else rep.outcome,
            "duration_s": round(rep.duration, 3),
            "evidence": {k: v for k, v in item.user_properties},
            "failure": failure,
        }
    )


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    target = session.config.getoption("--verification-report")
    results = session.config.stash.get(_RESULTS, [])
    if not target or not results:
        return
    out = Path(target)
    out.mkdir(parents=True, exist_ok=True)
    results = sorted(
        results,
        key=lambda r: (_rank(r["category"]), r["id"]),
    )
    summary: Dict[str, Dict[str, int]] = {}
    for r in results:
        bucket = summary.setdefault(r["category"], {"passed": 0, "failed": 0, "skipped": 0, "error": 0})
        bucket[r["outcome"]] = bucket.get(r["outcome"], 0) + 1
    failed = [r["id"] for r in results if r["outcome"] in ("failed", "error")]
    meta = _run_metadata(session, exclude=out)
    verdict = "PASS" if not failed else "FAIL"
    record = {"run": meta, "verdict": verdict, "summary": summary, "checks": results}

    (out / "verification-results.json").write_text(
        json.dumps(record, indent=2, default=str, ensure_ascii=False) + "\n"
    )
    (out / "verification-results.md").write_text(_markdown(record))
    with (out / "history.jsonl").open("a") as fh:
        fh.write(
            json.dumps(
                {
                    "timestamp_utc": meta["timestamp_utc"],
                    "git_commit": meta["git_commit"],
                    "git_dirty": meta["git_dirty"],
                    "verdict": verdict,
                    "total": len(results),
                    "passed": sum(1 for r in results if r["outcome"] == "passed"),
                    "failed": failed,
                },
                default=str,
            )
            + "\n"
        )


def _rank(category: str) -> int:
    return _CATEGORY_ORDER.index(category) if category in _CATEGORY_ORDER else 99


def _git(root: Path, *args: str) -> Optional[str]:
    try:
        return subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, timeout=10, check=True
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def _run_metadata(session: pytest.Session, exclude: Path) -> Dict[str, Any]:
    """Run context. ``git_dirty`` reflects *source* changes only. The report
    directory being written is excluded, or every run would count as dirty."""
    root = Path(session.config.rootpath)
    pathspec = ["--", "."]
    try:
        pathspec.append(f":(exclude){exclude.resolve().relative_to(root.resolve())}")
    except ValueError:
        pass  # report dir outside the repo: nothing to exclude
    status = _git(root, "status", "--porcelain", *pathspec)
    try:
        import requests

        requests_version = requests.__version__
    except ImportError:  # pragma: no cover
        requests_version = None
    return {
        "timestamp_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "git_commit": _git(root, "rev-parse", "--short", "HEAD"),
        "git_dirty": bool(status) if status is not None else None,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "pytest": pytest.__version__,
        "requests": requests_version,
        "command": "pytest " + " ".join(session.config.invocation_params.args),
    }


def _markdown(record: Dict[str, Any]) -> str:
    meta, summary = record["run"], record["summary"]
    lines = [
        "# Custom tool verification: external service (security, idempotency, integrity)",
        "",
        f"**Verdict: {record['verdict']}**. Run {meta['timestamp_utc']}, commit "
        f"`{meta['git_commit']}`{' (uncommitted changes)' if meta['git_dirty'] else ''}, "
        f"Python {meta['python']}, requests {meta['requests']}.",
        "",
        "Generated by `proof/run-custom-tool-verification.sh`. Don't edit by hand; "
        "re-run the script. `history.jsonl` keeps one line per run.",
        "",
        "| Category | Passed | Failed | Skipped |",
        "|---|---|---|---|",
    ]
    for cat in sorted(summary, key=_rank):
        s = summary[cat]
        lines.append(f"| {cat} | {s.get('passed', 0)} | {s.get('failed', 0) + s.get('error', 0)} | {s.get('skipped', 0)} |")
    current = None
    for r in record["checks"]:
        if r["category"] != current:
            current = r["category"]
            lines += ["", f"## {current.capitalize()}", "", "| ID | Result | Claim | Evidence |", "|---|---|---|---|"]
        mark = {"passed": "PASS", "failed": "**FAIL**", "error": "**ERROR**"}.get(r["outcome"], r["outcome"].upper())
        evidence = "<br>".join(
            f"`{k}` = {_cell(v)}" for k, v in r["evidence"].items()
        ) or "-"
        if r["failure"]:
            evidence += f"<br>failure: {_cell(r['failure'])}"
        lines.append(f"| {r['id']} | {mark} | {_cell(r['claim'])} | {evidence} |")
    return "\n".join(lines) + "\n"


def _cell(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str, ensure_ascii=False)
    text = text.replace("|", "\\|").replace("\n", " ")
    return text if len(text) <= 160 else text[:157] + "..."
