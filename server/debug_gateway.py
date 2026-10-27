"""Agent Debug Gateway — Console feedback → Issue → web-cursor task."""

from __future__ import annotations

import base64
import json
import logging
from typing import Any, Callable, Optional

from debug_attachments import attachment_asset_ids, normalize_attachments
from debug_client_snapshot import merge_intent_context, normalize_client_snapshot
from debug_feedback_types import normalize_problem_type, problem_type_label
from debug_issue_store import DebugIssue, get_store
from dev_task import get_agent_task
from web_cursor_feedback import (
    WebCursorError,
    create_feedback_task,
    post_task_message,
    task_api_url,
)

log = logging.getLogger("debug_gateway")

_USER_MESSAGE = "已提交反馈，正在分析。"

GetIntentFn = Callable[[int], Optional[dict[str, Any]]]


def _json_preview(obj: Any, limit: int = 12000) -> str:
    try:
        text = json.dumps(obj, ensure_ascii=False, indent=2, default=str)
    except (TypeError, ValueError):
        text = str(obj)
    if len(text) > limit:
        return text[:limit] + "\n…(truncated)"
    return text


def build_intent_context(intent: dict[str, Any]) -> dict[str, Any]:
    """Collect execution现场 from a Brain intent/job record."""
    ident = intent.get("intent_id") or intent.get("id")
    ctx = intent.get("context") or intent.get("ctx_param") or {}
    if not isinstance(ctx, dict):
        ctx = {}
    return {
        "intent_id": ident,
        "session_id": str(intent.get("session_id") or ctx.get("session_id") or ""),
        "user_input": str(intent.get("text") or intent.get("utterance") or ""),
        "source": str(intent.get("source") or ""),
        "intent_status": str(intent.get("status") or intent.get("intent_status") or ""),
        "error": str(
            intent.get("error")
            or intent.get("msg")
            or intent.get("message")
            or ""
        ).strip(),
        "edge_id": str(intent.get("edge_id") or ""),
        "intent_origin": str(intent.get("intent_origin") or ""),
        "execution_plan": intent.get("execution_plan") or [],
        "step_log": intent.get("step_log") or intent.get("steps") or [],
        "status_log": intent.get("status_log") or [],
        "presentation": intent.get("presentation"),
        "context": ctx,
        "source_context": intent.get("source_context") or ctx.get("source_context"),
        "outputs": intent.get("outputs") or intent.get("exposed_outputs"),
        "missing_capabilities": intent.get("missing_capabilities") or [],
        "planner_cost_ms": intent.get("planner_cost_ms"),
        "created_at": intent.get("created_at") or intent.get("intent_base_time"),
    }


# web-cursor stores up to 4000 chars and shows the first 2000 in the agent brief.
_DESCRIPTION_LIMIT = 4000
_HEAD_LIMIT = 1800
# Same caps as the control plane (`attachments.ts`): the messages API rejects more.
_MAX_AGENT_IMAGES = 5
_MAX_AGENT_IMAGE_BYTES = 4 * 1024 * 1024
_AGENT_IMAGE_MIME = frozenset({"image/png", "image/jpeg", "image/gif", "image/webp"})


def _clip(text: str, limit: int) -> str:
    raw = str(text or "").strip()
    if len(raw) <= limit:
        return raw
    return raw[:limit] + "…"


def feedback_task_title(issue: DebugIssue) -> str:
    label = problem_type_label(issue.problem_type)
    if int(issue.intent_id or 0) > 0:
        title = f"用户反馈 intent #{issue.intent_id}"
    else:
        title = f"用户反馈 {issue.source or 'console'}"
    if label:
        title = f"{title} · {label}"
    summary = issue.user_summary.strip()
    if summary:
        title = f"{title}：{_clip(summary, 40)}"
    return _clip(title, 80)


def _attachment_lines(issue: DebugIssue) -> list[str]:
    if not issue.attachments:
        return []
    lines = ["", "## 附件（Brain asset）"]
    for row in issue.attachments:
        kind = row.get("kind") or "file"
        aid = row.get("asset_id") or "—"
        mime = row.get("mime_type") or ""
        name = row.get("filename") or ""
        detail = f"- {kind} {aid}"
        if mime:
            detail += f" mime={mime}"
        if name:
            detail += f" name={name}"
        lines.append(detail)
    return lines


def _agent_image_mime(mime: str) -> str:
    raw = str(mime or "").split(";", 1)[0].strip().lower()
    if raw in ("image/jpg", "image/pjpeg"):
        return "image/jpeg"
    return raw or "image/jpeg"


def feedback_images_for_agent(
    attachments: list[dict[str, str]] | None,
) -> tuple[list[dict[str, str]], list[str]]:
    """Load image bytes the Dev Agent can actually see.

    Returns ``([{data, mimeType}], errors)``. Non-image attachments stay as
    asset-id text. A missing file is an error string, not a failed report.
    """
    try:
        from sdk.asset_bytes import AssetFetchError, fetch_asset_image_bytes
    except ImportError:  # pragma: no cover
        from server.sdk.asset_bytes import AssetFetchError, fetch_asset_image_bytes

    images: list[dict[str, str]] = []
    errors: list[str] = []
    for row in attachments or []:
        if str(row.get("kind") or "image").strip().lower() != "image":
            continue
        aid = str(row.get("asset_id") or "").strip()
        if not aid:
            continue
        if len(images) >= _MAX_AGENT_IMAGES:
            errors.append(f"{aid}: 超过 {_MAX_AGENT_IMAGES} 张，未发送")
            continue
        try:
            data, mime = fetch_asset_image_bytes(aid)
        except AssetFetchError as err:
            errors.append(f"{aid}: {err}")
            continue
        except Exception as err:
            errors.append(f"{aid}: {err}")
            continue
        mime_type = _agent_image_mime(mime)
        if mime_type not in _AGENT_IMAGE_MIME:
            errors.append(f"{aid}: web-cursor 不接受 {mime_type}")
            continue
        if not data or len(data) > _MAX_AGENT_IMAGE_BYTES:
            errors.append(f"{aid}: 图片为空或超过 4MB")
            continue
        images.append(
            {
                "data": base64.b64encode(data).decode("ascii"),
                "mimeType": mime_type,
            }
        )
    return images, errors


def build_feedback_description(
    issue: DebugIssue,
    context: dict[str, Any],
    *,
    client_snapshot: dict[str, Any] | None = None,
    image_count: int = 0,
    image_errors: list[str] | None = None,
) -> str:
    """Task description for web-cursor. The fix request stays inside the first 2000 chars."""
    label = problem_type_label(issue.problem_type)
    head = [
        "修复这条 HomeAgent 用户一键反馈。按 web-cursor 任务处理：用下面的现场定位根因，"
        "在本任务注入的仓库里改代码并开 PR，按本任务的 goal 交付。",
        "现场后半如果被截断，以本任务 description 全文为准。",
    ]
    if image_count > 0:
        head.extend(
            [
                "",
                "## 截图",
                f"用户上传了 {image_count} 张图片。这些图片会作为下一条用户消息的图片附件发给 Dev Agent，"
                "模型能直接看到画面，不只有 asset id。",
                "在看到那些图片之前不要改代码、不要下结论。"
                "如果这条消息里还没有图片，只回复「等待截图」并结束。",
            ]
        )
    elif image_errors:
        head.extend(
            [
                "",
                "## 截图",
                "图片字节没有传到 Dev Agent，不要等待图片。",
            ]
        )
        for note in image_errors[:5]:
            head.append(f"- {note}")
    head.extend(
        [
            "",
            "## 现场",
            f"- issue_id: {issue.issue_id}",
            f"- intent_id: {issue.intent_id}",
            f"- session_id: {issue.session_id or context.get('session_id') or '—'}",
            f"- participant_id: {issue.participant_id}",
            f"- source: {issue.source}",
            f"- status: {context.get('intent_status') or '—'}",
            f"- error: {_clip(str(context.get('error') or '—'), 400)}",
        ]
    )
    if label:
        head.append(f"- feedback_type: {issue.problem_type}（{label}）")
    brain = _brain_url_from_snapshot(client_snapshot)
    if brain:
        head.append(f"- brain: {brain}")
    head.extend(["", "## 用户原话", _clip(str(context.get("user_input") or "—"), 500)])
    if issue.user_summary.strip():
        head.extend(["", "## 用户补充", _clip(issue.user_summary, 500)])
    head.extend(_attachment_lines(issue))
    head_text = _clip("\n".join(head), _HEAD_LIMIT)

    sections: list[str] = []
    sections.append("## 执行计划\n" + _json_preview(context.get("execution_plan") or [], limit=900))
    sections.append("## Step Log\n" + _json_preview(context.get("step_log") or [], limit=900))
    sections.append("## 状态时间线\n" + _json_preview(context.get("status_log") or [], limit=600))
    if client_snapshot:
        snap = normalize_client_snapshot(client_snapshot)
        if snap:
            sections.append("## Client Snapshot\n" + _json_preview(snap, limit=900))
    sections.append("## Context JSON\n" + _json_preview(context, limit=1500))

    body = head_text
    for section in sections:
        piece = "\n\n" + section
        if len(body) + len(piece) <= _DESCRIPTION_LIMIT:
            body += piece
            continue
        remain = _DESCRIPTION_LIMIT - len(body) - 1
        if remain > 80:
            body += "\n" + piece[:remain].rstrip() + "…"
        break
    return body[:_DESCRIPTION_LIMIT]


def _participant_matches_intent(intent: dict[str, Any], participant_id: str) -> bool:
    pid = participant_id.strip()
    if not pid:
        return False
    edge = str(intent.get("edge_id") or "").strip()
    if edge and edge == pid:
        return True
    ctx = intent.get("context") or intent.get("ctx_param") or {}
    if isinstance(ctx, dict):
        for key in ("participant_id", "edge_id", "client_hint"):
            if str(ctx.get(key) or "").strip() == pid:
                return True
    return False


def _web_cursor_fields(issue: DebugIssue) -> dict[str, str]:
    task_id = str(issue.web_cursor_task_id or "").strip()
    if not task_id:
        return {}
    return {
        "web_cursor_task_id": task_id,
        "web_cursor_task_url": task_api_url(task_id),
    }


def issue_to_user_view(issue: DebugIssue) -> dict[str, Any]:
    return {
        "issue_id": issue.issue_id,
        "intent_id": issue.intent_id,
        "status": issue.status,
        "message": _USER_MESSAGE,
        "task_id": issue.task_id,
        **_web_cursor_fields(issue),
    }


def issue_to_admin_view(issue: DebugIssue, *, dev_task: dict[str, Any] | None = None) -> dict[str, Any]:
    view = {
        "issue_id": issue.issue_id,
        "intent_id": issue.intent_id,
        "session_id": issue.session_id,
        "source": issue.source,
        "participant_id": issue.participant_id,
        "status": issue.status,
        "user_summary": issue.user_summary,
        "problem_type": issue.problem_type,
        "problem_type_label": problem_type_label(issue.problem_type),
        "attachments": list(issue.attachments or []),
        "attachment_asset_ids": attachment_asset_ids(issue.attachments),
        "task_id": issue.task_id,
        "error": issue.error,
        "context": issue.context,
        "created_at": issue.created_at,
        "updated_at": issue.updated_at,
        **_web_cursor_fields(issue),
    }
    if dev_task:
        view["dev_task"] = dev_task
    return view


_PICKUP_SOURCES = frozenset({"pickup_terminal", "home_mic", "pickup"})


def _is_pickup_source(source: str) -> bool:
    key = (source or "").strip().lower()
    return key in _PICKUP_SOURCES or key.startswith("pickup")


def _deliver_feedback_images(
    web_task_id: str,
    *,
    images: list[dict[str, str]],
    image_errors: list[str],
) -> str:
    """Post screenshot bytes onto the web-cursor task. Empty string means ok."""
    if not images:
        return ""
    note = ""
    if image_errors:
        note = "\n未能附上的附件：\n" + "\n".join(f"- {row}" for row in image_errors[:5])
    message = (
        f"以下是用户一键反馈上传的截图，共 {len(images)} 张。"
        "请先看这些图片，再结合上一条现场按任务 goal 交付。"
        + note
    )
    try:
        post_task_message(web_task_id, message=message, images=images)
    except WebCursorError as err:
        log.warning(
            "debug_report image post failed task=%s: %s",
            web_task_id,
            err,
        )
        try:
            post_task_message(
                web_task_id,
                message=(
                    "截图发送失败，不要继续等待图片。"
                    f"原因：{err}。请按文字现场处理。"
                ),
            )
        except WebCursorError as follow_err:
            log.warning(
                "debug_report image failure notice failed task=%s: %s",
                web_task_id,
                follow_err,
            )
            return f"{err}; 失败通知也没发出：{follow_err}"
        return str(err)
    return ""


def submit_debug_report(
    *,
    intent_id: int,
    participant_id: str,
    source: str = "user_console",
    user_summary: str = "",
    problem_type: str = "",
    attachments: list[dict[str, str]] | None = None,
    client_snapshot: dict[str, Any] | None = None,
    get_intent: GetIntentFn,
) -> dict[str, Any]:
    """Create an Issue and a web-cursor task from intent现场, or from pickup client_snapshot alone."""
    pid = participant_id.strip()
    if not pid:
        return {"ok": False, "error": "participant_id is required"}

    normalized_type = normalize_problem_type(problem_type)
    if problem_type.strip() and not normalized_type:
        return {"ok": False, "error": "invalid problem_type"}

    src = source.strip() or "user_console"
    resolved_intent_id = int(intent_id or 0)

    if resolved_intent_id <= 0:
        if not _is_pickup_source(src):
            return {"ok": False, "error": "intent_id is required"}
        snap = normalize_client_snapshot(client_snapshot)
        context = merge_intent_context(
            {
                "intent_id": 0,
                "session_id": str(snap.get("device_id") or pid),
                "user_input": "",
                "source": src,
                "intent_status": "n/a",
                "error": str(snap.get("last_error") or ""),
            },
            snap,
        )
    else:
        intent = get_intent(resolved_intent_id)
        if not intent:
            return {"ok": False, "error": "intent not found"}
        if not _participant_matches_intent(intent, pid):
            return {"ok": False, "error": "participant_id does not match intent issuer"}
        context = merge_intent_context(build_intent_context(intent), client_snapshot)

    summary = user_summary.strip()
    if not summary and normalized_type:
        summary = problem_type_label(normalized_type)
    store = get_store()
    issue = store.create(
        intent_id=resolved_intent_id,
        session_id=str(context.get("session_id") or ""),
        source=src,
        participant_id=pid,
        user_summary=summary,
        problem_type=normalized_type,
        attachments=normalize_attachments(attachments),
        context=context,
    )

    images, image_errors = feedback_images_for_agent(issue.attachments)
    description = build_feedback_description(
        issue,
        context,
        client_snapshot=client_snapshot,
        image_count=len(images),
        image_errors=image_errors,
    )
    title = feedback_task_title(issue)
    try:
        created = create_feedback_task(title=title, description=description)
    except WebCursorError as err:
        store.update(issue.issue_id, status="failed", error=str(err))
        issue = store.get(issue.issue_id) or issue
        log.warning(
            "debug_report web-cursor create failed issue=%s intent=%s: %s",
            issue.issue_id,
            issue.intent_id,
            err,
        )
        return {
            "ok": False,
            "error": str(err),
            "issue_id": issue.issue_id,
            "intent_id": issue.intent_id,
        }

    web_task_id = str(created.get("task_id") or "").strip()
    if not web_task_id:
        err = "web-cursor 未返回 taskId"
        store.update(issue.issue_id, status="failed", error=err)
        issue = store.get(issue.issue_id) or issue
        return {
            "ok": False,
            "error": err,
            "issue_id": issue.issue_id,
            "intent_id": issue.intent_id,
        }
    image_post_error = _deliver_feedback_images(
        web_task_id,
        images=images,
        image_errors=image_errors,
    )
    update_fields: dict[str, Any] = {
        "web_cursor_task_id": web_task_id,
        "status": "queued",
    }
    if image_post_error:
        update_fields["error"] = f"截图未送达 Dev Agent：{image_post_error}"
    store.update(issue.issue_id, **update_fields)
    issue = store.get(issue.issue_id) or issue
    log.info(
        "debug_report issue=%s intent=%s web_cursor_task=%s source=%s",
        issue.issue_id,
        issue.intent_id,
        web_task_id,
        issue.source,
    )
    return {"ok": True, **issue_to_user_view(issue)}


def _brain_url_from_snapshot(client_snapshot: dict[str, Any] | None) -> str:
    if not client_snapshot:
        return ""
    snap = normalize_client_snapshot(client_snapshot)
    primary = snap.get("primary_brain")
    if isinstance(primary, dict):
        for key in ("base_url", "intent_url"):
            raw = str(primary.get(key) or "").strip()
            if not raw:
                continue
            if raw.startswith("http://") or raw.startswith("https://"):
                from urllib.parse import urlparse

                parsed = urlparse(raw)
                if parsed.scheme and parsed.netloc:
                    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    return str(snap.get("brain_base") or "").strip().rstrip("/")


def get_debug_issue(issue_id: int) -> dict[str, Any] | None:
    issue = get_store().get(issue_id)
    if issue is None:
        return None
    dev_task = None
    if issue.task_id:
        dev_task = get_agent_task(issue.task_id)
    return issue_to_admin_view(issue, dev_task=dev_task)


def list_debug_issues(
    *,
    before_id: int | None = None,
    limit: int = 30,
    intent_id: int | None = None,
) -> dict[str, Any]:
    issues, exhausted = get_store().list_issues(
        before_id=before_id,
        limit=limit,
        intent_id=intent_id,
    )
    rows = []
    for issue in issues:
        dev_task = get_agent_task(issue.task_id) if issue.task_id else None
        rows.append(issue_to_admin_view(issue, dev_task=dev_task))
    next_before = rows[-1]["issue_id"] if rows else None
    return {
        "issues": rows,
        "limit": limit,
        "before_id": before_id,
        "next_before_id": next_before,
        "exhausted": exhausted,
    }
