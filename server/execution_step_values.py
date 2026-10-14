"""Execution step status, capture failure wording and context parameter values.

No Brain imports, network calls, storage access or startup side effects.
"""


_TERMINAL_STEP_STATUSES = frozenset({2, 3})


_CAPTURE_STEP_CAPABILITIES = frozenset(
    {
        "camera.capture",
        "camera.take_video",
        "take_video",
        "document.scan",
        "visual.input",
        "camera.capture_and_upload",
    }
)


def _step_status_int(step) -> int:
    try:
        return int((step or {}).get("status") or 0)
    except (TypeError, ValueError):
        return 0


def _capture_succeeded_before(plan, failed_step) -> bool:
    """True if a capture/scan step succeeded (status=2) before the failed step."""
    try:
        fail_n = int((failed_step or {}).get("step") or 0)
    except (TypeError, ValueError):
        return False
    for step in plan or []:
        if not isinstance(step, dict):
            continue
        try:
            n = int(step.get("step") or 0)
        except (TypeError, ValueError):
            continue
        if n >= fail_n:
            continue
        cap = str(step.get("capability") or "").strip()
        if cap in _CAPTURE_STEP_CAPABILITIES and _step_status_int(step) == 2:
            return True
    return False


def _upload_failure_msg(plan, failed_step, msg):
    """Upload failed after a successful capture: say so honestly.

    The capture already landed in the device inbox, so the user should hear
    "拍照成功，已存本机" plus the real upload failure — never "拍照失败".
    """
    text = str(msg or "").strip()
    if not _capture_succeeded_before(plan, failed_step):
        return text
    if text.startswith("拍照成功"):
        return text
    if "上传" in text or "upload" in text.lower():
        return f"拍照成功，照片已保存在本机；但{text}"
    return f"拍照成功，照片已保存在本机；但上传失败：{text}"


def _plan_steps_all_terminal(plan) -> bool:
    if not plan:
        return False
    for step in plan:
        if _step_status_int(step) not in _TERMINAL_STEP_STATUSES:
            return False
    return True


def _system_predecessors_succeeded(plan, step_n) -> bool:
    for step in plan or []:
        if not isinstance(step, dict):
            continue
        try:
            n = int(step.get("step") or 0)
        except (TypeError, ValueError):
            continue
        if n <= 0 or n >= int(step_n):
            continue
        try:
            st = int(step.get("status") or 0)
        except (TypeError, ValueError):
            return False
        if st != 2:
            return False
    return True


def _resolve_system_params(raw, intent):
    params = dict(raw) if isinstance(raw, dict) else {}
    ctx = intent.get("ctx_param") or intent.get("context") or {}
    if not isinstance(ctx, dict):
        ctx = {}
    out = {}
    for key, val in params.items():
        if isinstance(val, str) and val.startswith("$") and len(val) > 1:
            name = val[1:]
            if name in ctx and ctx[name] is not None:
                out[key] = ctx[name]
            else:
                out[key] = val
        else:
            out[key] = val
    return out
