"""Live proof that two custom tools coexist in one run.

Registers ``hello_world`` and ``goodbye_world`` together and asks the model
to use both. The proof passes when the run completes and each tool was
called and returned its own output:

    python examples/multi_tool_proof.py --model qwen2.5-coder:14b
"""

from __future__ import annotations

import argparse
import json
import sys

from goodbye_world_tool import goodbye_world
from hello_world_tool import hello_world

from local_agent_runner import ToolPermissions, run

DEMO_TASK = (
    "First use the hello_world tool to greet Ada. Then use the goodbye_world "
    "tool to say goodbye to Ada. Finally reply with both messages the tools "
    "returned."
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live two-custom-tool proof.")
    parser.add_argument("--model", default="qwen2.5-coder:14b")
    parser.add_argument("--endpoint", default="http://localhost:11434")
    parser.add_argument("--transcript", help="optional path to write the §3 Result JSON")
    args = parser.parse_args(argv)

    result = run(
        args.model,
        DEMO_TASK,
        ToolPermissions(),  # no built-ins: only the two custom tools are offered
        endpoint=args.endpoint,
        custom_tools=[hello_world, goodbye_world],
    )
    if args.transcript:
        with open(args.transcript, "w") as fh:
            json.dump(result.to_dict(), fh, indent=2)
    print(json.dumps(result.to_dict(), indent=2))

    # Each tool must have been called and must have produced its *own* output.
    routed = {
        "hello_world": any(
            s["tool_call"]["name"] == "hello_world" and s["tool_result"].startswith("Hello,")
            for s in result.transcript
        ),
        "goodbye_world": any(
            s["tool_call"]["name"] == "goodbye_world" and s["tool_result"].startswith("Goodbye,")
            for s in result.transcript
        ),
    }
    if result.status != "completed" or not all(routed.values()):
        print(f"PROOF FAILED: status={result.status} routed={routed} {result.error or ''}",
              file=sys.stderr)
        return 1
    print("PROOF OK: both custom tools were called, each with its own result.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
