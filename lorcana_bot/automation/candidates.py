from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class AutomatedActionFamily(StrEnum):
    CHOOSE_WHO_GOES_FIRST = "chooseWhoGoesFirst"
    ALTER_HAND = "alterHand"
    RESOLVE_BAG = "resolveBag"
    RESOLVE_EFFECT = "resolveEffect"
    PUT_CARD_INTO_INKWELL = "putCardIntoInkwell"
    PLAY_CARD = "playCard"
    ACTIVATE_ABILITY = "activateAbility"
    QUEST = "quest"
    CHALLENGE = "challenge"
    MOVE_CHARACTER_TO_LOCATION = "moveCharacterToLocation"
    PASS_TURN = "passTurn"
    CONCEDE = "concede"


FAMILY_ORDER: dict[str, float] = {
    AutomatedActionFamily.CHOOSE_WHO_GOES_FIRST: 0,
    AutomatedActionFamily.ALTER_HAND: 1,
    AutomatedActionFamily.RESOLVE_EFFECT: 2,
    AutomatedActionFamily.RESOLVE_BAG: 3,
    AutomatedActionFamily.PLAY_CARD: 4,
    AutomatedActionFamily.QUEST: 4.5,
    AutomatedActionFamily.PUT_CARD_INTO_INKWELL: 5,
    AutomatedActionFamily.ACTIVATE_ABILITY: 6,
    AutomatedActionFamily.MOVE_CHARACTER_TO_LOCATION: 8,
    AutomatedActionFamily.CHALLENGE: 9,
    AutomatedActionFamily.PASS_TURN: 50,
    AutomatedActionFamily.CONCEDE: 1000,
}


@dataclass(frozen=True)
class AutomatedActionCandidate:
    family: str
    actor: int
    stable_key: str
    source_instance_id: int | None = None
    source_card_id: str | None = None
    target_instance_id: int | None = None
    target_card_id: str | None = None
    targets: tuple[int, ...] = ()
    card_instance_id: int | None = None
    payment_mode: str | None = None
    shift_target_instance_id: int | None = None
    singer_instance_ids: tuple[int, ...] = ()
    ability_id: str | None = None
    ability_index: int | None = None
    cost_selections: dict[str, Any] = field(default_factory=dict)
    bag_index: int | None = None
    pending_effect_id: str | None = None
    choice_index: int | None = None
    resolve_optional: bool | None = None
    named_card: str | None = None
    destinations: dict[str, tuple[int, ...]] = field(default_factory=dict)
    label: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CandidateValidationResult:
    valid: bool
    reason: str | None = None
    code: str | None = None


@dataclass(frozen=True)
class CandidateScoreContributor:
    name: str
    value: float
    detail: str | None = None


@dataclass(frozen=True)
class AutomatedActionCandidateSummary:
    candidate: AutomatedActionCandidate
    family: str
    stable_key: str
    score: float
    family_order: float
    contributors: tuple[CandidateScoreContributor, ...]
    information_policy: str
    source_definition_id: str | None = None
    target_definition_id: str | None = None
    actor_deck_signature: str | None = None


def stable_tuple_ids(values: Any) -> tuple[int, ...]:
    if values is None:
        return ()
    return tuple(sorted(int(value) for value in values))


def _normalize_for_key(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _normalize_for_key(value[k]) for k in sorted(value)}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_normalize_for_key(v) for v in sorted(value) if v is not None]
    return value


def make_stable_key(family: str, actor: int, **fields: Any) -> str:
    payload = {"family": str(family), "actor": int(actor)}
    for key, value in sorted(fields.items()):
        if value is not None and value != () and value != {}:
            payload[key] = _normalize_for_key(value)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def candidate_to_dict(candidate: AutomatedActionCandidate) -> dict[str, Any]:
    return _jsonable(asdict(candidate))


def candidate_summary_to_dict(summary: AutomatedActionCandidateSummary) -> dict[str, Any]:
    raw = asdict(summary)
    raw["candidate"] = candidate_to_dict(summary.candidate)
    return _jsonable(raw)


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_jsonable(v) for v in value]
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, StrEnum):
        return str(value)
    return value
