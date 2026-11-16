"""Live proof: a real local model uses the ticket tools against the fake service.

The offline suite (tests/test_ticket_service_tool.py) scripts the model. This
script runs the same tools with a real Ollama model, over real HTTP, and
forces a dropped connection after the first commit. It then checks the
service's final state against the run:

    python examples/ticket_service/live_proof.py --model qwen2.5-coder:14b --out DIR

Writes DIR/live-proof.json (checks + the full Result). Exit 0 only if every check passes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fake_service import DROP_AFTER_COMMIT, FakeTicketService
from ticket_tools import make_ticket_tools

from local_agent_runner import ToolPermissions, run

API_KEY = "sk-live-proof-3b8e1f0c9a7d2e64"
SIGNING_SECRET = "whsec-live-proof-5c2a9e7f1d0b"
TITLE = "Printer on floor 3 is jammed"
TASK = (
    f"Create a support ticket titled '{TITLE}' with priority high. Then fetch that "
    "ticket by its id to confirm it exists. Finally reply with the ticket id and priority."
)


def main(argv: Optional[List[str]] = None, client: Any = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default="qwen2.5-coder:14b")
    parser.add_argument("--endpoint", default="http://localhost:11434")
    parser.add_argument("--max-iterations", type=int, default=8)
    parser.add_argument("--out", help="directory for live-proof.json")
    args = parser.parse_args(argv)

    with FakeTicketService(API_KEY, SIGNING_SECRET) as service:
        service.inject(DROP_AFTER_COMMIT)  # first create commits, then the reply is lost
        result = run(
            args.model, TASK, ToolPermissions(),
            endpoint=args.endpoint, max_iterations=args.max_iterations,
            custom_tools=make_ticket_tools(service.base_url, API_KEY, SIGNING_SECRET, backoff=0.1),
            client=client,
        )
        dump = json.dumps(result.to_dict(), ensure_ascii=False)
        called = [s["tool_call"]["name"] for s in result.transcript]
        checks: Dict[str, bool] = {
            "run completed": result.status == "completed",
            "model called create_ticket": "create_ticket" in called,
            "model called get_ticket": "get_ticket" in called,
            "dropped connection was exercised": any(r.status is None for r in service.posts()),
            "exactly one ticket on the service": len(service.tickets) == 1,
            "ticket has the requested title and priority": any(
                t["title"] == TITLE and t["priority"] == "high" for t in service.tickets.values()
            ),
            "every request carried a valid signature": all(
                r.signature_valid for r in service.requests_log
            ),
            "no secret in the Result": API_KEY not in dump and SIGNING_SECRET not in dump,
        }
        record = {
            "model": args.model,
            "verdict": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks,
            "service_tickets": service.tickets,
            "service_requests": [
                {"method": r.method, "path": r.path, "status": r.status,
                 "signature_valid": r.signature_valid} for r in service.requests_log
            ],
            "result": result.to_dict(),
            "error": result.error,
        }

    for name, ok in checks.items():
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}", file=sys.stderr)
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "live-proof.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
    print(f"LIVE PROOF: {record['verdict']}", file=sys.stderr)
    return 0 if record["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
