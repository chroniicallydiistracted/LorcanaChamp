from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class AmountContext:
    actor: int
    source_id: int
    target_id: int | None = None


class AmountResolver:
    def resolve(self, state, ctx, raw_amount: Any, context: AmountContext) -> int:
        if raw_amount is None:
            return 0
        if isinstance(raw_amount, bool):
            return int(raw_amount)
        if isinstance(raw_amount, int):
            return raw_amount
        if isinstance(raw_amount, str):
            return int(raw_amount) if raw_amount.lstrip("+-").isdigit() else 0
        if not isinstance(raw_amount, dict):
            return 0
        kind = raw_amount.get("type")
        if kind == "static":
            return int(raw_amount.get("amount") or raw_amount.get("value") or 0)
        if kind == "items-in-play":
            player = self._controller_from_raw(state, raw_amount, context)
            return len(ctx.query.items_in_play(state, player))
        if kind == "characters-in-play":
            player = self._controller_from_raw(state, raw_amount, context)
            return len(ctx.query.characters_in_play(state, player))
        if kind == "damage-on-self":
            return int(state.cards[context.source_id].damage)
        if kind == "filtered-count":
            return self._filtered_count(state, ctx, raw_amount, context)
        return 0

    def _controller_from_raw(self, state, raw: dict[str, Any], context: AmountContext) -> int:
        source_controller = int(state.cards[context.source_id].controller)
        controller = raw.get("controller") or raw.get("owner")
        if controller == "opponent":
            return int(state.opponent(source_controller))
        return source_controller

    def _filtered_count(self, state, ctx, raw: dict[str, Any], context: AmountContext) -> int:
        from .target_resolver import TargetQueryContext
        target = {
            "selector": "all",
            "zones": raw.get("zones") or ("play",),
            "cardTypes": raw.get("cardType") or raw.get("cardTypes") or (),
            "owner": raw.get("owner"),
            "controller": raw.get("controller"),
            "filters": raw.get("filters") or raw.get("filter") or (),
            "excludeSelf": raw.get("excludeSelf") or raw.get("exclude_self"),
            "count": "all",
        }
        q = TargetQueryContext(actor=int(state.cards[context.source_id].controller), source_id=context.source_id)
        count = len(ctx.targets.resolve(state, ctx, target, q))
        return count * int(raw.get("multiplier") or 1)
