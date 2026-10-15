"""Infer presentation type/source from planner decisions and scheduled capabilities."""
from __future__ import annotations

try:
    from .planner_output import _normalize_presentation_plan
    from .presentation_policy import (
        _DISPLAY_CAPS,
        _caps_in_plan,
        _plan_wants_document_presentation,
        _plan_wants_image_presentation,
        _voice_symmetric_presentation_kind,
    )
except ImportError:  # pragma: no cover
    from planner_output import _normalize_presentation_plan  # type: ignore
    from presentation_policy import (  # type: ignore
        _DISPLAY_CAPS,
        _caps_in_plan,
        _plan_wants_document_presentation,
        _plan_wants_image_presentation,
        _voice_symmetric_presentation_kind,
    )


def presentation_kind_from_plan(intent, *, plan_emits_field):
    raw = intent.get("presentation")
    planned = {}
    raw_type = str((raw or {}).get("type") or "").strip().lower() if isinstance(raw, dict) else ""
    if isinstance(raw, dict) and (
        raw.get("from") or raw.get("payload_from") or raw_type == "audio"
    ):
        planned = _normalize_presentation_plan(raw)
    if not planned.get("type"):
        planned = _normalize_presentation_plan(intent.get("presentation_plan"))
    if planned.get("type"):
        src = planned.get("from")
        plan = intent.get("execution_plan") or []
        if src and plan and not plan_emits_field(plan, src):
            planned = {}
        else:
            return _voice_symmetric_presentation_kind(
                intent, planned["type"], src or ""
            )
    caps = _caps_in_plan(intent)
    if any(c in _DISPLAY_CAPS for c in caps):
        return "image", "asset_ref"
    if "music.recognize" in caps:
        return _voice_symmetric_presentation_kind(intent, "text", "answer_text")
    if "clock.now" in caps:
        return _voice_symmetric_presentation_kind(intent, "text", "time_text")
    if "map.route.estimate" in caps:
        return _voice_symmetric_presentation_kind(intent, "text", "answer_text")
    if "math.calculate" in caps:
        return _voice_symmetric_presentation_kind(intent, "text", "answer_text")
    if "chat.smalltalk" in caps:
        return _voice_symmetric_presentation_kind(intent, "text", "reply")
    if "display.audio" in caps or "xiaodu.play" in caps or "xiaodu.control" in caps or "display.audio.control" in caps:
        return _voice_symmetric_presentation_kind(intent, "text", "status_text")
    if "asset.inventory" in caps:
        if _plan_wants_document_presentation(intent):
            return "document", "asset_ref"
        if _plan_wants_image_presentation(intent):
            return "image", "asset_ref"
        return _voice_symmetric_presentation_kind(intent, "text", "answer_text")
    if "image.ocr" in caps:
        return _voice_symmetric_presentation_kind(intent, "text", "text")
    if "capabilities.summary" in caps:
        return "audio", "answer_text"
    if "vision.ask" in caps:
        return _voice_symmetric_presentation_kind(intent, "text", "answer_text")
    if "query.content" in caps:
        return _voice_symmetric_presentation_kind(intent, "text", "answer_text")
    if "search.images" in caps:
        return "image", "asset_refs"
    if "vision.perceive" in caps:
        return _voice_symmetric_presentation_kind(intent, "text", "summary")
    if "light.set" in caps:
        return _voice_symmetric_presentation_kind(intent, "text", "state")
    if "climate.set" in caps:
        return _voice_symmetric_presentation_kind(intent, "text", "status_text")
    if "aquarium.set" in caps:
        return _voice_symmetric_presentation_kind(intent, "text", "status_text")
    if "lock.status" in caps:
        return _voice_symmetric_presentation_kind(intent, "text", "status_text")
    if "camera.capture" in caps or "camera.capture_and_upload" in caps:
        return "image", "asset_ref"
    if "document.scan" in caps or "visual.input" in caps:
        return "image", "asset_ref"
    return "", ""
