from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.registries.static_registry import StaticEffectRegistry, StaticRegistry


@dataclass(frozen=True, slots=True)
class MoveRegistryCacheStats:
    hits: int = 0
    misses: int = 0
    size: int = 0


_cache: dict[tuple[str, int, int], StaticEffectRegistry] = {}
_hits = 0
_misses = 0
_observer: Callable[[str, tuple[str, int, int]], None] | None = None


def _state_from_context(context: MatchState | object) -> MatchState:
    if isinstance(context, MatchState):
        return context
    state = getattr(context, "state", None)
    if isinstance(state, MatchState):
        return state
    getter = getattr(getattr(context, "cards", None), "_state_getter", None)
    if callable(getter):
        found = getter()
        if isinstance(found, MatchState):
            return found
    raise TypeError("move registry cache requires a MatchState or runtime context")


def _query_from_context(context: object):
    query = getattr(getattr(context, "cards", None), "_query", None)
    if query is not None:
        return query
    query = getattr(context, "query", None)
    if query is not None:
        return query
    raise TypeError("move registry cache requires a context with a QueryService")


def _cache_key(state: MatchState) -> tuple[str, int, int]:
    return (str(state.ctx.matchID), int(state.ctx._stateID), int(state.G.staticEffectsVersion))


def get_or_build_move_registry(context: MatchState | object) -> StaticEffectRegistry:
    global _hits, _misses
    state = _state_from_context(context)
    key = _cache_key(state)
    cached = _cache.get(key)
    if cached is not None:
        _hits += 1
        if _observer:
            _observer("hit", key)
        return cached
    query = _query_from_context(context)
    registry = StaticRegistry().build(state, query)
    _cache[key] = registry
    _misses += 1
    if _observer:
        _observer("miss", key)
    return registry


def build_registry_from_match_state(state: MatchState, query) -> StaticEffectRegistry:
    return StaticRegistry().build(state, query)


def set_move_registry_cache_observer(observer: Callable[[str, tuple[str, int, int]], None] | None) -> None:
    global _observer
    _observer = observer


def get_move_registry_cache_stats() -> MoveRegistryCacheStats:
    return MoveRegistryCacheStats(hits=_hits, misses=_misses, size=len(_cache))


def clear_move_registry_cache() -> None:
    global _hits, _misses
    _cache.clear()
    _hits = 0
    _misses = 0


getOrBuildMoveRegistry = get_or_build_move_registry
buildRegistryFromMatchState = build_registry_from_match_state


__all__ = [
    "MoveRegistryCacheStats",
    "buildRegistryFromMatchState",
    "build_registry_from_match_state",
    "clear_move_registry_cache",
    "getOrBuildMoveRegistry",
    "get_move_registry_cache_stats",
    "get_or_build_move_registry",
    "set_move_registry_cache_observer",
]
