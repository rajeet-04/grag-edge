"""Process-wide access to the running EdgeRuntime for LangGraph nodes."""
from __future__ import annotations

_runtime = None


def set_edge_runtime(runtime) -> None:
    global _runtime
    _runtime = runtime


def get_edge_runtime():
    return _runtime
