"""Upload asset bytes to co-located img-server or local gopropics store."""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

try:
    from .asset_values import _safe_on_disk_name
    from .brain_env import default_upload_dir
    from .intent_origin import instance_intent_origin
except ImportError:  # pragma: no cover
    from asset_values import _safe_on_disk_name  # type: ignore
    from brain_env import default_upload_dir  # type: ignore
    from intent_origin import instance_intent_origin  # type: ignore

UPLOAD_DIR = default_upload_dir()
_ASSET_UPLOAD_DIR: Path | None = None


def asset_upload_dir() -> Path:
    global _ASSET_UPLOAD_DIR
    if _ASSET_UPLOAD_DIR is None:
        _ASSET_UPLOAD_DIR = UPLOAD_DIR / "assets"
    return _ASSET_UPLOAD_DIR


def explicit_img_server_upload_url() -> str:
    return (
        os.environ.get("BRAIN_IMG_UPLOAD_URL")
        or os.environ.get("PHOTO_UPLOAD_URL")
        or ""
    ).strip().rstrip("/")


def img_server_upload_url() -> str:
    return explicit_img_server_upload_url() or "http://127.0.0.1:8080/api/v1/photos/upload"


def img_server_internal_base() -> str:
    try:
        parsed = urllib.parse.urlsplit(img_server_upload_url())
        if parsed.netloc:
            return "%s://%s" % ((parsed.scheme or "http"), parsed.netloc)
    except Exception:
        pass
    return "http://127.0.0.1:8080"


def use_local_upload_store() -> bool:
    if instance_intent_origin() != "cloud":
        return False
    return not explicit_img_server_upload_url()


def put_bytes_on_local_upload(
    data: bytes,
    *,
    filename: str,
    mime_type: str,
) -> dict:
    upload_dir = asset_upload_dir()
    upload_dir.mkdir(parents=True, exist_ok=True)
    saved_as = _safe_on_disk_name(filename, prefix=uuid.uuid4().hex[:8])
    dest = upload_dir / saved_as
    dest.write_bytes(data)
    return {
        "backend": "local_upload",
        "saved_as": saved_as,
        "public_base": "",
        "url": "",
    }


def img_server_health_public_base() -> str:
    upload_url = img_server_upload_url().rstrip("/")
    if not upload_url:
        return ""
    try:
        parsed = urllib.parse.urlsplit(upload_url)
        health_url = f"{parsed.scheme}://{parsed.netloc}/health"
        with urllib.request.urlopen(health_url, timeout=2.0) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        payload = json.loads(raw) if raw.strip() else {}
        base = str((payload or {}).get("public_base") or "").strip().rstrip("/")
        if base.startswith("http://") or base.startswith("https://"):
            return base
    except Exception:
        pass
    return ""


def lan_img_server_public_base() -> str:
    try:
        from mdns_service import lan_ipv4

        ip = (lan_ipv4() or "127.0.0.1").strip()
        if ip.startswith("127."):
            ip = "127.0.0.1"
        return f"http://{ip}:8080"
    except Exception:
        return "http://127.0.0.1:8080"


def img_server_public_base() -> str:
    explicit = (
        os.environ.get("BRAIN_IMG_PUBLIC_BASE")
        or os.environ.get("PHOTO_PUBLIC_BASE")
        or ""
    ).strip().rstrip("/")
    if explicit:
        return explicit
    if instance_intent_origin() == "cloud":
        return "http://115.190.153.53:8080"
    return img_server_health_public_base() or lan_img_server_public_base()


def put_bytes_on_img_server(
    data: bytes,
    *,
    filename: str,
    mime_type: str,
    timeout_sec: float = 20.0,
) -> dict:
    upload_url = img_server_upload_url()
    if not upload_url:
        raise RuntimeError("img-server upload URL is empty")
    safe_name = Path(filename or "upload.bin").name or "upload.bin"
    boundary = f"----BrainAsset{uuid.uuid4().hex}"
    mime = (mime_type or "application/octet-stream").strip() or "application/octet-stream"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{safe_name}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode("utf-8") + data + f"\r\n--{boundary}--\r\n".encode("utf-8")
    req = urllib.request.Request(
        upload_url,
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=float(timeout_sec)) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            code = int(resp.getcode() or 0)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"img-server HTTP {e.code}: {raw[:300]}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise RuntimeError(f"img-server unreachable: {e}") from e
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as e:
        raise RuntimeError(f"img-server response not JSON (http={code}): {raw[:200]}") from e
    if not isinstance(payload, dict) or not payload.get("ok"):
        raise RuntimeError(f"img-server rejected upload: {payload!r}"[:300])
    saved_as = str(payload.get("saved_as") or "").strip()
    if not saved_as:
        raise RuntimeError("img-server ok but missing saved_as")
    public_base = img_server_public_base()
    url = str(payload.get("url") or "").strip()
    if url.startswith("http://127.") or url.startswith("http://localhost"):
        url = f"{public_base}/{Path(saved_as).name}"
    elif not (url.startswith("http://") or url.startswith("https://")):
        url = f"{public_base}/{Path(saved_as).name}"
    return {
        "saved_as": saved_as,
        "public_base": public_base,
        "url": url,
    }


def store_uploaded_asset_bytes(
    data: bytes,
    *,
    filename: str,
    mime_type: str,
) -> dict:
    if use_local_upload_store():
        stored = put_bytes_on_local_upload(
            data, filename=filename, mime_type=mime_type
        )
        stored.setdefault("backend", "local_upload")
        return stored
    stored = put_bytes_on_img_server(
        data, filename=filename, mime_type=mime_type
    )
    stored.setdefault("backend", "img_server")
    return stored
