"""Which Brain deployment instance this process represents (lan vs cloud)."""
from __future__ import annotations

import os

try:
    from .brain_env import SERVER_DIR as _HERE
except ImportError:  # pragma: no cover
    from brain_env import SERVER_DIR as _HERE  # type: ignore

_INTENT_ORIGINS = ("lan", "cloud")


def instance_intent_origin() -> str:
    """Which Brain this process is: lan (local/dev) or cloud (cloud-server)."""
    raw = (os.environ.get("BRAIN_ORIGIN") or "").strip().lower()
    if raw in _INTENT_ORIGINS:
        return raw
    try:
        here = str(_HERE.resolve())
    except OSError:
        here = ""
    if here.startswith("/root/chat-gateway") or "/root/chat-gateway/" in here:
        return "cloud"
    return "lan"


def resolve_intent_origin(value=None) -> str:
    """Receiving Brain origin is authoritative. Client hints are ignored."""
    return instance_intent_origin()
