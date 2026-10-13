"""Create a web-cursor task for a HomeAgent one-tap feedback report.

web-cursor owns the agent: ``POST /api/tasks`` stores the task and dispatches
it on the control-plane path (``@cursor/sdk``). This module does not talk to
agent-bridge.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

log = logging.getLogger("web_cursor_feedback")

_DEFAULT_BASE_URL = "http://127.0.0.1:4211"
_DEFAULT_PROJECT_NAME = "home-agent-feedback"
_DEFAULT_GOAL = "merge"
_DEFAULT_TASK_TYPE = "bugfix"
_GOALS = frozenset({"merge", "deploy"})
_TASK_TYPES = frozenset({"feature", "bugfix", "diagnose", "general"})
_TIMEOUT_SEC = 20

_project_id_cache: str | None = None


class WebCursorError(Exception):
    """web-cursor rejected the call or could not be reached."""


def reset_project_cache() -> None:
    global _project_id_cache
    _project_id_cache = None


def base_url() -> str:
    raw = (os.environ.get("WEB_CURSOR_BASE_URL") or _DEFAULT_BASE_URL).strip()
    return raw.rstrip("/") or _DEFAULT_BASE_URL


def feedback_project_name() -> str:
    raw = (os.environ.get("WEB_CURSOR_FEEDBACK_PROJECT") or _DEFAULT_PROJECT_NAME).strip()
    return raw or _DEFAULT_PROJECT_NAME


def feedback_goal() -> str:
    raw = (os.environ.get("WEB_CURSOR_FEEDBACK_GOAL") or _DEFAULT_GOAL).strip()
    if raw in _GOALS:
        return raw
    log.warning("invalid WEB_CURSOR_FEEDBACK_GOAL=%r; using %s", raw, _DEFAULT_GOAL)
    return _DEFAULT_GOAL


def feedback_task_type() -> str:
    raw = (os.environ.get("WEB_CURSOR_FEEDBACK_TASK_TYPE") or _DEFAULT_TASK_TYPE).strip()
    if raw in _TASK_TYPES:
        return raw
    log.warning("invalid WEB_CURSOR_FEEDBACK_TASK_TYPE=%r; using %s", raw, _DEFAULT_TASK_TYPE)
    return _DEFAULT_TASK_TYPE


def task_api_url(task_id: str) -> str:
    return f"{base_url()}/api/tasks/{task_id}"


def create_feedback_task(*, title: str, description: str) -> dict[str, str]:
    """Create a task on the feedback project and return its id."""
    project_id = resolve_feedback_project_id()
    payload = {
        "title": title,
        "description": description,
        "projectId": project_id,
        "taskType": feedback_task_type(),
        "goal": feedback_goal(),
    }
    data = _request("POST", "/api/tasks", payload)
    if not isinstance(data, dict):
        raise WebCursorError("web-cursor 返回的任务不是对象")
    task_id = str(data.get("taskId") or data.get("task_id") or "").strip()
    if not task_id:
        raise WebCursorError("web-cursor 未返回 taskId")
    return {
        "task_id": task_id,
        "project_id": str(data.get("projectId") or project_id),
        "task_url": task_api_url(task_id),
    }


def resolve_feedback_project_id() -> str:
    global _project_id_cache
    override = (os.environ.get("WEB_CURSOR_FEEDBACK_PROJECT_ID") or "").strip()
    if override:
        return override
    if _project_id_cache:
        return _project_id_cache
    name = feedback_project_name()
    data = _request("GET", "/api/projects")
    if not isinstance(data, list):
        raise WebCursorError("web-cursor 项目列表不是数组")
    matches = [
        row
        for row in data
        if isinstance(row, dict) and str(row.get("name") or "").strip() == name
    ]
    if len(matches) != 1:
        raise WebCursorError(
            f"web-cursor 项目 {name} 未找到或重名（{len(matches)} 个）；"
            "可设置 WEB_CURSOR_FEEDBACK_PROJECT_ID"
        )
    project_id = str(matches[0].get("projectId") or "").strip()
    if not project_id:
        raise WebCursorError(f"web-cursor 项目 {name} 没有 projectId")
    _project_id_cache = project_id
    return project_id


def _request(method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    url = base_url() + path
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SEC) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as err:
        raise WebCursorError(_http_error_message(err)) from err
    except TimeoutError as err:
        raise WebCursorError(f"web-cursor 超时（{base_url()}）") from err
    except urllib.error.URLError as err:
        raise WebCursorError(f"web-cursor 连不上（{base_url()}）：{err.reason}") from err
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as err:
        raise WebCursorError("web-cursor 返回的不是 JSON") from err


def _http_error_message(err: urllib.error.HTTPError) -> str:
    body = ""
    try:
        body = err.read().decode("utf-8", errors="replace")
    except Exception:
        body = ""
    message = body.strip()
    try:
        parsed = json.loads(body) if body else None
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict) and parsed.get("error"):
        message = str(parsed["error"])
    if len(message) > 300:
        message = message[:300] + "…"
    if not message:
        message = err.reason or "request failed"
    return f"web-cursor HTTP {err.code}: {message}"
