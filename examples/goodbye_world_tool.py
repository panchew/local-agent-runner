"""A second custom tool for local-agent-runner: ``goodbye_world``.

A deliberate near-twin of ``hello_world``, written in its own module with
the same argument name (``name``). Registering both proves that custom
tools combine without conflict. Calls are routed by tool name, and neither
module knows about the other:

    from local_agent_runner import ToolPermissions, run
    from hello_world_tool import hello_world
    from goodbye_world_tool import goodbye_world

    result = run("qwen2.5-coder:14b", "Greet Ada, then say goodbye.",
                 ToolPermissions(), custom_tools=[hello_world, goodbye_world])

``multi_tool_proof.py`` runs exactly that against a live Ollama.
"""

from local_agent_runner import custom_tool


@custom_tool
def goodbye_world(name: str) -> str:
    """Return a farewell for someone. Pass 'name' as the person to say goodbye to."""
    return f"Goodbye, {name}! See you next run."
