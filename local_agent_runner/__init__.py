"""local_agent_runner — standalone tool-calling loop engine for local Ollama models.

Run the test suite (fully offline, no Ollama server or GPU required):

    pip install -e ".[dev]"
    pytest
"""

from local_agent_runner.ollama_client import (
    ChatMessage,
    ChatResponse,
    OllamaClient,
    OllamaClientError,
    OllamaConnectionError,
    OllamaModelMissingError,
)

__all__ = [
    "ChatMessage",
    "ChatResponse",
    "OllamaClient",
    "OllamaClientError",
    "OllamaConnectionError",
    "OllamaModelMissingError",
]
