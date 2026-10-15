"""Intent status normalization aliases."""
from __future__ import annotations

STATUS_ALIASES = {
    "uploaded": "intent_received",
    "waiting": "intent_waiting",
    "success": "succeeded",
    "completed": "succeeded",
    "error": "failed",
    "plan_failed": "failed",
}
TERMINAL_STATUSES = frozenset({"succeeded", "failed"})
EMPTY_PLAN_MSG = "execution_plan 为空，无法调度"


def normalize_status(raw):
    text = str(raw or "").strip()
    return STATUS_ALIASES.get(text, text)
