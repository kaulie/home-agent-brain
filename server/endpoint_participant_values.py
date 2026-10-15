"""Participant / endpoint declarations on registration records (no Flask, no DB)."""
from __future__ import annotations


def endpoint_supported_types(rec):
    types = []
    raw = rec.get("endpoints") if isinstance(rec, dict) else None
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                for t in (
                    item.get("supported")
                    or item.get("types")
                    or item.get("supported_presentation")
                    or []
                ):
                    types.append(str(t))
                kind = item.get("type") or item.get("channel")
                if kind:
                    kind_s = str(kind)
                    if kind_s not in types:
                        types.append(kind_s)
                    if kind_s == "display":
                        for implied in ("image", "text"):
                            if implied not in types:
                                types.append(implied)
            elif item:
                types.append(str(item))
    return types or ["text", "image"]


def endpoint_ids_for_participant(rec, pres_type=None):
    ids = []
    raw = rec.get("endpoints") if isinstance(rec, dict) else None
    if not isinstance(raw, list):
        return ids
    want = str(pres_type or "").strip().lower()
    for item in raw:
        if not isinstance(item, dict):
            continue
        eid = str(item.get("endpoint_id") or item.get("id") or "").strip()
        if not eid:
            continue
        if want:
            supported = [
                str(t).lower()
                for t in (
                    item.get("supported")
                    or item.get("types")
                    or item.get("supported_presentation")
                    or []
                )
            ]
            kind = str(item.get("type") or item.get("channel") or "").lower()
            if kind == "display" and want in ("image", "text", "video", "html", "audio"):
                ids.append(eid)
                continue
            if supported and want not in supported and want != kind:
                continue
        ids.append(eid)
    return ids


def primary_endpoint_id(rec, pres_type=None):
    ids = endpoint_ids_for_participant(rec, pres_type)
    return ids[0] if ids else ""


def is_endpoint_participant(rec):
    if not isinstance(rec, dict) or not rec:
        return False
    if rec.get("role_endpoint"):
        return True
    return "endpoint" in (rec.get("roles") or [])


def declared_role(rec, role):
    role = str(role or "").strip()
    if not rec or not role:
        return False
    if rec.get(f"role_{role}"):
        return True
    return role in (rec.get("roles") or [])


def runtime_capabilities(rec):
    out = []
    for svc in rec.get("services") or []:
        if not isinstance(svc, dict):
            continue
        service_id = str(svc.get("service_id") or "").strip()
        group = str(svc.get("group") or "").strip()
        for cap in svc.get("capabilities") or []:
            if not isinstance(cap, dict):
                continue
            cid = str(cap.get("capability_id") or "").strip()
            if not cid:
                continue
            out.append(
                {
                    "capability_id": cid,
                    "service_id": service_id,
                    "group": group,
                    "kind": str(cap.get("kind") or "").strip().lower(),
                    "role": cap.get("role") or "",
                    "planner_recognize": cap.get("planner_recognize") or "",
                    "typical_triggers": list(cap.get("typical_triggers") or [])
                    if isinstance(cap.get("typical_triggers"), list)
                    else [],
                    "do_not_dispatch": list(cap.get("do_not_dispatch") or [])
                    if isinstance(cap.get("do_not_dispatch"), list)
                    else [],
                    "description": cap.get("description") or "",
                }
            )
    return out


def declared_capability(rec, capability_id):
    want = str(capability_id or "").strip()
    if not rec or not want:
        return False
    for cap in runtime_capabilities(rec):
        if cap.get("capability_id") == want:
            return True
    return False


def endpoint_supports_type(rec, pres_type):
    if not pres_type:
        return True
    types = [str(t).lower() for t in endpoint_supported_types(rec)]
    return str(pres_type).lower() in types


def resolve_endpoint_token(token, listed, listed_map):
    token = str(token or "").strip()
    if not token:
        return ""
    if token in listed_map:
        return token
    for pid, rec in listed:
        if primary_endpoint_id(rec) == token:
            return pid
        raw = rec.get("endpoints") if isinstance(rec, dict) else None
        if not isinstance(raw, list):
            continue
        for item in raw:
            if not isinstance(item, dict):
                continue
            eid = str(item.get("endpoint_id") or item.get("id") or "").strip()
            if eid == token:
                return pid
    return ""


def tv_response_participant(listed):
    for pid, rec in listed:
        dt = str((rec or {}).get("device_type") or "").lower()
        if dt in ("chromecast", "tv", "google_tv", "cast"):
            return pid
        raw = (rec or {}).get("endpoints") if isinstance(rec, dict) else None
        if not isinstance(raw, list):
            continue
        for item in raw:
            if not isinstance(item, dict):
                continue
            blob = " ".join(
                str(item.get(k) or "")
                for k in ("endpoint_id", "id", "type", "channel")
            ).lower()
            if any(mark in blob for mark in ("chromecast", "living_room_tv", "living-room-tv")):
                return pid
            if "tv" in blob.split() or blob.endswith(".tv") or blob.startswith("tv"):
                return pid
    return ""
