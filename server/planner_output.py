"""Planner output schemas, JSON parsing and capability gap normalization."""
from __future__ import annotations

import json
import re


# Legacy / model-invented ids → canonical capability_id for gap reports.
_CAPABILITY_ID_ALIASES = {
    "ac.set": "climate.set",
    "hvac.set": "climate.set",
    "air_conditioner.set": "climate.set",
}


_PRESENTATION_SCHEMA = {
    "type": "text | image | audio — audio means the user should hear the result spoken; the control plane turns that into an execution step on the issuing runtime",
    "from": "summary | answer_text | time_text | asset_ref | state — which execution field fills the payload",
    "channel": "iphone | kindle | android | speaker",
    "endpoint": "optional; only when the user/intent explicitly names a destination. Omit to use Input Source Affinity (default Response Target = Input Source). Never copy an Execution Target.",
    "text": "optional",
    "asset_ref": "optional AssetRef {asset_id, type, mime_type?} when from=asset_ref; never a URL or filesystem path",
    "audio_url": "optional",
}


# Planner-facing presentation fields (must match OUTPUT_SCHEMA; no extra keys).
_PLANNER_PRESENTATION_SCHEMA = {
    "type": "text | image | audio | document",
    "from": "optional execution field some plan step emits: time_text | answer_text | summary | state | status_text | asset_ref | …",
    "endpoint": "optional; only when the user explicitly names a destination; omit for Input Source Affinity",
}


_PLANNER_OUTPUT_SCHEMA = {
    "type": "object",
    "required": [
        "goal",
        "required_capabilities",
        "reason",
        "plan",
        "presentation",
        "missing_capabilities",
        "better_capabilities",
    ],
    "additionalProperties": False,
    "properties": {
        "goal": {"type": "string"},
        "required_capabilities": {
            "type": "array",
            "items": {"type": "string", "description": "capability_id copied from Available Capabilities"},
        },
        "reason": {"type": "string"},
        "plan": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["step", "capability", "input_constrict", "output_constrict", "execution_timing"],
                "additionalProperties": False,
                "properties": {
                    "step": {"type": "integer"},
                    "capability": {
                        "type": "string",
                        "description": "exact capability_id from a matching Available Capabilities row",
                    },
                    "input_constrict": {
                        "type": "object",
                        "description": "keys from that row's input_schema; $key references allowed",
                    },
                    "output_constrict": {
                        "type": "object",
                        "description": "keys this step exposes for later $key or presentation.from; value is {type, data_dest}",
                        "additionalProperties": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string"},
                                "data_dest": {"type": "string", "enum": ["context"]},
                            },
                        },
                    },
                    "execution_timing": {
                        "type": "object",
                        "required": ["mode"],
                        "properties": {
                            "mode": {"type": "string", "enum": ["immediate", "delay", "interval", "cron"]},
                            "exec_time": {
                                "type": "integer",
                                "description": "Unix milliseconds for delay; from intent_base_time, not model time",
                            },
                            "first_exec_time": {
                                "type": "integer",
                                "description": "Unix milliseconds for interval/cron; from intent_base_time",
                            },
                            "interval_sec": {"type": "integer"},
                            "end_time": {"type": "integer"},
                            "count": {"type": "integer"},
                            "cron_expr": {"type": "string"},
                            "timezone": {"type": "string"},
                        },
                    },
                    "assigned_edge_id": {
                        "type": "string",
                        "description": "edge_id from the matching Available Capabilities row",
                    },
                },
            },
        },
        "presentation": {
            "type": "object",
            "required": ["type"],
            "additionalProperties": False,
            "properties": {
                "type": {"type": "string", "enum": ["text", "image", "audio", "document"]},
                "from": {"type": "string"},
                "endpoint": {"type": "string"},
            },
        },
        "missing_capabilities": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["capability", "reason"],
                "properties": {
                    "capability": {"type": "string"},
                    "reason": {"type": "string"},
                },
            },
        },
        "better_capabilities": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["capability", "reason"],
                "properties": {
                    "capability": {"type": "string"},
                    "reason": {"type": "string"},
                },
            },
        },
    },
}


def extract_llm_output(llm_answer):
    if not llm_answer:
        return {}
    try:
        output = json.loads(llm_answer) if isinstance(llm_answer, str) else llm_answer
    except (TypeError, ValueError):
        return {}
    return output if isinstance(output, dict) else {}


def extract_llm_output_relaxed(llm_answer):
    """Qwen shadow only: strip fences / leading junk. Doubao path stays strict."""
    got = extract_llm_output(llm_answer)
    if got:
        return got
    text = str(llm_answer or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, count=1, flags=re.IGNORECASE)
        text = re.sub(r"\s*```\s*$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        output = json.loads(text[start : end + 1])
    except (TypeError, ValueError):
        return {}
    return output if isinstance(output, dict) else {}


def _as_capability_notes(raw):
    if raw is None:
        return []
    if not isinstance(raw, list):
        raw = [raw]
    notes = []
    for item in raw:
        if isinstance(item, str):
            cap = item.strip()
            if cap:
                notes.append({"capability": cap, "reason": ""})
            continue
        if not isinstance(item, dict):
            continue
        cap = str(
            item.get("capability")
            or item.get("capability_id")
            or item.get("name")
            or ""
        ).strip()
        reason = str(item.get("reason") or item.get("why") or "").strip()
        if cap or reason:
            notes.append({"capability": cap, "reason": reason})
    return notes


def extract_llm_capability_notes(llm_answer, catalog=None):
    output = extract_llm_output(llm_answer)
    return {
        "missing_capabilities": _normalize_capability_notes(
            output.get("missing_capabilities"), catalog
        ),
        "better_capabilities": _normalize_capability_notes(
            output.get("better_capabilities"), catalog
        ),
    }


def extract_llm_presentation(llm_answer):
    """Planner-owned Presentation decision. Not a capability step."""
    if not llm_answer:
        return {}
    try:
        output = json.loads(llm_answer) if isinstance(llm_answer, str) else llm_answer
    except (TypeError, ValueError):
        return {}
    if not isinstance(output, dict):
        return {}
    return _normalize_presentation_plan(output.get("presentation"))


def _normalize_presentation_plan(raw):
    if not isinstance(raw, dict):
        return {}
    ptype = str(raw.get("type") or "").strip().lower()
    if ptype not in ("text", "image", "audio", "document"):
        return {}
    src = str(raw.get("from") or raw.get("payload_from") or "").strip()
    out = {"type": ptype}
    if src:
        out["from"] = src
    channel = str(raw.get("channel") or "").strip().lower()
    if channel in ("iphone", "kindle", "android", "speaker"):
        out["channel"] = channel
    endpoint = str(raw.get("endpoint") or "").strip()
    if endpoint:
        out["endpoint"] = endpoint
    endpoint_id = str(raw.get("endpoint_id") or "").strip()
    if endpoint_id:
        out["endpoint_id"] = endpoint_id
    return out


def _normalize_capability_id(cap: str, catalog_ids: set[str] | frozenset[str]) -> str:
    cid = str(cap or "").strip()
    if not cid:
        return ""
    if cid in catalog_ids:
        return cid
    aliased = _CAPABILITY_ID_ALIASES.get(cid)
    if aliased and aliased in catalog_ids:
        return aliased
    return aliased or cid


def _normalize_capability_notes(raw, catalog=None):
    catalog_ids = frozenset(
        str(row.get("capability_id") or "").strip()
        for row in (catalog or [])
        if isinstance(row, dict) and str(row.get("capability_id") or "").strip()
    )
    notes = _as_capability_notes(raw)
    out: list[dict[str, str]] = []
    for note in notes:
        cap = str(note.get("capability") or "").strip()
        reason = str(note.get("reason") or "").strip()
        if cap in catalog_ids:
            # Advertised capability cannot be "missing".
            continue
        normalized = _normalize_capability_id(cap, catalog_ids)
        if normalized in catalog_ids:
            continue
        if normalized or reason:
            out.append({"capability": normalized, "reason": reason})
    return out


def _score_capability_row_for_text(user_text: str, row: dict) -> int:
    raw = str(user_text or "")
    if not raw or not isinstance(row, dict):
        return 0
    score = 0
    for trigger in row.get("typical_triggers") or []:
        token = str(trigger or "").strip()
        if token and token in raw:
            score += 3
    display = str(row.get("display_name") or "").strip()
    if display and display in raw:
        score += 5
    recognize = str(row.get("planner_recognize") or "")
    if display and display in recognize and any(
        kw in raw for kw in ("空调", "制冷", "制热", "扫风")
    ):
        score += 2
    return score


def _catalog_matches_utterance(user_text: str, catalog) -> bool:
    """True when the catalog clearly advertises a row for this utterance."""
    best = 0
    for row in catalog or []:
        if not isinstance(row, dict):
            continue
        best = max(best, _score_capability_row_for_text(user_text, row))
    return best >= 3


def _planner_empty_plan_unreliable(user_text: str, llm_answer: str, catalog) -> bool:
    """Empty plan is suspect when the live catalog already matches the utterance."""
    output = extract_llm_output(llm_answer)
    plan = output.get("plan") if isinstance(output, dict) else None
    if isinstance(plan, list) and plan:
        return False
    return _catalog_matches_utterance(user_text, catalog)
