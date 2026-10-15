"""Volcano Engine Ark chat-completions HTTP client (火山方舟).

No Flask, DB, or ``home_brain`` imports. Configuration from ``brain_env``.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

try:
    from . import brain_env
    from .model_response import _ark_http_error_json, _without_secrets
except ImportError:  # pragma: no cover
    import brain_env  # type: ignore
    from model_response import _ark_http_error_json, _without_secrets  # type: ignore

ARK_HTTP_401_SENTINEL = "__ARK_HTTP_401__"


@dataclass(frozen=True)
class ChatCompletionResponse:
    content: str
    response_json: dict[str, Any] | None
    cost_ms: int
    request_payload: dict[str, Any]


def _auth_headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {brain_env.ARK_API_KEY}",
    }


def build_planner_payload(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str | None = None,
) -> dict[str, Any]:
    return {
        "model": model or brain_env.MODEL_ID,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": 4096,
        "temperature": 0.2,
        "top_p": 0.1,
        "stream": False,
        "response_format": {"type": "json_object"},
        "extra_body": {"thinking": {"type": "disabled"}},
    }


def build_runner_payload(user_content: str, *, model: str | None = None) -> dict[str, Any]:
    return {
        "model": model or brain_env.MODEL_ID,
        "messages": [{"role": "user", "content": user_content}],
        "temperature": 0.7,
        "max_tokens": 120,
    }


def extract_assistant_content(response_json: dict[str, Any]) -> str:
    choices = response_json.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return str(message.get("content") or "")


def post_chat_completions(payload: dict[str, Any], timeout: float = 180.0) -> ChatCompletionResponse:
    """POST Ark ``/chat/completions``; never logs Authorization."""
    body = json.dumps(payload).encode("utf-8")
    started = time.time()
    response_json: dict[str, Any] | None = None
    content = ""
    try:
        req = urllib.request.Request(brain_env.ARK_URL, data=body, headers=_auth_headers())
        resp = urllib.request.urlopen(req, timeout=float(timeout))
        raw = resp.read().decode("utf-8")
        response_json = json.loads(raw) if raw.strip() else {}
        content = extract_assistant_content(response_json)
    except urllib.error.HTTPError as exc:
        response_json = _ark_http_error_json(exc)
        if int(getattr(exc, "code", 0) or 0) == 401:
            content = ARK_HTTP_401_SENTINEL
    cost_ms = int((time.time() - started) * 1000)
    safe_payload = _without_secrets(payload)
    return ChatCompletionResponse(
        content=content,
        response_json=response_json,
        cost_ms=cost_ms,
        request_payload=safe_payload,
    )
