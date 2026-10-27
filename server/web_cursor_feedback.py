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
import urllib.parse
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
_IMAGE_POST_TIMEOUT_SEC = 60
_UI_VERSION_HEADER = "x-ui-version"
_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

_project_id_cache: str | None = None
_ui_version_cache: str | None = None


class WebCursorError(Exception):
    """web-cursor rejected the call or could not be reached."""


def reset_project_cache() -> None:
    global _project_id_cache, _ui_version_cache
    _project_id_cache = None
    _ui_version_cache = None


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


def post_task_message(
    task_id: str,
    *,
    message: str,
    images: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Send a follow-up the Dev Agent can see.

    ``POST /api/tasks`` already dispatched the description as text. Image bytes
    have to ride a later ``POST /api/tasks/{id}/messages`` ``images`` array
    (base64 ``data`` + ``mimeType``) or the model only sees asset ids.
    """
    tid = str(task_id or "").strip()
    if not tid:
        raise WebCursorError("task_id is required")
    text = str(message or "")
    rows = [
        row
        for row in (images or [])
        if isinstance(row, dict) and str(row.get("data") or "").strip()
    ]
    if not text.strip() and not rows:
        raise WebCursorError("message or images required")
    payload: dict[str, Any] = {"message": text}
    if rows:
        payload["images"] = rows
    quoted = urllib.parse.quote(tid, safe="")
    data = _request(
        "POST",
        f"/api/tasks/{quoted}/messages",
        payload,
        timeout=_IMAGE_POST_TIMEOUT_SEC if rows else _TIMEOUT_SEC,
    )
    return data if isinstance(data, dict) else {}


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


def _ui_version() -> str:
    """Version web-cursor requires on writes (`x-ui-version`), from `GET /health`."""
    global _ui_version_cache
    if _ui_version_cache:
        return _ui_version_cache
    data = _request("GET", "/health", attach_ui_version=False)
    version = str(data.get("version") or "").strip() if isinstance(data, dict) else ""
    if not version:
        raise WebCursorError("web-cursor /health 没有 version")
    _ui_version_cache = version
    return version


def _request(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    attach_ui_version: bool = True,
    timeout: float | None = None,
) -> Any:
    write = method.upper() in _WRITE_METHODS
    version = _ui_version() if write and attach_ui_version else ""
    limit = _TIMEOUT_SEC if timeout is None else timeout
    try:
        return _open(method, path, payload, version, limit)
    except urllib.error.HTTPError as err:
        body, parsed = _read_http_error(err)
        refreshed = _mismatch_server_version(parsed) if write and attach_ui_version else ""
        if refreshed and refreshed != version:
            global _ui_version_cache
            _ui_version_cache = refreshed
            try:
                return _open(method, path, payload, refreshed, limit)
            except urllib.error.HTTPError as retry_err:
                retry_body, retry_parsed = _read_http_error(retry_err)
                raise WebCursorError(
                    _format_http_error(retry_err.code, retry_body, retry_parsed)
                ) from retry_err
        raise WebCursorError(_format_http_error(err.code, body, parsed)) from err
    except TimeoutError as err:
        raise WebCursorError(f"web-cursor 超时（{base_url()}）") from err
    except urllib.error.URLError as err:
        raise WebCursorError(f"web-cursor 连不上（{base_url()}）：{err.reason}") from err


def _open(
    method: str,
    path: str,
    payload: dict[str, Any] | None,
    ui_version: str,
    timeout: float,
) -> Any:
    url = base_url() + path
    data = None
    headers = {"Accept": "application/json"}
    if ui_version:
        headers[_UI_VERSION_HEADER] = ui_version
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as err:
        raise WebCursorError("web-cursor 返回的不是 JSON") from err


def _read_http_error(err: urllib.error.HTTPError) -> tuple[str, dict[str, Any] | None]:
    body = ""
    try:
        body = err.read().decode("utf-8", errors="replace")
    except Exception:
        body = ""
    try:
        parsed = json.loads(body) if body else None
    except json.JSONDecodeError:
        parsed = None
    return body, parsed if isinstance(parsed, dict) else None


def _mismatch_server_version(parsed: dict[str, Any] | None) -> str:
    if not isinstance(parsed, dict) or parsed.get("code") != "ui-version-mismatch":
        return ""
    return str(parsed.get("serverVersion") or "").strip()


def _format_http_error(code: int, body: str, parsed: dict[str, Any] | None) -> str:
    message = body.strip()
    if isinstance(parsed, dict) and parsed.get("error"):
        message = str(parsed["error"])
    if len(message) > 300:
        message = message[:300] + "…"
    if not message:
        message = "request failed"
    return f"web-cursor HTTP {code}: {message}"
