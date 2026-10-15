"""Notify.speak / wake-echo execution_plan step helpers."""
from __future__ import annotations

WAKE_ECHO_CAPABILITY = "voicewakeup.echo"


def notify_speak_plan_step(issuer_id, text, step=1):
    return {
        "step": int(step),
        "capability": "notify.speak",
        "assigned_edge_id": str(issuer_id or "").strip(),
        "input_constrict": {"text": text},
        "output_constrict": {},
    }


def wake_echo_plan_step(issuer_id, text, step=1):
    return {
        "step": int(step),
        "capability": WAKE_ECHO_CAPABILITY,
        "assigned_edge_id": str(issuer_id or "").strip(),
        "input_constrict": {"text": text},
        "output_constrict": {
            "echo_text": {"type": "string", "data_dest": "context"},
        },
    }


def speak_text_token(step):
    ic = step.get("input_constrict") if isinstance(step.get("input_constrict"), dict) else {}
    return str(ic.get("text") or "").strip()


def drop_unproducible_speak_steps(plan, *, plan_emits_field):
    steps = [dict(s) for s in (plan or []) if isinstance(s, dict)]
    producers = [
        s
        for s in steps
        if str(s.get("capability") or "").strip()
        not in ("notify.speak", WAKE_ECHO_CAPABILITY)
    ]
    kept = []
    for step in steps:
        cap = str(step.get("capability") or "").strip()
        if cap == "notify.speak":
            token = speak_text_token(step)
            if token.startswith("$") and not plan_emits_field(producers, token):
                continue
        kept.append(step)
    for idx, step in enumerate(kept, start=1):
        step["step"] = idx
    return kept
