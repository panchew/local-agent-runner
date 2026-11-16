"""A minimal custom tool for local-agent-runner: ``hello_world``.

Import it and pass it to ``run()``:

    from local_agent_runner import ToolPermissions, run
    from hello_world_tool import hello_world

    result = run("qwen2.5-coder:14b", "Greet Ada using your tool.",
                 ToolPermissions(), custom_tools=[hello_world])

Or run this file for a live proof against a local Ollama (CONTRACT §1.1):

    python examples/hello_world_tool.py --model qwen2.5-coder:14b
"""

from __future__ import annotations

import argparse
import json
import sys

from local_agent_runner import ToolPermissions, custom_tool, run

DEMO_TASK = (
    "Use the hello_world tool to greet Ada, then reply with exactly the "
    "greeting the tool returned."
)


@custom_tool
def hello_world(name: str) -> str:
    """Return a greeting for someone. Pass 'name' as the person to greet."""
    return f"Hello, {name}! Greetings from a custom local-agent-runner tool."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live hello_world custom-tool proof.")
    parser.add_argument("--model", default="qwen2.5-coder:14b")
    parser.add_argument("--endpoint", default="http://localhost:11434")
    parser.add_argument("--transcript", help="optional path to write the §3 Result JSON")
    args = parser.parse_args(argv)

    # No built-ins enabled: hello_world is the only tool the model sees.
    result = run(
        args.model,
        DEMO_TASK,
        ToolPermissions(),
        endpoint=args.endpoint,
        custom_tools=[hello_world],
    )
    if args.transcript:
        with open(args.transcript, "w") as fh:
            json.dump(result.to_dict(), fh, indent=2)

    print(json.dumps(result.to_dict(), indent=2))
    called = any(s["tool_call"]["name"] == "hello_world" for s in result.transcript)
    if result.status != "completed" or not called:
        print(f"PROOF FAILED: status={result.status} hello_world_called={called} "
              f"{result.error or ''}", file=sys.stderr)
        return 1
    print("PROOF OK: the model called hello_world and the loop completed.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
