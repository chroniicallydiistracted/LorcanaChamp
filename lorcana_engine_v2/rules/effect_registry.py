from __future__ import annotations

from dataclasses import dataclass

from lorcana_engine_v2.core.ids import PlayerId


@dataclass(frozen=True, slots=True)
class EffectWindow:
    startsAtTurn: int
    expiresAtTurn: int


def resolve_effect_window(
    current_turn: int,
    duration: object,
    *,
    current_player_id: PlayerId | str | None = None,
    target_owner_id: PlayerId | str | None = None,
) -> EffectWindow:
    turn = current_turn if isinstance(current_turn, int) and current_turn >= 1 else 0
    if turn == 0:
        return EffectWindow(startsAtTurn=0, expiresAtTurn=0)

    if isinstance(duration, str):
        if duration == "next-turn":
            return EffectWindow(startsAtTurn=turn + 1, expiresAtTurn=turn + 1)
        if duration == "their-next-turn":
            if current_player_id is not None and target_owner_id is not None and str(current_player_id) != str(target_owner_id):
                return EffectWindow(startsAtTurn=turn + 1, expiresAtTurn=turn + 1)
            return EffectWindow(startsAtTurn=turn + 2, expiresAtTurn=turn + 2)
        if duration == "until-start-of-next-turn":
            return EffectWindow(startsAtTurn=turn, expiresAtTurn=turn + 1)
        if duration in {"permanent", "while-in-play"}:
            return EffectWindow(startsAtTurn=turn, expiresAtTurn=2**53 - 1)
        return EffectWindow(startsAtTurn=turn, expiresAtTurn=turn)

    return EffectWindow(startsAtTurn=turn, expiresAtTurn=turn)


def is_effect_expired(lifecycle: object, current_turn: int) -> bool:
    expires_at_turn = getattr(lifecycle, "expiresAtTurn", None)
    if expires_at_turn is None and isinstance(lifecycle, dict):
        expires_at_turn = lifecycle.get("expiresAtTurn")
    return isinstance(expires_at_turn, int) and expires_at_turn < current_turn


__all__ = ["EffectWindow", "is_effect_expired", "resolve_effect_window"]
