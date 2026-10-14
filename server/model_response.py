"""Model response parsing, safe request records and provider error messages.

No Brain imports, network calls, storage access or startup side effects.
"""
import json


_ARK_SECRET_KEYS = frozenset({"authorization", "api_key", "ark_api_key", "bearer"})


_ARK_HTTP_MSG_MAX = 240


def _without_secrets(value):
    if isinstance(value, dict):
        return {
            k: _without_secrets(v)
            for k, v in value.items()
            if str(k).lower() not in _ARK_SECRET_KEYS
        }
    if isinstance(value, list):
        return [_without_secrets(v) for v in value]
    return value


def _ark_result(*, ans="", cost_ms=0, request_payload=None, response_json=None, cache_hit=False):
    payload = _without_secrets(request_payload) if request_payload is not None else None
    return {
        "ans": ans,
        "cost_ms": int(cost_ms or 0),
        "request_payload": payload,
        "response_json": response_json,
        "cache_hit": bool(cache_hit),
    }


def _ark_http_error_json(exc):
    body = ""
    try:
        body = exc.read().decode("utf-8", errors="replace")
    except Exception:
        body = ""
    parsed = None
    if body:
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = None
    status = int(getattr(exc, "code", 0) or 0)
    if isinstance(parsed, dict):
        out = dict(parsed)
        out.setdefault("http_status", status)
        return out
    return {"http_status": status, "body": body[:8000]}


def get_model_answer(res_json):
    try:
        output_list = res_json.get("output", [])
        for block in output_list:
            if block.get("type") == "message":
                content_arr = block.get("content", [])
                if len(content_arr) > 0 and "text" in content_arr[0]:
                    return content_arr[0]["text"]
        return "暂时无法获取回答"
    except Exception:
        return "数据解析失败"


def _qwen_reply_text(response_json):
    """Parse model_server POST /chat JSON ({ok, text|answer|reply})."""
    if isinstance(response_json, str):
        return response_json
    if not isinstance(response_json, dict):
        return str(response_json or "")
    for key in ("reply", "answer", "text", "content", "output"):
        val = response_json.get(key)
        if isinstance(val, str) and val.strip():
            return val
        if isinstance(val, dict):
            nested = val.get("content") or val.get("text")
            if isinstance(nested, str) and nested.strip():
                return nested
    msg = response_json.get("message")
    if isinstance(msg, dict):
        nested = msg.get("content") or msg.get("text")
        if isinstance(nested, str) and nested.strip():
            return nested
    return ""


def _ark_http_error_msg(response_json):
    """User-facing failure when the ARK planner call itself returned HTTP >= 400.

    ``call_ark`` already parses provider HTTP errors into ``response_json``
    (``http_status`` + ``error.code/message`` via ``_ark_http_error_json``).
    Returns None when there is no HTTP error, so a genuinely empty LLM plan still
    falls through to ``_empty_plan_failure_msg`` with its original diagnostics.
    """
    if not isinstance(response_json, dict):
        return None
    try:
        status = int(response_json.get("http_status") or 0)
    except (TypeError, ValueError):
        status = 0
    if status < 400:
        return None
    if status == 401:
        return "规划服务 401，检查 ARK_API_KEY"
    code = ""
    message = ""
    err = response_json.get("error")
    if isinstance(err, dict):
        code = str(err.get("code") or "").strip()
        message = str(err.get("message") or "").strip()
    if not message:
        raw_body = response_json.get("body")
        if isinstance(raw_body, str) and raw_body.strip():
            message = raw_body.strip()
    code_part = f"（{code}）" if code else ""
    if code == "AccountOverdueError":
        text = f"规划服务 HTTP {status}{code_part}：火山方舟 ARK 账号欠费，请充值后重试"
    else:
        text = f"规划服务 HTTP {status}{code_part}：请稍后重试"
        if message:
            text += f"；{message}"
    if len(text) > _ARK_HTTP_MSG_MAX:
        text = text[:_ARK_HTTP_MSG_MAX - 3] + "..."
    return text
