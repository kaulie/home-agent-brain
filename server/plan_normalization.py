"""Execution plan normalization; live provider lookup is supplied by the caller."""
from __future__ import annotations

if __package__:
    from .presentation_policy import (
        _DISPLAY_CAPS,
        _user_asked_speaker,
        _user_asked_tv,
        _user_asked_photo,
        _user_asked_document_scan,
    )
else:
    from presentation_policy import (
        _DISPLAY_CAPS,
        _user_asked_speaker,
        _user_asked_tv,
        _user_asked_photo,
        _user_asked_document_scan,
    )


_DELIVERY_CAPS = {"endpoint.present", "endpoint.feedback", "notify.speak"}

# Interactive paper scan (waits for user). Never a fallback for bare 「拍照」.
_DOCUMENT_SCAN_CAPS = frozenset({"document.scan", "visual.input"})
_CAMERA_CAPTURE_CAPS = frozenset({"camera.capture", "camera.capture_and_upload"})


# TV output is gated on an explicit request; display.audio is not an image hint.
_TV_GATED_CAPS = _DISPLAY_CAPS | {"display.audio"}


# Speaker playback and playback controls also require an explicit device request.
_SPEAKER_PLAY_CAP = "xiaodu.play"


_PLAY_CONTROL_CAPS = frozenset({"xiaodu.control", "display.audio.control"})


def _user_asked_generated_image(text):
    raw = str(text or "")
    keys = (
        "图片",
        "来张",
        "画一张",
        "画张",
        "出图",
        "配图",
        "生成图",
        "生图",
        "一张图",
        "photo",
        "picture",
        "image",
    )
    if any(k in raw for k in keys):
        return True
    lower = raw.lower()
    return "generate" in lower and "image" in lower


def _query_keeps_image_goal(query, intent_text):
    q = str(query or "")
    if _user_asked_generated_image(q) or _user_asked_tv(q):
        return True
    # Same full sentence (or longer paraphrase) already carries the goal.
    return bool(intent_text) and intent_text in q


def _repair_stripped_query_inputs(plan, intent=None):
    """If planner stripped query to a topic noun, restore full intent text.

    Downstream only sees this step's inputs; bare topics cause refuse-without-image.
    Also set want_image=true when this step expects asset_ref and the user asked
    for a picture / TV cast (Edge force-draws even if the text model refuses).
    """
    text = str((intent or {}).get("text") or "").strip()
    if not text:
        return plan
    wants_pic = _user_asked_generated_image(text) or _user_asked_tv(text)
    if not wants_pic:
        return plan
    repaired = []
    for step in plan or []:
        if not isinstance(step, dict):
            repaired.append(step)
            continue
        s = dict(step)
        ic = s.get("input_constrict")
        oc = s.get("output_constrict")
        if not isinstance(ic, dict) or "query" not in ic:
            repaired.append(s)
            continue
        expects_image = isinstance(oc, dict) and (
            "asset_ref" in oc or "image_ref" in oc or "capture_ref" in oc
        )
        if not expects_image:
            repaired.append(s)
            continue
        new_ic = dict(ic)
        q = str(new_ic.get("query") or "").strip()
        if not q or not _query_keeps_image_goal(q, text):
            new_ic["query"] = text
        if str(new_ic.get("want_image") or "").strip().lower() not in (
            "1",
            "true",
            "yes",
            "on",
        ):
            new_ic["want_image"] = "true"
        s["input_constrict"] = new_ic
        repaired.append(s)
    return repaired


_LEGACY_ASSET_ALIAS = {
    "image_ref": "asset_ref",
    "photo_url": "asset_ref",
}


def _rewrite_asset_token(value):
    """Map legacy $image_ref tokens to $asset_ref. $capture_ref is a local inbox handle, not an Asset."""
    if not isinstance(value, str):
        return value
    raw = value.strip()
    if not raw.startswith("$"):
        return value
    key = raw[1:].strip()
    mapped = _LEGACY_ASSET_ALIAS.get(key)
    if mapped:
        return "$" + mapped
    return value


def _normalize_plan_asset_refs(plan):
    """Force step I/O identity: image_ref/photo_url → asset_ref. Keep capture_ref."""
    out = []
    for step in plan or []:
        if not isinstance(step, dict):
            out.append(step)
            continue
        s = dict(step)
        ic = s.get("input_constrict")
        if isinstance(ic, dict):
            new_ic = {}
            for k, v in ic.items():
                nk = _LEGACY_ASSET_ALIAS.get(str(k), str(k))
                new_ic[nk] = _rewrite_asset_token(v)
            s["input_constrict"] = new_ic
        oc = s.get("output_constrict")
        if isinstance(oc, dict):
            new_oc = {}
            for k, v in oc.items():
                nk = _LEGACY_ASSET_ALIAS.get(str(k), str(k))
                if isinstance(v, dict):
                    new_oc[nk] = dict(v)
                else:
                    new_oc[nk] = v
            s["output_constrict"] = new_oc
        out.append(s)
    return out


def sanitize_execution_plan(plan, intent=None, *, online_capability_providers):
    """Strip delivery-as-capability and TV display unless the user asked for TV.

    Also: bare 「拍照」 must not fall back to document.scan (interactive wait).
    """
    text = str((intent or {}).get("text") or "")
    asked_tv = _user_asked_tv(text)
    asked_photo = _user_asked_photo(text)
    asked_scan = _user_asked_document_scan(text)
    # Photo shutter ≠ paper scan. When user said 拍照 (and not 扫描), drop scan caps.
    block_scan_for_photo = asked_photo and not asked_scan
    cleaned = []
    for step in plan or []:
        if not isinstance(step, dict):
            continue
        cap = str(step.get("capability") or "").strip()
        if not cap:
            continue
        if cap in _DELIVERY_CAPS:
            continue
        if cap in _TV_GATED_CAPS and not asked_tv:
            continue
        if cap == _SPEAKER_PLAY_CAP and not _user_asked_speaker(text):
            continue
        if cap in _PLAY_CONTROL_CAPS and not (
            _user_asked_speaker(text) or _user_asked_tv(text)
        ):
            continue
        if block_scan_for_photo and cap in _DOCUMENT_SCAN_CAPS:
            continue
        cleaned.append(dict(step))
    has_capture = any(
        str(s.get("capability") or "") in _CAMERA_CAPTURE_CAPS for s in cleaned
    )
    if asked_photo and not asked_tv:
        drop = {"notify.speak", "query.content"}
        if not has_capture:
            drop.add("vision.ask")
        cleaned = [s for s in cleaned if str(s.get("capability") or "") not in drop]
    cleaned = _normalize_plan_asset_refs(cleaned)
    cleaned = _repair_stripped_query_inputs(cleaned, intent)
    cleaned = _fold_capture_upload_composite(cleaned, online_capability_providers=online_capability_providers)
    for idx, step in enumerate(cleaned, start=1):
        step["step"] = idx
    return cleaned


def _prepare_shortcut_execution_plan(plan, intent=None, *, online_capability_providers):
    """Shortcut plans are pre-built; do not strip notify.speak like LLM sanitize."""
    steps = []
    for step in plan or []:
        if not isinstance(step, dict):
            continue
        cap = str(step.get("capability") or "").strip()
        if not cap:
            continue
        steps.append(dict(step))
    steps = _normalize_plan_asset_refs(steps)
    steps = _repair_stripped_query_inputs(steps, intent)
    steps = _fold_capture_upload_composite(steps, online_capability_providers=online_capability_providers)
    for idx, step in enumerate(steps, start=1):
        step["step"] = idx
    return steps


_COMPOSITE_CAPTURE_UPLOAD = "camera.capture_and_upload"


def _step_uses_capture_ref_token(step) -> bool:
    ic = (step or {}).get("input_constrict")
    if not isinstance(ic, dict):
        return False
    return str(ic.get("capture_ref") or "").strip() == "$capture_ref"


def _fold_capture_upload_composite(plan, *, online_capability_providers):
    """Merge consecutive capture + upload($capture_ref) into one composite step.

    capture_ref is Runtime-local and cannot cross edges. Brain schedules the
    composite as a whole; Runtime expands it.
    """
    rows = [dict(s) for s in (plan or []) if isinstance(s, dict)]
    if not rows:
        return rows
    out = []
    i = 0
    while i < len(rows):
        cur = rows[i]
        nxt = rows[i + 1] if i + 1 < len(rows) else None
        cap = str(cur.get("capability") or "").strip()
        nxt_cap = str((nxt or {}).get("capability") or "").strip()
        if (
            cap == "camera.capture"
            and nxt_cap == "asset.upload"
            and _step_uses_capture_ref_token(nxt)
        ):
            providers = {
                str(row.get("edge_id") or "").strip()
                for row in online_capability_providers(_COMPOSITE_CAPTURE_UPLOAD)
            }
            providers.discard("")
            if not providers:
                out.append(cur)
                i += 1
                continue
            dest = {}
            ic = nxt.get("input_constrict")
            if isinstance(ic, dict):
                dest_val = ic.get("dest") or ic.get("upload_dest")
                if dest_val not in (None, "", "$capture_ref"):
                    dest["dest"] = dest_val
            oc = nxt.get("output_constrict")
            if not isinstance(oc, dict) or not oc:
                oc = {"asset_ref": {"type": "string", "data_dest": "context"}}
            merged = {
                "step": cur.get("step"),
                "capability": _COMPOSITE_CAPTURE_UPLOAD,
                "input_constrict": dest,
                "output_constrict": oc,
            }
            timing = cur.get("execution_timing") or (nxt or {}).get("execution_timing")
            if timing:
                merged["execution_timing"] = timing
            edge = str(cur.get("assigned_edge_id") or "").strip()
            nxt_edge = str((nxt or {}).get("assigned_edge_id") or "").strip()
            if edge and edge in providers:
                merged["assigned_edge_id"] = edge
            elif nxt_edge and nxt_edge in providers:
                merged["assigned_edge_id"] = nxt_edge
            elif len(providers) == 1:
                merged["assigned_edge_id"] = next(iter(providers))
            out.append(merged)
            i += 2
            continue
        out.append(cur)
        i += 1
    return out
