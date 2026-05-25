from __future__ import annotations

import re
from dataclasses import dataclass
from collections.abc import Mapping
from typing import Iterable

from lorcana_engine_v2.cards.models import CardDefinition
from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.core.results import RuntimeValidationResult


SHIFT_LABEL_PATTERN = re.compile(r"\b(?:([A-Za-z][A-Za-z' -]+)\s+)?Shift\s+(\d+)\b", re.I)
SING_TOGETHER_PATTERN = re.compile(r"\bSing Together\s+(\d+)\b", re.I)


@dataclass(frozen=True, slots=True)
class ExertCostCard:
    cardId: InstanceId
    cardType: str | None = None
    subject: str | None = None
    exhaustedErrorCode: str | None = None
    dryingErrorCode: str | None = None


@dataclass(frozen=True, slots=True)
class BasicCost:
    ink: int = 0
    exertCards: tuple[ExertCostCard, ...] = ()


@dataclass(frozen=True, slots=True)
class PayBasicCostResult:
    success: bool
    inkPaid: int = 0
    error: str | None = None
    errorCode: str | None = None


@dataclass(frozen=True, slots=True)
class ShiftTargetMode:
    type: str
    classification: str | None = None
    name: str | None = None


@dataclass(frozen=True, slots=True)
class ShiftRules:
    inkCost: int | None
    rawLabel: str | None
    targetMode: ShiftTargetMode
    discardCost: "ShiftDiscardCost | None" = None
    unsupportedReason: str | None = None


@dataclass(frozen=True, slots=True)
class ShiftDiscardCost:
    discardCards: int
    discardCardType: str | None = None


def _raw_card_type(card_def: CardDefinition | None) -> str | None:
    return card_def.card_type if card_def is not None else None


def _raw_action_subtype(card_def: CardDefinition | None) -> str | None:
    if card_def is None:
        return None
    subtype = card_def.raw.get("actionSubtype") or card_def.raw.get("action_subtype")
    return str(subtype) if subtype is not None else None


def _raw_keyword_ability(card_def: CardDefinition | None, keyword: str):
    if card_def is None:
        return None
    for ability in card_def.abilities:
        if ability.kind == "keyword" and ability.raw.get("keyword") == keyword:
            return ability
    return None


def _text_parts(card_def: CardDefinition | None) -> tuple[str, ...]:
    if card_def is None:
        return ()
    values: list[str] = []
    raw_text = card_def.raw.get("text")
    if isinstance(raw_text, str):
        values.append(raw_text)
    elif isinstance(raw_text, list):
        for entry in raw_text:
            if isinstance(entry, dict):
                title = entry.get("title")
                description = entry.get("description")
                if isinstance(title, str):
                    values.append(title)
                if isinstance(description, str):
                    values.append(description)
    for ability in card_def.abilities:
        if ability.text:
            values.append(ability.text)
    return tuple(values)


def _same_word(left: str, right: str) -> bool:
    return left.strip().lower() == right.strip().lower()


def _has_name(card_def: CardDefinition | None, name: str) -> bool:
    if card_def is None:
        return False
    return _same_word(card_def.name, name) or _same_word(card_def.full_name, name)


def _has_mimicry(card_def: CardDefinition | None) -> bool:
    if card_def is None:
        return False
    return any(
        ability.kind == "keyword" and ability.raw.get("keyword") == "Mimicry"
        for ability in card_def.abilities
    )


def _parse_shift_cost(label: str | None) -> int | None:
    if not label:
        return None
    match = SHIFT_LABEL_PATTERN.search(label)
    if not match:
        return None
    return int(match.group(2))


def _parse_shift_label(card_def: CardDefinition | None) -> str | None:
    keyword = _raw_keyword_ability(card_def, "Shift")
    if keyword is not None and keyword.text and "shift" in keyword.text.lower():
        return keyword.text
    for text in _text_parts(card_def):
        if SHIFT_LABEL_PATTERN.search(text):
            return text
    return None


def _shift_target_mode(card_def: CardDefinition, shift_label: str | None) -> ShiftTargetMode:
    keyword = _raw_keyword_ability(card_def, "Shift")
    shift_target = keyword.raw.get("shiftTarget") if keyword is not None else None
    if isinstance(shift_target, str) and shift_target.strip():
        return ShiftTargetMode(type="name", name=shift_target.strip())

    if shift_label:
        match = SHIFT_LABEL_PATTERN.search(shift_label)
        prefix = match.group(1).strip() if match and match.group(1) else ""
        if prefix:
            if _same_word(prefix, "Universal"):
                return ShiftTargetMode(type="universal")
            return ShiftTargetMode(type="classification", classification=prefix)

    text_blob = " ".join(_text_parts(card_def))
    if re.search(r"Universal Shift|on top of any one of your characters|on top of any of your characters", text_blob, re.I):
        return ShiftTargetMode(type="universal")
    named = re.search(r"on top of (?:one of )?your characters named ([^)\\.]+)", text_blob, re.I)
    if named:
        return ShiftTargetMode(type="name", name=named.group(1).strip())
    classified = re.search(r"on top of (?:one of )?your ([A-Za-z][A-Za-z' -]+?) characters", text_blob, re.I)
    if classified and not _same_word(classified.group(1), "any"):
        return ShiftTargetMode(type="classification", classification=classified.group(1).strip())
    return ShiftTargetMode(type="name", name=card_def.name)


def get_shift_rules(card_def: CardDefinition | None) -> ShiftRules | None:
    if card_def is None:
        return None
    keyword = _raw_keyword_ability(card_def, "Shift")
    label = _parse_shift_label(card_def)
    if keyword is None and label is None:
        return None
    raw_cost = keyword.raw.get("cost") if keyword is not None else None
    if isinstance(raw_cost, dict):
        discard_cards = raw_cost.get("discardCards") or raw_cost.get("discard_cards")
        if isinstance(discard_cards, int) and discard_cards > 0:
            return ShiftRules(
                inkCost=None,
                rawLabel=label,
                targetMode=_shift_target_mode(card_def, label),
                discardCost=ShiftDiscardCost(
                    discardCards=discard_cards,
                    discardCardType=(
                        str(raw_cost.get("discardCardType") or raw_cost.get("discard_card_type"))
                        if raw_cost.get("discardCardType") or raw_cost.get("discard_card_type")
                        else None
                    ),
                ),
            )
        non_ink_keys = [key for key, value in raw_cost.items() if key != "ink" and value is not None]
        if non_ink_keys:
            return ShiftRules(
                inkCost=None,
                rawLabel=label,
                targetMode=_shift_target_mode(card_def, label),
                unsupportedReason="TODO: Non-ink Shift costs are not supported in playCard yet",
            )
        if isinstance(raw_cost.get("ink"), int):
            ink_cost = int(raw_cost["ink"])
        else:
            ink_cost = _parse_shift_cost(label)
    else:
        ink_cost = _parse_shift_cost(label)
    return ShiftRules(
        inkCost=ink_cost,
        rawLabel=label,
        targetMode=_shift_target_mode(card_def, label),
    )


def resolve_shift_target_candidates(
    shift_rules: ShiftRules | None,
    candidates: Iterable[InstanceId],
    get_card_definition,
) -> tuple[InstanceId, ...]:
    if shift_rules is None:
        return ()
    mode = shift_rules.targetMode
    resolved: list[InstanceId] = []
    for card_id in candidates:
        definition = get_card_definition(card_id)
        if _raw_card_type(definition) != "character":
            continue
        if mode.type == "universal":
            resolved.append(InstanceId(str(card_id)))
        elif mode.type == "classification":
            if any(_same_word(value, mode.classification or "") for value in definition.classifications):
                resolved.append(InstanceId(str(card_id)))
        elif mode.type == "name":
            target_names = re.split(r"\s+(?:or|and)\s+", mode.name or "")
            if _has_mimicry(definition) or any(_has_name(definition, target_name) for target_name in target_names):
                resolved.append(InstanceId(str(card_id)))
    return tuple(resolved)


def is_song_card(card_def: CardDefinition | None) -> bool:
    return _raw_card_type(card_def) == "action" and _raw_action_subtype(card_def) == "song"


def get_singer_threshold(card_def: CardDefinition | None) -> int | None:
    if _raw_card_type(card_def) != "character":
        return None
    keyword = _raw_keyword_ability(card_def, "Singer")
    value = keyword.raw.get("value") if keyword is not None else None
    return int(value) if isinstance(value, int) else int(card_def.cost)


def _payload(effect: object) -> Mapping[str, object]:
    value = getattr(effect, "payload", {})
    return value if isinstance(value, Mapping) else {}


def _effects_for_card(registry: object | None, card_id: InstanceId | str, kind: str | None = None) -> tuple[object, ...]:
    if registry is None:
        return ()
    getter = getattr(registry, "get_effects_for_card", None)
    if callable(getter):
        return tuple(getter(InstanceId(str(card_id)), kind=kind))
    by_target = getattr(registry, "byTarget", {})
    effects = tuple(by_target.get(InstanceId(str(card_id)), ()))
    if kind is None:
        return effects
    return tuple(effect for effect in effects if getattr(effect, "kind", None) == kind)


def _active_temporary_keyword_value(meta: object, keyword: str, current_turn: int) -> int:
    keywords = getattr(meta, "temporaryKeywords", None) or {}
    starts = getattr(meta, "temporaryKeywordStarts", None) or {}
    values = getattr(meta, "temporaryKeywordValues", None) or {}
    expires = keywords.get(keyword) if isinstance(keywords, Mapping) else None
    start = starts.get(keyword, 1) if isinstance(starts, Mapping) else 1
    if isinstance(expires, int) and int(start) <= current_turn <= expires:
        raw_value = values.get(keyword, 0) if isinstance(values, Mapping) else 0
        return int(raw_value) if isinstance(raw_value, int) else 0
    return 0


def _static_granted_singer_value(registry: object | None, singer_id: InstanceId | str) -> int:
    value = 0
    for effect in _effects_for_card(registry, singer_id, "gain-keyword"):
        payload = _payload(effect)
        if payload.get("keyword") != "Singer":
            continue
        raw_value = payload.get("value")
        if isinstance(raw_value, int):
            value = max(value, raw_value)
    return value


def _static_singer_threshold_modifier(registry: object | None, singer_id: InstanceId | str) -> int:
    total = 0
    for effect in _effects_for_card(registry, singer_id, "property-modification"):
        payload = _payload(effect)
        if payload.get("property") != "singer-threshold":
            continue
        raw_value = payload.get("value", payload.get("modifier", 0))
        if isinstance(raw_value, int):
            total += raw_value
    return total


def _continuous_singer_threshold_modifier(G: object | None, singer_id: InstanceId | str) -> int:
    continuous = getattr(G, "continuousEffects", None)
    by_target = getattr(continuous, "byTarget", {}) if continuous is not None else {}
    total = 0
    for effect in by_target.get(InstanceId(str(singer_id)), ()):
        if getattr(effect, "kind", None) != "stat-modifier":
            continue
        if getattr(effect, "stat", None) != "singer-threshold":
            continue
        total += int(getattr(effect, "modifier", 0) or 0)
    return total


def get_singer_threshold_for_instance(
    *,
    framework,
    singerId: InstanceId,
    singerDef: CardDefinition | None,
    getDefinitionByInstanceId,
    G=None,
    registry=None,
) -> int | None:
    _ = getDefinitionByInstanceId
    base_threshold = get_singer_threshold(singerDef)
    if base_threshold is None:
        return None
    printed_singer = 0
    keyword = _raw_keyword_ability(singerDef, "Singer")
    raw_keyword_value = keyword.raw.get("value") if keyword is not None else None
    if isinstance(raw_keyword_value, int):
        printed_singer = raw_keyword_value

    current_turn = 1
    state_snapshot = getattr(framework, "state", None)
    status = getattr(state_snapshot, "status", None)
    raw_turn = getattr(status, "turn", None)
    if isinstance(raw_turn, int) and raw_turn > 0:
        current_turn = raw_turn

    try:
        meta = framework.cards.require(singerId).meta if framework is not None else None
    except Exception:
        meta = None

    temporary_singer = _active_temporary_keyword_value(meta, "Singer", current_turn)
    static_singer = _static_granted_singer_value(registry, singerId)
    threshold_modifier = _static_singer_threshold_modifier(registry, singerId) + _continuous_singer_threshold_modifier(G, singerId)
    printed_cost_to_sing = int(singerDef.cost) + threshold_modifier if singerDef is not None else threshold_modifier
    singer_value = max(printed_singer, static_singer, temporary_singer)
    return max(base_threshold, singer_value, printed_cost_to_sing)


def get_sing_together_threshold(card_def: CardDefinition | None) -> int | None:
    if not is_song_card(card_def):
        return None
    keyword = _raw_keyword_ability(card_def, "SingTogether")
    value = keyword.raw.get("value") if keyword is not None else None
    if isinstance(value, int):
        return value
    for text in _text_parts(card_def):
        match = SING_TOGETHER_PATTERN.search(text)
        if match:
            return int(match.group(1))
    return None


def is_ready_and_not_drying(meta) -> bool:
    return getattr(meta, "state", None) != "exerted" and getattr(meta, "isDrying", None) is not True


def validate_exert_cost(meta, card_type: str | None) -> RuntimeValidationResult:
    if getattr(meta, "state", None) == "exerted":
        return RuntimeValidationResult.fail("Card is exerted", "CARD_EXERTED")
    if card_type == "character" and getattr(meta, "isDrying", None) is True:
        return RuntimeValidationResult.fail("Card is drying", "CARD_DRYING")
    return RuntimeValidationResult.ok()


def get_available_ink(context, player_id: PlayerId | str) -> int:
    cards = context.framework.zones.getCards({"zone": "inkwell", "playerId": PlayerId(str(player_id))})
    return sum(1 for card_id in cards if context.cards.require(card_id).meta.state != "exerted")


def spend_ink(context, player_id: PlayerId | str, amount: int) -> tuple[InstanceId, ...]:
    paid: list[InstanceId] = []
    for card_id in context.framework.zones.getCards({"zone": "inkwell", "playerId": PlayerId(str(player_id))}):
        if len(paid) >= max(0, amount):
            break
        runtime_card = context.cards.require(card_id)
        if runtime_card.meta.state == "exerted":
            continue
        context.cards.patchMeta(card_id, {"state": "exerted"})
        paid.append(InstanceId(str(card_id)))
    return tuple(paid)


def _normalize_subject(subject: str | None) -> str:
    return subject if subject else "Card"


def validate_basic_cost(context, cost: BasicCost) -> RuntimeValidationResult:
    for exert_card in cost.exertCards:
        meta = context.cards.require(exert_card.cardId).meta
        validation = validate_exert_cost(meta, exert_card.cardType)
        if validation.valid:
            continue
        subject = _normalize_subject(exert_card.subject)
        if validation.errorCode == "CARD_EXERTED":
            return RuntimeValidationResult.fail(
                f"{subject} is exerted",
                exert_card.exhaustedErrorCode or "CARD_EXERTED",
            )
        if validation.errorCode == "CARD_DRYING":
            return RuntimeValidationResult.fail(
                f"{subject} is drying",
                exert_card.dryingErrorCode or "CARD_DRYING",
            )
        return validation
    ink = max(0, int(cost.ink or 0))
    if ink and get_available_ink(context, context.playerId) < ink:
        return RuntimeValidationResult.fail(
            f"Not enough ink (have {get_available_ink(context, context.playerId)}, need {ink})",
            "INSUFFICIENT_INK",
        )
    return RuntimeValidationResult.ok()


def pay_basic_cost(context, cost: BasicCost) -> PayBasicCostResult:
    validation = validate_basic_cost(context, cost)
    if not validation.valid:
        return PayBasicCostResult(False, error=validation.error, errorCode=validation.errorCode)
    ink = max(0, int(cost.ink or 0))
    if ink:
        spend_ink(context, context.playerId, ink)
    for exert_card in cost.exertCards:
        context.cards.patchMeta(exert_card.cardId, {"state": "exerted"})
    return PayBasicCostResult(True, inkPaid=ink)


__all__ = [
    "BasicCost",
    "ExertCostCard",
    "PayBasicCostResult",
    "ShiftDiscardCost",
    "ShiftRules",
    "get_available_ink",
    "get_shift_rules",
    "get_sing_together_threshold",
    "get_singer_threshold",
    "get_singer_threshold_for_instance",
    "is_ready_and_not_drying",
    "is_song_card",
    "pay_basic_cost",
    "resolve_shift_target_candidates",
    "spend_ink",
    "validate_basic_cost",
    "validate_exert_cost",
]
