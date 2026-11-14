"""Tests for the public API surface."""

import inspect
import sys
from pathlib import Path

# Add the project root to Python path to allow imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from local_agent_runner import (
    Result,
    STATUS_COMPLETED,
    STATUS_MAX_ITERATIONS_EXCEEDED,
    ToolPermissions,
    run,
)


def test_imports() -> None:
    """Test that all expected symbols can be imported directly from the package."""
    assert callable(run)
    assert inspect.isclass(Result)
    assert STATUS_COMPLETED == "completed"