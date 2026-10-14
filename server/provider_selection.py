"""Pure matching of named runtime instances and appliance inputs."""
from __future__ import annotations

import re


def _provider_display_name(svc, view, edge_id):
    for raw in (
        (svc or {}).get("display_name"),
        (view or {}).get("display_name"),
        (svc or {}).get("edge_name"),
        edge_id,
    ):
        name = str(raw or "").strip()
        if name:
            return name
    return str(edge_id or "")


def _instance_key(row):
    name = str((row or {}).get("display_name") or "").strip()
    sid = str((row or {}).get("service_id") or "").strip()
    return name or sid


def _group_providers_by_instance(providers):
    groups = {}
    for row in providers or []:
        key = _instance_key(row)
        if not key:
            key = str((row or {}).get("edge_id") or "")
        groups.setdefault(key, []).append(row)
    return groups


def _ambiguous_capability_edge_msg(providers):
    names = []
    seen = set()
    for row in providers or []:
        name = _instance_key(row)
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    listed = "、".join(names) if names else "（未命名）"
    return (
        "家里有多台同能力设备，请说清楚要用哪一台。"
        f"候选：{listed}。"
    )


def _is_mac_runtime_row(row):
    dt = str((row or {}).get("device_type") or "").strip().lower()
    if dt == "mac":
        return True
    hint = str((row or {}).get("client_hint") or "").strip().lower()
    return "laptop" in hint or hint in ("living-room-mac", "livingroom-mac")


def _user_text_matches_instance(text, instance_key):
    blob = str(text or "").strip().casefold()
    key = str(instance_key or "").strip()
    if not blob or not key:
        return False
    folded_key = key.casefold()
    if folded_key in blob:
        return True
    for token in _instance_match_tokens(key):
        if token in blob:
            return True
    return False


_APPLIANCE_TOKEN_NOISE = frozenset(
    {
        "camera",
        "photo",
        "相机",
        "拍照",
        "cam",
        "the",
        "and",
        "or",
        "on",
        "ok",
    }
)


def _instance_match_tokens(instance_key: str) -> list[str]:
    key = str(instance_key or "").strip()
    if not key:
        return []
    tokens: list[str] = []
    seen: set[str] = set()
    for raw in (key, key.replace(".", " ").replace("_", " ")):
        folded = raw.casefold()
        if folded and folded not in seen:
            seen.add(folded)
            tokens.append(folded)
        for part in re.split(r"[\s_/·\-]+", raw):
            part = part.strip()
            if len(part) < 2:
                continue
            folded_part = part.casefold()
            if folded_part not in seen:
                seen.add(folded_part)
                tokens.append(folded_part)
    return [t for t in tokens if t not in _APPLIANCE_TOKEN_NOISE]


def _service_id_matches_text(service_id, text) -> bool:
    sid = str(service_id or "").strip()
    if not sid:
        return False
    return _user_text_matches_instance(text, sid.replace(".", " ").replace("_", " "))


def _matched_instance_groups(groups, text):
    hits = []
    for key, rows in (groups or {}).items():
        if _user_text_matches_instance(text, key):
            hits.append((key, rows))
            continue
        for row in rows:
            if _service_id_matches_text(row.get("service_id"), text):
                hits.append((key, rows))
                break
    if len(hits) > 1:
        hits.sort(key=lambda item: len(item[0]), reverse=True)
        longest = len(hits[0][0])
        hits = [item for item in hits if len(item[0]) == longest]
    return hits


def _step_appliance_name(step):
    inp = (step or {}).get("input_constrict")
    if not isinstance(inp, dict):
        return ""
    for field in ("appliance", "label", "device_id"):
        val = str(inp.get(field) or "").strip()
        if val:
            return val
    return ""


def _ensure_appliance_param(step, provider):
    name = str((provider or {}).get("display_name") or "").strip()
    if not name or not isinstance(step, dict):
        return
    inp = step.get("input_constrict")
    if not isinstance(inp, dict):
        inp = {}
        step["input_constrict"] = inp
    if not str(inp.get("appliance") or "").strip():
        inp["appliance"] = name
