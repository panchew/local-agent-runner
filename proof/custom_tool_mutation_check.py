#!/usr/bin/env python3
"""Mutation check for the external-service custom tool verification suite.

A passing security test only means something if it would fail without the
protection it claims to verify. For each protection in
``examples/ticket_service/ticket_tools.py`` this script:

1. copies the repo to a temp dir (the real source is never modified)
2. disables that one protection with an exact text substitution
3. runs ``tests/test_ticket_service_tool.py`` with ``--verification-report``
4. records which checks failed

A mutation is **killed** when every check expected to catch it fails. A
**survivor** means a protection isn't actually verified by the suite.

Usage: proof/custom_tool_mutation_check.py OUT_DIR
Writes OUT_DIR/mutation-results.json and OUT_DIR/mutation-results.md.
Exit code 0 only if the baseline passes and every mutation is killed.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOL = "examples/ticket_service/ticket_tools.py"
SUITE = "tests/test_ticket_service_tool.py"

# (id, protection disabled, file, exact old text, replacement, checks expected to fail)
MUTATIONS = [
    ("M01", "no redaction of secrets in tool output", TOOL,
     "    for secret in secrets:\n        if secret:\n            text = text.replace(secret, REDACTED)\n",
     "", ["SEC-01"]),
    ("M02", "truncate service error before redacting (partial-key leak)", TOOL,
     "            detail = redact(str(detail), [self.api_key, self.signing_secret])\n",
     "            detail = str(detail)\n", ["SEC-01"]),
    ("M03", "follow redirects", TOOL,
     "allow_redirects=False", "allow_redirects=True", ["SEC-04"]),
    ("M04", "no ticket_id format validation", TOOL,
     "if not isinstance(ticket_id, str) or not TICKET_ID.fullmatch(ticket_id):",
     "if not isinstance(ticket_id, str):", ["SEC-03"]),
    ("M05", "allow plain http to any host", TOOL,
     'if parts.scheme == "http" and not _is_loopback(parts.hostname):',
     "if False:", ["SEC-05"]),
    ("M06", "no streaming size cap (only the declared Content-Length check remains)", TOOL,
     "            if size > self.max_response_bytes:\n",
     "            if False:\n", ["SEC-09"]),
    ("M07", "fresh idempotency key per tool call (repeat calls not deduplicated)", TOOL,
     "    material = scope.encode()", "    material = uuid.uuid4().bytes + scope.encode()",
     ["IDEM-01", "IDEM-06"]),
    ("M07b", "fresh idempotency key per transport retry", TOOL,
     "            last = attempt == self.max_attempts\n",
     "            last = attempt == self.max_attempts\n"
     "            if idempotency_key:\n"
     "                headers[\"Idempotency-Key\"] = uuid.uuid4().hex\n",
     ["IDEM-02", "IDEM-03"]),
    ("M08", "no idempotency key sent at all", TOOL,
     '            headers["Idempotency-Key"] = idempotency_key\n', "            pass\n",
     ["IDEM-01", "IDEM-02"]),
    ("M09", "no transport retries", TOOL,
     "            last = attempt == self.max_attempts\n", "            last = True\n",
     ["IDEM-02", "IDEM-03", "IDEM-04"]),
    ("M10", "idempotency key not scoped to the run", TOOL,
     "    material = scope.encode() +", "    material = b'' +", ["IDEM-08"]),
    ("M11", "no response signature verification", TOOL,
     "        if not hmac.compare_digest(signature, _sign(self.signing_secret, content)):",
     "        if False:", ["INT-02", "INT-03"]),
    ("M12", "no semantic check that the returned ticket matches the request", TOOL,
     'if ticket.get("title") != title or ticket.get("priority") != priority:', "if False:",
     ["INT-04"]),
    ("M13", "secrets passed to the model-facing schema", TOOL,
     '"title": {"type": "string", "description": "Short summary, max 200 chars."},',
     '"title": {"type": "string", "description": "Short summary. Auth: " + api_key},',
     ["SEC-01"]),
]


def run_suite(root: Path, report: Path) -> dict:
    subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", SUITE,
         "--verification-report", str(report)],
        cwd=root, capture_output=True, text=True, timeout=600,
    )
    data = json.loads((report / "verification-results.json").read_text())
    return {
        "failed": sorted({c["id"].split("[")[0] for c in data["checks"]
                          if c["outcome"] in ("failed", "error")}),
        "total": len(data["checks"]),
    }


def copy_repo(dest: Path) -> Path:
    root = dest / "repo"
    shutil.copytree(REPO, root, ignore=shutil.ignore_patterns(
        ".git", "__pycache__", "*.egg-info", ".pytest_cache", "artifacts", "run-workspace"))
    return root


def main(out_dir: str) -> int:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        root = copy_repo(Path(tmp))
        baseline = run_suite(root, Path(tmp) / "baseline")
        print(f"baseline: {baseline['total']} checks, failed={baseline['failed'] or 'none'}")
        original = {}
        for mid, what, rel, old, new, expected in MUTATIONS:
            path = root / rel
            text = original.setdefault(rel, path.read_text())
            if text.count(old) != 1:
                raise SystemExit(f"{mid}: mutation anchor not found exactly once in {rel}")
            path.write_text(text.replace(old, new))
            try:
                outcome = run_suite(root, Path(tmp) / mid)
            finally:
                path.write_text(text)
            missed = [e for e in expected if e not in outcome["failed"]]
            status = "killed" if not missed else "SURVIVED"
            results.append({"id": mid, "protection_disabled": what, "expected_to_fail": expected,
                            "actually_failed": outcome["failed"], "status": status,
                            "expected_but_passed": missed})
            print(f"{mid} {status:8} {what}  ->  failed: {', '.join(outcome['failed']) or 'none'}")

    ok = not baseline["failed"] and all(r["status"] == "killed" for r in results)
    record = {"baseline": baseline, "verdict": "PASS" if ok else "FAIL", "mutations": results}
    (out / "mutation-results.json").write_text(json.dumps(record, indent=2) + "\n")
    lines = [
        "# Mutation check: are the verification checks sensitive?",
        "",
        f"**Verdict: {record['verdict']}**. Baseline: {baseline['total']} checks, "
        f"{len(baseline['failed'])} failing. Each row disables one protection in "
        f"`{TOOL}` and re-runs the suite. *killed* means the expected checks went red.",
        "",
        "| ID | Protection disabled | Expected to fail | Actually failed | Status |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(f"| {r['id']} | {r['protection_disabled']} | {', '.join(r['expected_to_fail'])} "
                     f"| {', '.join(r['actually_failed']) or 'none'} | "
                     f"{'killed' if r['status'] == 'killed' else '**SURVIVED**'} |")
    (out / "mutation-results.md").write_text("\n".join(lines) + "\n")
    print(f"MUTATION CHECK: {record['verdict']}")
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    sys.exit(main(sys.argv[1]))
