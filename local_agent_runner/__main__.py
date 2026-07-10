"""``python -m local_agent_runner`` — the same §2 CLI as the
``local-agent-runner`` console script."""

import sys

from local_agent_runner.cli import main

if __name__ == "__main__":
    sys.exit(main())
