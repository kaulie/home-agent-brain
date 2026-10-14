"""Pure presentation policy: user wording, media preference and spoken fields."""
from __future__ import annotations

import json


_DISPLAY_CAPS = {"display.photo", "display.slideshow"}


_SPOKEN_PRESENTATION_FIELDS = frozenset(
    {
        "time_text",
        "answer_text",
        "reply",
        "summary",
        "people",
        "state",
        "text",
        "status_text",
    }
)


def _user_asked_speaker(text):
    """用户点名了小度/音箱（xiaodu.play 是「点名才排」的步骤）。"""
    raw = str(text or "")
    return any(k in raw for k in ("小度", "音箱", "小爱", "喇叭"))


def _user_asked_tv(text):
    raw = str(text or "")
    keys = ("电视", "投屏", "投到", "chromecast", "Chromecast", "slideshow", "轮播")
    return any(k in raw for k in keys)


def _user_asked_photo(text):
    raw = str(text or "")
    keys = ("拍张", "拍照", "拍一张", "take_photo", "照相")
    return any(k in raw for k in keys)


def _intent_source_voice(intent) -> bool:
    return str((intent or {}).get("source") or "").strip().lower() == "voice"


def _user_asked_photo_count(text) -> bool:
    raw = str(text or "")
    if "照片" not in raw and "张" not in raw:
        return False
    return any(k in raw for k in ("多少", "几张", "几幅", "数量", "一共"))


def _user_asked_see_photo(text) -> bool:
    raw = str(text or "")
    if _user_asked_photo_count(raw):
        return False
    view_keys = ("看一下", "看下", "给我看", "看看", "显示", "瞧")
    photo_keys = ("照片", "图片", "那张", "这张")
    return any(v in raw for v in view_keys) and any(p in raw for p in photo_keys)


def _user_asked_see_document(text) -> bool:
    """User asked to preview a PDF/document (not a photo count question)."""
    raw = str(text or "")
    if _user_asked_photo_count(raw):
        return False
    # Pure photo view stays image; do not steal 「看一下那张照片」.
    if _user_asked_see_photo(raw):
        return False
    view_keys = ("看一下", "看下", "给我看", "看看", "显示", "瞧", "预览", "打开")
    doc_keys = ("pdf", "PDF", "文档", "文件", "document")
    return any(v in raw for v in view_keys) and any(d in raw for d in doc_keys)


def _plan_wants_image_presentation(intent) -> bool:
    caps = _caps_in_plan(intent)
    if any(c in _DISPLAY_CAPS for c in caps):
        return True
    raw = intent.get("presentation")
    if isinstance(raw, dict) and str(raw.get("type") or "").strip().lower() == "image":
        return True
    text = str((intent or {}).get("text") or "")
    if _user_asked_tv(text):
        return True
    if _user_asked_see_photo(text):
        return True
    return False


def _plan_wants_document_presentation(intent) -> bool:
    raw = intent.get("presentation")
    if isinstance(raw, dict) and str(raw.get("type") or "").strip().lower() == "document":
        return True
    text = str((intent or {}).get("text") or "")
    return _user_asked_see_document(text)


def _voice_symmetric_presentation_kind(intent, kind: str, from_key: str) -> tuple[str, str]:
    """Voice in → spoken out: word-field delivery defaults to audio, not text."""
    pkind = str(kind or "").strip().lower()
    if pkind != "text":
        return pkind, from_key
    if not _intent_source_voice(intent):
        return pkind, from_key
    if _plan_wants_image_presentation(intent):
        return pkind, from_key
    fk = str(from_key or "").strip()
    if not fk or fk in _SPOKEN_PRESENTATION_FIELDS:
        return "audio", from_key
    return pkind, from_key


def _speak_delivery_text(intent):
    pres = intent.get("presentation") if isinstance(intent.get("presentation"), dict) else {}
    text = str(pres.get("text") or "").strip()
    if text:
        return text
    ctx = intent.get("ctx_param") or intent.get("context") or {}
    if not isinstance(ctx, dict):
        return ""
    for key in ("time_text", "answer_text", "summary", "state"):
        val = str(ctx.get(key) or "").strip()
        if val:
            return val
    return ""


def _caps_in_plan(intent):
    caps = []
    for step in intent.get("execution_plan") or []:
        if isinstance(step, dict) and step.get("capability"):
            caps.append(str(step.get("capability") or "").strip())
    return caps


def _people_count_text(people):
    raw = people
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return ""
    if not isinstance(raw, list) or not raw:
        return ""
    total = 0
    for item in raw:
        if isinstance(item, dict):
            try:
                total += int(item.get("count") or 1)
            except (TypeError, ValueError):
                total += 1
        else:
            total += 1
    return f"{total}个人"
