"""Input source context persisted on intents."""
from __future__ import annotations

SOURCE_INPUT_CAPABILITY = {
    "voice": "voice.input",
    "visual": "visual.input",
    "text": "text.input",
}
SOURCE_INPUT_ENDPOINT = {
    "voice": "microphone",
    "visual": "camera",
    "text": "keyboard",
}


def ncm_play_issuer_id(intent):
    intent = intent or {}
    ctx = intent.get("ctx_param") or intent.get("context") or {}
    if not isinstance(ctx, dict):
        ctx = {}
    src = ctx.get("source_context") or intent.get("source_context") or {}
    if isinstance(src, dict):
        for key in ("input_participant_id", "device_id"):
            pid = str(src.get(key) or "").strip()
            if pid:
                return pid
    return str(intent.get("edge_id") or intent.get("participant_id") or "").strip()


def issuer_participant_id(intent):
    intent = intent or {}
    return str(intent.get("edge_id") or intent.get("participant_id") or "").strip()


def build_source_context(edge_id, source, inbound=None):
    inbound = inbound if isinstance(inbound, dict) else {}
    raw = inbound.get("source_context") if isinstance(inbound.get("source_context"), dict) else {}
    source_l = str(source or "text").strip().lower() or "text"
    device_id = str(raw.get("device_id") or edge_id or "").strip()
    endpoint_id = str(raw.get("endpoint_id") or inbound.get("source_id") or "").strip()
    if not endpoint_id:
        endpoint_id = SOURCE_INPUT_ENDPOINT.get(source_l, "keyboard")
    capability_id = str(raw.get("capability_id") or "").strip()
    if not capability_id:
        capability_id = SOURCE_INPUT_CAPABILITY.get(source_l, "text.input")
    out = {}
    if device_id:
        out["device_id"] = device_id
    if endpoint_id:
        out["endpoint_id"] = endpoint_id
    if capability_id:
        out["capability_id"] = capability_id
    return out
