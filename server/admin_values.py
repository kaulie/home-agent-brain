"""Admin API display values: node titles, policy summaries and step labels.

Pure helpers for the ``/api/v1/admin/*`` routes in ``home_brain``. They read
only their arguments: no Flask request, database or runtime state.
"""
from __future__ import annotations

ADMIN_ROLE_LABELS = {
    "intent_source": "发出 Intent",
    "runtime": "执行 Runtime",
    "endpoint": "呈现 Endpoint",
    "observer": "观察 Observer",
}


def admin_node_title(rec, pid=""):
    rec = rec if isinstance(rec, dict) else {}
    name = str(rec.get("display_name") or "").strip()
    loc = str(rec.get("location") or rec.get("room") or "").strip()
    if loc and name and loc not in name:
        return f"{loc} · {name}"
    return name or str(pid or rec.get("participant_id") or rec.get("edge_id") or "").strip()


def admin_target_title(target_kind, target_id):
    kind = str(target_kind or "").strip().lower()
    tid = str(target_id or "").strip()
    if kind == "role":
        return ADMIN_ROLE_LABELS.get(tid, tid)
    return tid


def admin_policy_summary(
    *,
    participant_id="",
    target_kind="",
    target_id="",
    enabled=None,
    rec=None,
    error=None,
    action="",
):
    title = admin_node_title(rec, participant_id) or participant_id or "节点"
    target = admin_target_title(target_kind, target_id)
    if action == "policy_replace":
        line = f"改写 {title} 的调度策略"
    elif enabled is True:
        line = f"打开 {title} 的 {target}".strip()
    elif enabled is False:
        line = f"关掉 {title} 的 {target}".strip()
    elif target:
        line = f"改 {title} 的 {target}".strip()
    else:
        line = f"管理 {title}"
    if error:
        return f"{line} 失败：{error}"
    return line


def policy_items_from_body(body):
    items = []
    roles = body.get("roles") if isinstance(body.get("roles"), dict) else {}
    for role, enabled in roles.items():
        items.append(
            {
                "target_kind": "role",
                "target_id": str(role),
                "enabled": bool(enabled),
            }
        )
    caps = body.get("capabilities") if isinstance(body.get("capabilities"), dict) else {}
    for cap, enabled in caps.items():
        items.append(
            {
                "target_kind": "capability",
                "target_id": str(cap),
                "enabled": bool(enabled),
            }
        )
    extra = body.get("items") if isinstance(body.get("items"), list) else []
    items.extend(item for item in extra if isinstance(item, dict))
    return items


def step_status_text(step):
    raw = step.get("status") if isinstance(step, dict) else None
    if raw in (2, "2", "succeeded", "success", "completed"):
        return "succeeded"
    if raw in (3, "3", "failed", "error"):
        return "failed"
    if raw in (1, "1", "running"):
        return "running"
    if raw in (0, "0", None, ""):
        return ""
    return str(raw)
