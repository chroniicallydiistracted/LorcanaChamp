from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from lorcana_engine_v2.core.ids import InstanceId, PlayerId, ZoneId
from lorcana_engine_v2.core.results import LogMessage, LogVisibility, ProjectedLogEntry, RuntimeValidationResult
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.core.zones import ZoneRef

from .registry import MoveEnumerationContext, MoveExecutionContext, MoveValidationContext


CHOOSE_WHO_GOES_FIRST = "chooseWhoGoesFirst"
ALTER_HAND = "alterHand"


def resolve_runtime_player_ids(
    player_ids: Sequence[PlayerId] | None,
    zones_private,
) -> tuple[PlayerId, ...]:
    if player_ids:
        return tuple(PlayerId(str(player_id)) for player_id in player_ids)

    resolved: list[PlayerId] = []
    seen: set[str] = set()
    zone_cards: Mapping[object, object] = getattr(zones_private, "zoneCards", {})
    for raw_zone_id in zone_cards:
        zone_id = str(raw_zone_id)
        separator_index = zone_id.find(":")
        if separator_index <= 0 or separator_index >= len(zone_id) - 1:
            continue
        player_id = zone_id[separator_index + 1 :]
        if not player_id or player_id in seen:
            continue
        seen.add(player_id)
        resolved.append(PlayerId(player_id))

    if resolved:
        return tuple(resolved)

    card_index: Mapping[object, object] = getattr(zones_private, "cardIndex", {})
    for card_state in card_index.values():
        owner_id = getattr(card_state, "ownerID", None)
        if owner_id is None or str(owner_id) in seen:
            continue
        seen.add(str(owner_id))
        resolved.append(PlayerId(str(owner_id)))

    return tuple(resolved)


def _arg_player_id(args: Mapping[str, object]) -> object:
    return args.get("playerId", args.get("player_id"))


def _cards_to_mulligan(args: Mapping[str, object]) -> tuple[InstanceId, ...] | None:
    raw_cards = args.get("cardsToMulligan", args.get("cards_to_mulligan", ()))
    if raw_cards is None:
        return ()
    if not isinstance(raw_cards, Sequence) or isinstance(raw_cards, (str, bytes)):
        return None
    return tuple(InstanceId(str(card_id)) for card_id in raw_cards)


@dataclass(frozen=True, slots=True)
class ChooseWhoGoesFirstMove:
    serverOnly: bool = False
    ignorePriority: bool = False
    ignoreStaleStateID: bool = False

    def available(self, context: MoveEnumerationContext) -> bool:
        return bool(
            resolve_runtime_player_ids(
                context.framework.state.playerIds,
                context.framework.state._zonesPrivate,
            )
        )

    def validate(self, context: MoveValidationContext) -> RuntimeValidationResult:
        raw_player_id = _arg_player_id(context.args)
        if context.validationMode == "preflight" and raw_player_id is None:
            return RuntimeValidationResult.ok()

        resolved_player_ids = resolve_runtime_player_ids(
            context.framework.state.playerIds,
            context.framework.state._zonesPrivate,
        )
        player_id = PlayerId(str(raw_player_id))
        if player_id not in resolved_player_ids:
            return RuntimeValidationResult.fail(f"Invalid player ID: {raw_player_id}", "INVALID_PLAYER")

        return RuntimeValidationResult.ok()

    def execute(self, context: MoveExecutionContext) -> MatchState:
        raw_player_id = _arg_player_id(context.args)
        chosen_player = PlayerId(str(raw_player_id))
        resolved_player_ids = resolve_runtime_player_ids(
            context.framework.state.playerIds,
            context.framework.state._zonesPrivate,
        )
        pending_mulligan = (
            (chosen_player,) + tuple(player_id for player_id in resolved_player_ids if player_id != chosen_player)
            if resolved_player_ids
            else (chosen_player,)
        )

        context.framework.status.patch(
            {
                "otp": chosen_player,
                "turnOwnerId": chosen_player,
                "pendingMulligan": pending_mulligan,
            }
        )
        context.framework.priority.openWindow(chosen_player)

        for player_id in pending_mulligan:
            context.framework.zones.shuffle(ZoneRef(zone=ZoneId("deck"), playerId=player_id))

        context.framework.log(
            ProjectedLogEntry(
                category="action",
                visibility=LogVisibility(mode="PUBLIC"),
                defaultMessage=LogMessage(
                    key="lorcana.setup.firstPlayerChosen",
                    values={"chooser": str(context.playerId), "chosen": str(chosen_player)},
                ),
            )
        )
        return context.state


@dataclass(frozen=True, slots=True)
class AlterHandMove:
    serverOnly: bool = False
    ignorePriority: bool = False
    ignoreStaleStateID: bool = False
    optimistic: str = "auto"

    def available(self, context: MoveEnumerationContext) -> bool:
        return True

    def validate(self, context: MoveValidationContext) -> RuntimeValidationResult:
        raw_player_id = _arg_player_id(context.args)
        player_id = PlayerId(str(raw_player_id))

        if player_id not in context.framework.state.playerIds:
            return RuntimeValidationResult.fail("Invalid player", "INVALID_PLAYER")

        pending_mulligan = context.framework.state.status.pendingMulligan or ()
        if player_id not in pending_mulligan:
            return RuntimeValidationResult.fail(
                "Player has already made a mulligan decision",
                "MULLIGAN_ALREADY_DONE",
            )

        cards_to_mulligan = _cards_to_mulligan(context.args)
        if cards_to_mulligan is None:
            return RuntimeValidationResult.fail(
                "cardsToMulligan must be a list",
                "INVALID_CARDS_TO_MULLIGAN",
            )

        hand_cards = context.framework.zones.getCards({"zone": "hand", "playerId": player_id})
        for card_id in cards_to_mulligan:
            if card_id not in hand_cards:
                return RuntimeValidationResult.fail(f"Card {card_id} not in hand", "CARD_NOT_IN_HAND")

        return RuntimeValidationResult.ok()

    def execute(self, context: MoveExecutionContext) -> MatchState:
        player_id = PlayerId(str(_arg_player_id(context.args)))
        cards_to_mulligan = _cards_to_mulligan(context.args) or ()
        deck_zone = ZoneRef(zone=ZoneId("deck"), playerId=player_id)
        hand_zone = ZoneRef(zone=ZoneId("hand"), playerId=player_id)

        for card_id in cards_to_mulligan:
            context.framework.zones.moveCard(card_id, deck_zone, index=0)

        drawn = context.framework.zones.drawCards(
            from_zone=deck_zone,
            to_zone=hand_zone,
            count=len(cards_to_mulligan),
        )

        visibility = LogVisibility(
            mode="PUBLIC_WITH_OVERRIDES",
            overrides={
                str(player_id): LogMessage(
                    key="lorcana.setup.mulligan.detail",
                    values={
                        "playerId": str(player_id),
                        "count": len(cards_to_mulligan),
                        "mulliganed": tuple(str(card_id) for card_id in cards_to_mulligan),
                        "drawn": tuple(str(card_id) for card_id in drawn),
                    },
                )
            },
        )
        context.framework.log(
            ProjectedLogEntry(
                category="action",
                visibility=visibility,
                defaultMessage=LogMessage(
                    key="lorcana.setup.mulligan.count",
                    values={"playerId": str(player_id), "count": len(cards_to_mulligan)},
                ),
                typedEntry={
                    "key": "lorcana.setup.mulligan.count",
                    "values": {"playerId": str(player_id), "count": len(cards_to_mulligan)},
                    "visibility": visibility,
                    "category": "action",
                },
            )
        )

        pending_mulligan = context.framework.state.status.pendingMulligan or ()
        next_pending = tuple(pending_player for pending_player in pending_mulligan if pending_player != player_id)
        context.framework.status.patch({"pendingMulligan": next_pending})

        if next_pending:
            context.framework.priority.openWindow(next_pending[0])
        else:
            context.framework.log(
                ProjectedLogEntry(
                    category="action",
                    visibility=LogVisibility(mode="PUBLIC"),
                    defaultMessage=LogMessage(key="lorcana.setup.done", values={}),
                )
            )

        return context.state


__all__ = [
    "ALTER_HAND",
    "CHOOSE_WHO_GOES_FIRST",
    "AlterHandMove",
    "ChooseWhoGoesFirstMove",
    "resolve_runtime_player_ids",
]
