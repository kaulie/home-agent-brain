"""Replaceable LLM transport boundary for planner and ad-hoc chat calls.

Default implementation is Volcano Ark (see ``volcano_ark_client``). Tests and
future providers swap ``get_planner_transport()`` without touching ``home_brain``.
"""
from __future__ import annotations

from typing import Callable, Protocol

try:
    from .volcano_ark_client import ChatCompletionResponse, post_chat_completions
except ImportError:  # pragma: no cover
    from volcano_ark_client import ChatCompletionResponse, post_chat_completions  # type: ignore

PlannerTransport = Callable[[dict, float], ChatCompletionResponse]

DEFAULT_PROVIDER_ID = "volcano_ark"

_planner_transport: PlannerTransport | None = None
_active_provider_id: str = DEFAULT_PROVIDER_ID


class LLMProvider(Protocol):
    """Provider plugin shape for non-Ark LLM backends."""

    provider_id: str

    def post_chat_completions(self, payload: dict, timeout: float) -> ChatCompletionResponse:
        ...


def default_planner_transport() -> PlannerTransport:
    return post_chat_completions


def get_planner_transport() -> PlannerTransport:
    if _planner_transport is not None:
        return _planner_transport
    return default_planner_transport()


def set_planner_transport(transport: PlannerTransport | None, *, provider_id: str | None = None) -> None:
    global _planner_transport, _active_provider_id
    _planner_transport = transport
    if provider_id:
        _active_provider_id = provider_id
    elif transport is None:
        _active_provider_id = DEFAULT_PROVIDER_ID


def active_planner_provider_id() -> str:
    return _active_provider_id
