"""Asset value normalization, filenames, public views and time filters (no I/O)."""
from __future__ import annotations

import json
import re
import uuid
import unicodedata
import mimetypes
import urllib.parse
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _as_asset_ref(raw):
    """Normalize an AssetRef. URLs and paths are not identity."""
    if isinstance(raw, str):
        aid = raw.strip()
        if not aid:
            return None
        if aid.startswith("{") or aid.startswith("["):
            try:
                parsed = json.loads(aid)
            except (TypeError, ValueError):
                parsed = None
            if isinstance(parsed, dict):
                return _as_asset_ref(parsed)
            if isinstance(parsed, list) and parsed:
                return _as_asset_ref(parsed[0])
        return {"asset_id": aid, "type": "image"}
    if not isinstance(raw, dict):
        return None
    nested = raw.get("asset_ref")
    if isinstance(nested, dict) and not str(raw.get("asset_id") or "").strip():
        return _as_asset_ref(nested)
    if isinstance(nested, str) and nested.strip().startswith("{") and not str(raw.get("asset_id") or "").strip():
        return _as_asset_ref(nested)
    aid = str(raw.get("asset_id") or "").strip()
    if not aid:
        return None
    if aid.startswith("{"):
        inner = _as_asset_ref(aid)
        if inner:
            return inner
    out = {
        "asset_id": aid,
        "type": str(raw.get("type") or "image").strip() or "image",
    }
    mime = str(raw.get("mime_type") or "").strip()
    if mime:
        out["mime_type"] = mime
    return out


def _asset_media_family(ref) -> str:
    """Best-effort media family of an AssetRef (image/audio/video/document/other)."""
    if not isinstance(ref, dict):
        return "other"
    asset_type = str(ref.get("type") or "").strip().lower()
    mime = str(ref.get("mime_type") or "").strip().lower()
    if asset_type == "image" or mime.startswith("image/"):
        return "image"
    if asset_type == "audio" or mime.startswith("audio/"):
        return "audio"
    if asset_type == "video" or mime.startswith("video/"):
        return "video"
    if asset_type == "document" or mime.startswith(("application/", "text/")):
        return "document"
    return "other"


def _is_previewable_document_ref(ref) -> bool:
    """A document preview needs a real document artifact.

    `asset.inventory` often hands back a `type=url` asset (mime `text/uri-list`) while the
    step that produces the real PDF is still running. Previewing that link would make the
    client try to render a URL as a document, so it is not previewable (#677).
    """
    if not isinstance(ref, dict):
        return False
    if str(ref.get("type") or "").strip().lower() == "url":
        return False
    return _asset_media_family(ref) == "document"


def _parse_asset_refs_list(raw):
    """Parse inventory-style asset_refs (JSON string or list) into AssetRef dicts."""
    data = raw
    if isinstance(data, str):
        text = data.strip()
        if not text:
            return []
        try:
            data = json.loads(text)
        except (TypeError, ValueError):
            return []
    if not isinstance(data, list):
        return []
    refs = []
    for item in data:
        ref = _as_asset_ref(item)
        if ref:
            refs.append(ref)
    return refs


_ASSET_UPLOAD_TYPES = frozenset({"image", "audio", "video", "document"})


_ASSET_NAME_ERROR = "文件名含非法字符。只允许字母、数字、中文、-、_。"


_ASSET_STEM_RE = re.compile(r"^[A-Za-z0-9\u4e00-\u9fff_-]+$")


_ASSET_EXT_RE = re.compile(r"^[A-Za-z0-9]{1,8}$")


class AssetFilenameError(ValueError):
    """Upload filename failed charset / path cleaning."""


def _clean_upload_filename(raw: str) -> str:
    """Drop directories and normalize Unicode. Does not rewrite charset."""
    name = Path(str(raw or "").replace("\\", "/")).name.strip()
    return unicodedata.normalize("NFC", name)


def _validate_asset_filename(raw: str) -> str:
    """Return cleaned basename, or raise AssetFilenameError."""
    cleaned = _clean_upload_filename(raw)
    if not cleaned or cleaned in {".", ".."}:
        raise AssetFilenameError(_ASSET_NAME_ERROR)
    stem = Path(cleaned).stem
    suffix = Path(cleaned).suffix.lower()
    if not stem or not _ASSET_STEM_RE.fullmatch(stem):
        raise AssetFilenameError(_ASSET_NAME_ERROR)
    if len(stem) > 80:
        raise AssetFilenameError(_ASSET_NAME_ERROR)
    if suffix:
        ext = suffix.lstrip(".")
        if not _ASSET_EXT_RE.fullmatch(ext):
            raise AssetFilenameError(_ASSET_NAME_ERROR)
        return f"{stem}.{ext}"
    return stem


def _safe_on_disk_name(original: str, *, prefix: str) -> str:
    """Filesystem key: {prefix}_{validated_basename}."""
    validated = _validate_asset_filename(original)
    token = str(prefix or "").strip() or uuid.uuid4().hex[:12]
    return f"{token}_{validated}"


def _infer_asset_type(*, mime_type: str, filename: str, explicit: str) -> str:
    raw = str(explicit or "").strip().lower()
    if raw in _ASSET_UPLOAD_TYPES:
        return raw
    mime = str(mime_type or "").strip().lower()
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("audio/"):
        return "audio"
    if mime.startswith("video/"):
        return "video"
    name = str(filename or "").strip().lower()
    if name.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".bmp")):
        return "image"
    if name.endswith((".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac")):
        return "audio"
    if name.endswith((".mp4", ".mov", ".m4v", ".webm", ".mkv")):
        return "video"
    if name.endswith((".pdf", ".doc", ".docx", ".txt", ".rtf")):
        return "document"
    return "image"


def _guess_mime(filename: str, fallback: str = "application/octet-stream") -> str:
    mime, _ = mimetypes.guess_type(filename or "")
    return (mime or "").strip() or fallback


def _asset_representation_storage(storage: dict, representation: str) -> dict:
    """Map logical representation → img_server keys (original vs preview thumbnail)."""
    base = dict(storage or {})
    rep = str(representation or "original").strip().lower()
    if rep not in ("preview", "thumbnail"):
        return base
    preview_key = str(base.get("preview_key") or base.get("cloud_preview_key") or "").strip()
    if not preview_key:
        return base
    out = dict(base)
    out["key"] = preview_key
    cloud_preview = str(base.get("cloud_preview_key") or preview_key).strip()
    if cloud_preview:
        out["cloud_key"] = cloud_preview
    return out


_ASSET_META_KEYS = (
    "asset_id",
    "type",
    "mime_type",
    "size_bytes",
    "size",
    "status",
    "metadata",
    "created_at",
    "updated_at",
    "expires_at",
)


_STORAGE_URL_KEYS = frozenset({"url", "photo_url", "image_url"})


def _asset_metadata_only(record: dict) -> dict:
    record = record or {}
    out = {k: record[k] for k in _ASSET_META_KEYS if record.get(k) is not None}
    aid = str(record.get("asset_id") or "").strip()
    if aid:
        out["asset_id"] = aid
    return out


def _asset_stream_href(asset_id: str, intent_id: str, *, representation: str = "original") -> str:
    params = {"intent_id": str(intent_id or "").strip()}
    rep = str(representation or "original").strip().lower()
    if rep and rep != "original":
        params["representation"] = rep
    qs = urllib.parse.urlencode(params)
    return "/api/v1/assets/%s/content?%s" % (urllib.parse.quote(str(asset_id), safe=""), qs)


def _url_asset_target(record: dict) -> str:
    """url 资产的授权目标链接（metadata.url_target，仅 type=url 携带）。"""
    meta = (record or {}).get("metadata")
    meta = meta if isinstance(meta, dict) else {}
    raw = str(meta.get("url_target") or "").strip()
    try:
        parsed = urllib.parse.urlparse(raw)
    except Exception:
        return ""
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return raw
    return ""


def _asset_runtime_storage(storage: dict) -> dict:
    if not isinstance(storage, dict):
        return {}
    return {k: v for k, v in storage.items() if k not in _STORAGE_URL_KEYS}


def _asset_endpoint_view(record: dict, intent_id: str) -> dict:
    out = _asset_metadata_only(record)
    if str((record or {}).get("type") or "").strip().lower() == "url":
        target = _url_asset_target(record)
        if target:
            out["url"] = target
    aid = str((record or {}).get("asset_id") or "").strip()
    iid = str(intent_id or "").strip()
    if aid and iid:
        storage = (record or {}).get("storage")
        rep = "original"
        if isinstance(storage, dict):
            has_preview = bool(
                str(storage.get("preview_key") or storage.get("cloud_preview_key") or "").strip()
            )
            has_original = bool(str(storage.get("key") or storage.get("cloud_key") or "").strip())
            if has_preview and not has_original:
                rep = "preview"
            elif has_preview:
                rep = "preview"
        out["stream"] = {"href": _asset_stream_href(aid, iid, representation=rep)}
    return out


def _asset_runtime_view(record: dict) -> dict:
    out = _asset_metadata_only(record)
    if str((record or {}).get("type") or "").strip().lower() == "url":
        target = _url_asset_target(record)
        if target:
            out["url"] = target
    storage = _asset_runtime_storage((record or {}).get("storage"))
    if storage:
        out["storage"] = storage
    return out


def _asset_public_view(record: dict, *, include_storage: bool = False) -> dict:
    """Metadata-only snapshot (no storage URLs / no url-asset target). Legacy
    include_storage ignored: storage URLs are never handed to the public."""
    out = _asset_metadata_only(record)
    meta = out.get("metadata")
    if isinstance(meta, dict) and "url_target" in meta:
        out["metadata"] = {k: v for k, v in meta.items() if k != "url_target"}
    return out


def _parse_asset_day_window(day: str, timezone_name: str | None) -> tuple[float, float] | None:
    """Return [start, end) unix seconds for day=today|yesterday|YYYY-MM-DD in timezone."""
    raw = str(day or "").strip().lower()
    if not raw:
        return None
    tz_name = str(timezone_name or "").strip() or "Asia/Shanghai"
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("Asia/Shanghai")
    now = datetime.now(tz)
    if raw in ("today", "今天"):
        start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif raw in ("yesterday", "昨天"):
        start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    else:
        try:
            y, m, d = [int(p) for p in raw.split("-", 2)]
            start_dt = datetime(y, m, d, tzinfo=tz)
        except (TypeError, ValueError):
            return None
    end_dt = start_dt + timedelta(days=1)
    return start_dt.timestamp(), end_dt.timestamp()


def _parse_asset_time_bound(raw: str | None) -> float | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        pass
    try:
        # ISO-8601; treat naive as local/Asia/Shanghai wall time.
        if text.endswith("Z"):
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        return dt.timestamp()
    except ValueError:
        return None
