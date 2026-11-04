"""Replaceable LLM transport boundary for planner and ad-hoc chat calls.

Default provider is DeepSeek (see ``deepseek_client``). Set
``BRAIN_LLM_PROVIDER=volcano_ark`` to use Volcano Ark. Tests swap
``get_planner_transport()`` without touching ``home_brain``.
"""
from __future__ import annotations

from typing import Callable, Protocol

try:
    from . import brain_env
    from . import deepseek_client as deepseek
    from .volcano_ark_client import (
        ARK_HTTP_401_SENTINEL,
        ChatCompletionResponse,
        build_planner_payload as ark_build_planner_payload,
        build_runner_payload as ark_build_runner_payload,
        post_chat_completions as ark_post_chat_completions,
    )
except ImportError:  # pragma: no cover
    import brain_env  # type: ignore
    import deepseek_client as deepseek  # type: ignore
    from volcano_ark_client import (  # type: ignore
        ARK_HTTP_401_SENTINEL,
        ChatCompletionResponse,
        build_planner_payload as ark_build_planner_payload,
        build_runner_payload as ark_build_runner_payload,
        post_chat_completions as ark_post_chat_completions,
    )

PlannerTransport = Callable[[dict, float], ChatCompletionResponse]

PROVIDER_DEEPSEEK = "deepseek"
PROVIDER_VOLCANO_ARK = "volcano_ark"
DEFAULT_PROVIDER_ID = PROVIDER_DEEPSEEK

_planner_transport: PlannerTransport | None = None
_active_provider_id: str = DEFAULT_PROVIDER_ID


class LLMProvider(Protocol):
    """Provider plugin shape for LLM backends."""

    provider_id: str

    def post_chat_completions(self, payload: dict, timeout: float) -> ChatCompletionResponse:
        ...


def normalize_provider_id(raw: str | None) -> str:
    text = str(raw or "").strip().lower()
    if text in ("", "deepseek", "deepseek_api"):
        return PROVIDER_DEEPSEEK
    if text in ("volcano_ark", "ark", "doubao", "volc"):
        return PROVIDER_VOLCANO_ARK
    # Allow custom/test provider ids through unchanged.
    if text:
        return text
    return DEFAULT_PROVIDER_ID


def default_planner_transport(provider_id: str | None = None) -> PlannerTransport:
    pid = normalize_provider_id(provider_id or _active_provider_id)
    if pid == PROVIDER_VOLCANO_ARK:
        return ark_post_chat_completions
    return deepseek.post_chat_completions


def get_planner_transport() -> PlannerTransport:
    if _planner_transport is not None:
        return _planner_transport
    return default_planner_transport(_active_provider_id)


def set_planner_transport(transport: PlannerTransport | None, *, provider_id: str | None = None) -> None:
    global _planner_transport, _active_provider_id
    _planner_transport = transport
    if provider_id:
        _active_provider_id = normalize_provider_id(provider_id)
    elif transport is None:
        _active_provider_id = normalize_provider_id(getattr(brain_env, "LLM_PROVIDER", None))


def active_planner_provider_id() -> str:
    return _active_provider_id


def build_planner_payload(system_prompt: str, user_prompt: str, *, model: str | None = None) -> dict:
    if _active_provider_id == PROVIDER_VOLCANO_ARK:
        return ark_build_planner_payload(system_prompt, user_prompt, model=model)
    return deepseek.build_planner_payload(system_prompt, user_prompt, model=model)


def build_runner_payload(user_content: str, *, model: str | None = None) -> dict:
    if _active_provider_id == PROVIDER_VOLCANO_ARK:
        return ark_build_runner_payload(user_content, model=model)
    return deepseek.build_runner_payload(user_content, model=model)


def planner_cloud_service_id(provider_id: str | None = None) -> str:
    pid = normalize_provider_id(provider_id or _active_provider_id)
    if pid == PROVIDER_VOLCANO_ARK:
        return "ark.planner"
    return "deepseek.planner"


def configure_from_env() -> str:
    """Bind default transport from ``BRAIN_LLM_PROVIDER`` / ``brain_env.LLM_PROVIDER``."""
    pid = normalize_provider_id(getattr(brain_env, "LLM_PROVIDER", None))
    set_planner_transport(None, provider_id=pid)
    return pid


configure_from_env()

# Re-export sentinel for callers that used volcano_ark_client directly.
__all__ = [
    "ARK_HTTP_401_SENTINEL",
    "ChatCompletionResponse",
    "DEFAULT_PROVIDER_ID",
    "PROVIDER_DEEPSEEK",
    "PROVIDER_VOLCANO_ARK",
    "LLMProvider",
    "active_planner_provider_id",
    "build_planner_payload",
    "build_runner_payload",
    "configure_from_env",
    "default_planner_transport",
    "get_planner_transport",
    "normalize_provider_id",
    "planner_cloud_service_id",
    "set_planner_transport",
]
