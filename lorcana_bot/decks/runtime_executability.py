from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from lorcana_bot.card_logic import AbilityKind, ExecutionStatus, SourceEffectDef
from lorcana_bot.card_logic.effect_utils import (
    to_engine_cost_kind,
    to_engine_effect_kind,
    to_engine_replacement_kind,
    to_engine_static_kind,
)
from lorcana_bot.card_logic.resolution_requirements import analyze_resolution_requirements
from lorcana_bot.cards import CardDef
from lorcana_bot.costs import SUPPORTED_COST_KINDS
from lorcana_bot.effect_types import SUPPORTED_EFFECT_KINDS
from lorcana_bot.importers.lorcanito_source_importer import import_lorcanito_source_cards
from lorcana_bot.importers.lorcanito_source_mapper import ENGINE_EFFECT_MAP
from lorcana_bot.play_modes import get_shift_rules

from .deck_schema import ResolvedDeck, ResolvedDeckCard
from .trigger_blocker_report import analyze_source_trigger_projection

RuntimeSupportStatus = Literal[
    "executable",
    "projected_but_requires_pending_input",
    "scaffold_only",
    "source_preserved",
    "unsupported",
]


@dataclass(frozen=True)
class CardRuntimeSupport:
    card_id: str
    name: str
    status: RuntimeSupportStatus
    blockers: tuple[str, ...] = ()
    stale_blockers_ignored: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    runtime_paths_required: tuple[str, ...] = ()
    runtime_paths_verified: tuple[str, ...] = ()
    stored_resolved_deck_blockers: tuple[str, ...] = ()
    fresh_runtime_blockers: tuple[str, ...] = ()


@dataclass(frozen=True)
class DeckRuntimeSupport:
    deck_id: str
    status: RuntimeSupportStatus
    playability: str
    card_results: tuple[CardRuntimeSupport, ...]
    blockers_by_copies: dict[str, int]
    blockers_by_unique_cards: dict[str, int]
    stale_blockers_ignored_by_copies: dict[str, int]
    stored_blockers_by_copies: dict[str, int] = field(default_factory=dict)
    fresh_blockers_by_copies: dict[str, int] = field(default_factory=dict)


SUPPORTED_STATIC_EFFECT_KINDS = frozenset({"modify_stat", "gain_keyword", "cost_reduction", "restriction"})
SUPPORTED_REPLACEMENT_EFFECT_KINDS = frozenset({"prevent_damage", "replace_banish", "cannot_be_challenged", "cannot_be_targeted"})
SUPPORTED_EFFECT_CONDITIONS = frozenset(
    {
        "always",
        "your-turn",
        "turn",
        "opponent-turn",
        "during-turn",
        "has-character-count",
        "has-item-count",
        "has-location-count",
        "has-location-in-play",
        "has-another-character",
        "has-character-with-keyword",
        "has-character-with-classification",
        "has-character-with-strength",
        "has-named-character",
        "has-named-item",
        "is-exerted",
        "exerted",
        "has-any-damage",
        "no-damage",
        "self-has-damage",
        "inkwell-count",
        "resource-count",
        "target_damaged",
        "target-damaged",
        "target-query",
        "comparison",
        "lore-comparison",
        "card-type-comparison",
        "banished-in-challenge-this-turn",
        "in-challenge",
        "being-challenged",
        "has-card-under",
        "at-location",
        "play-context",
        "used-shift",
        "opponent-has-damaged-character",
        "first-turn-non-otp",
        "has-granted-ability",
        "is-named",
        "stat-threshold",
        "target-aggregate-comparison",
        "trigger-subject-had-card-under",
        "put-card-under-any-this-turn",
        "put-card-under-self-this-turn",
        "turn-metric",
        "and",
        "or",
        "not",
        "if",
    }
)


def load_current_card_defs(source_json: str | Path = "data/lorcanito_extracted/cards.normalized.json") -> dict[str, CardDef]:
    source_path = Path(source_json)
    if not source_path.exists():
        return {}
    db, _ = import_lorcanito_source_cards(source_path)
    return {card.id: card for card in db.all_cards()}


def classify_card_runtime_support(card_def: CardDef, resolved_card: ResolvedDeckCard | None = None) -> CardRuntimeSupport:
    blockers: list[str] = []
    evidence: list[str] = ["current_carddef_loaded"]
    required: list[str] = []
    verified: list[str] = []
    statuses: list[RuntimeSupportStatus] = []

    def add(
        status: RuntimeSupportStatus,
        blocker_items: tuple[str, ...] = (),
        evidence_items: tuple[str, ...] = (),
        required_items: tuple[str, ...] = (),
        verified_items: tuple[str, ...] = (),
    ) -> None:
        statuses.append(status)
        blockers.extend(blocker_items)
        evidence.extend(evidence_items)
        required.extend(required_items)
        verified.extend(verified_items)

    if not card_def.source_abilities and not card_def.source_effects and not card_def.source_static_abilities and not card_def.source_replacement_abilities:
        add("executable", (), ("no_gameplay_source_abilities",), ("normal_play",), ("legal_actions:PLAY", "apply_action:PLAY"))

    for ability in card_def.source_abilities:
        if ability.kind == AbilityKind.KEYWORD:
            continue
        if ability.kind == AbilityKind.TRIGGERED:
            add(*_classify_trigger_ability(card_def, ability))
        elif ability.kind == AbilityKind.ACTIVATED:
            add(*_classify_activated_ability(ability))
        elif ability.kind == AbilityKind.STATIC:
            add(*_classify_static_ability(ability))
        elif ability.kind == AbilityKind.REPLACEMENT:
            add(*_classify_replacement_ability(ability))
        elif ability.kind == AbilityKind.ACTION:
            add(*_classify_effect_collection(ability.effects, base_required=("EffectResolver",)))
        else:
            add("unsupported", (f"unsupported_ability:{ability.kind}",), evidence_items=("unknown_source_ability_kind",))

    if not card_def.source_abilities:
        add(*_classify_effect_collection(card_def.source_effects, base_required=("EffectResolver",)))

    for static_ability in card_def.source_static_abilities:
        add(*_classify_source_static_effect(static_ability))
    for replacement_ability in card_def.source_replacement_abilities:
        add(*_classify_source_replacement_effect(replacement_ability))

    keyword_status = _classify_keywords(card_def)
    if keyword_status is not None:
        add(*keyword_status)

    status = _combine_statuses(statuses)
    fresh = tuple(sorted(set(blockers)))
    stored = tuple(resolved_card.unsupported_blockers) if resolved_card is not None else ()
    stale_ignored = tuple(sorted(set(stored) - set(fresh)))
    return CardRuntimeSupport(
        card_id=card_def.id,
        name=card_def.full_name,
        status=status,
        blockers=fresh,
        stale_blockers_ignored=stale_ignored,
        evidence=tuple(sorted(set(evidence))),
        runtime_paths_required=tuple(sorted(set(required))),
        runtime_paths_verified=tuple(sorted(set(verified))),
        stored_resolved_deck_blockers=stored,
        fresh_runtime_blockers=fresh,
    )


def classify_resolved_deck_card_runtime_support(
    resolved_card: ResolvedDeckCard,
    card_defs: dict[str, CardDef],
) -> CardRuntimeSupport:
    if not resolved_card.resolved:
        stored = tuple(resolved_card.unsupported_blockers)
        return CardRuntimeSupport(
            card_id=resolved_card.card_id or resolved_card.raw_name,
            name=resolved_card.full_name or resolved_card.raw_name,
            status="source_preserved",
            blockers=("unresolved_card",),
            stale_blockers_ignored=tuple(sorted(set(stored) - {"unresolved_card"})),
            evidence=("resolved_deck_card_unresolved",),
            stored_resolved_deck_blockers=stored,
            fresh_runtime_blockers=("unresolved_card",),
        )
    if not resolved_card.card_id:
        return CardRuntimeSupport(
            card_id=resolved_card.raw_name,
            name=resolved_card.full_name or resolved_card.raw_name,
            status="source_preserved",
            blockers=("missing_card_id",),
            stale_blockers_ignored=tuple(resolved_card.unsupported_blockers),
            evidence=("resolved_deck_card_missing_card_id",),
            stored_resolved_deck_blockers=tuple(resolved_card.unsupported_blockers),
            fresh_runtime_blockers=("missing_card_id",),
        )
    card_def = card_defs.get(resolved_card.card_id)
    if card_def is None:
        return CardRuntimeSupport(
            card_id=resolved_card.card_id,
            name=resolved_card.full_name or resolved_card.raw_name,
            status="source_preserved",
            blockers=("missing_current_card_definition",),
            stale_blockers_ignored=tuple(sorted(set(resolved_card.unsupported_blockers) - {"missing_current_card_definition"})),
            evidence=("current_carddef_missing",),
            stored_resolved_deck_blockers=tuple(resolved_card.unsupported_blockers),
            fresh_runtime_blockers=("missing_current_card_definition",),
        )
    return classify_card_runtime_support(card_def, resolved_card)


def classify_deck_runtime_support(deck: ResolvedDeck, card_defs: dict[str, CardDef] | None = None) -> DeckRuntimeSupport:
    card_defs = card_defs if card_defs is not None else load_current_card_defs()
    card_results = tuple(classify_resolved_deck_card_runtime_support(card, card_defs) for card in deck.cards)
    blockers_by_unique: Counter[str] = Counter()
    blockers_by_copies: Counter[str] = Counter()
    stale_by_copies: Counter[str] = Counter()
    stored_by_copies: Counter[str] = Counter()
    count_by_card_id = {card.card_id or card.raw_name: card.count for card in deck.cards}
    for result in card_results:
        copies = count_by_card_id.get(result.card_id, 1)
        for blocker in result.blockers:
            blockers_by_unique[blocker] += 1
            blockers_by_copies[blocker] += copies
        for blocker in result.stale_blockers_ignored:
            stale_by_copies[blocker] += copies
        for blocker in result.stored_resolved_deck_blockers:
            stored_by_copies[blocker] += copies

    playability = _deck_playability(deck, card_results, blockers_by_copies)
    return DeckRuntimeSupport(
        deck_id=deck.id,
        status=_combine_statuses([result.status for result in card_results]),
        playability=playability,
        card_results=card_results,
        blockers_by_copies=dict(sorted(blockers_by_copies.items())),
        blockers_by_unique_cards=dict(sorted(blockers_by_unique.items())),
        stale_blockers_ignored_by_copies=dict(sorted(stale_by_copies.items())),
        stored_blockers_by_copies=dict(sorted(stored_by_copies.items())),
        fresh_blockers_by_copies=dict(sorted(blockers_by_copies.items())),
    )


def _classify_trigger_ability(card: CardDef, ability: Any) -> tuple[RuntimeSupportStatus, tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    analysis = analyze_source_trigger_projection(card, ability)
    required = ("trigger_projection", "event_emission", "trigger_matching", "bag_resolution")
    if analysis.can_project:
        return ("executable", (), ("trigger_projection:projected",), required, required)
    blockers = tuple(blocker for blocker in analysis.blockers if blocker != "activated_ability_reported_separately") or ("unsupported_trigger",)
    if any(blocker.startswith("unsupported_trigger_resolution_requirement:") for blocker in blockers):
        return ("projected_but_requires_pending_input", blockers, ("trigger_projection:pending_input_required",), required, ("trigger_projection", "trigger_matching"))
    return ("unsupported", blockers, ("trigger_projection:not_projected",), required, ())


def _classify_activated_ability(ability: Any) -> tuple[RuntimeSupportStatus, tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    statuses: list[RuntimeSupportStatus] = []
    blockers: list[str] = []
    for cost in ability.costs:
        engine_kind = to_engine_cost_kind(str(cost.kind))
        if engine_kind not in SUPPORTED_COST_KINDS:
            statuses.append("unsupported")
            blockers.append(f"unsupported_cost:{cost.kind}")
        elif engine_kind == "discard":
            statuses.append("projected_but_requires_pending_input")
            blockers.append("unsupported_cost:discard_choice")
        else:
            statuses.append("executable")
    effect_status, effect_blockers, _, _, _ = _classify_effect_collection(ability.effects, base_required=("EffectResolver",))
    statuses.append(effect_status)
    blockers.extend(effect_blockers)
    status = _combine_statuses(statuses)
    return (
        status,
        tuple(sorted(set(blockers))),
        ("activated_ability:USE_ABILITY",),
        ("legal_actions:USE_ABILITY", "apply_action:USE_ABILITY", "cost_payment", "EffectResolver", "automation:USE_ABILITY"),
        ("legal_actions:USE_ABILITY", "apply_action:USE_ABILITY", "cost_payment", "EffectResolver", "automation:USE_ABILITY") if status == "executable" else ("legal_actions:USE_ABILITY", "apply_action:USE_ABILITY"),
    )


def _classify_static_ability(ability: Any) -> tuple[RuntimeSupportStatus, tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    effects = tuple(ability.effects)
    if not effects:
        return ("source_preserved", ("source_preserved:static:no_effects",), ("static_source_preserved",), ("static_parser",), ())
    statuses = [_classify_static_effect_kind(effect)[0] for effect in effects]
    blockers = tuple(blocker for effect in effects for blocker in _classify_static_effect_kind(effect)[1])
    status = _combine_statuses(statuses)
    required = ("static_parser", "static_registry", "derived_state", "leave_play_cleanup")
    return (status, tuple(sorted(set(blockers))), ("static_effect_exact_classification",), required, required if status == "executable" else ("static_parser",))


def _classify_source_static_effect(static_effect: Any) -> tuple[RuntimeSupportStatus, tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    effect = getattr(static_effect, "effect", None)
    if effect is not None:
        status, blockers = _classify_static_effect_kind(effect)
        required = ("static_parser", "static_registry", "derived_state", "leave_play_cleanup")
        return (status, blockers, ("static_effect_exact_classification",), required, required if status == "executable" else ("static_parser",))
    kind = to_engine_static_kind(str(getattr(static_effect, "kind", "unknown")))
    if kind in SUPPORTED_STATIC_EFFECT_KINDS:
        return ("executable", (), (f"static_effect:{kind}",), ("static_parser", "static_registry", "derived_state", "leave_play_cleanup"), ("static_parser", "static_registry", "derived_state", "leave_play_cleanup"))
    return ("scaffold_only", (f"unsupported_static_effect:{getattr(static_effect, 'kind', 'unknown')}",), ("static_effect_not_in_registry",), ("static_parser", "static_registry", "derived_state", "leave_play_cleanup"), ())


def _classify_static_effect_kind(effect: Any) -> tuple[RuntimeSupportStatus, tuple[str, ...]]:
    raw_kind = str(getattr(effect, "kind", "unknown"))
    kind = to_engine_static_kind(raw_kind)
    if getattr(effect, "condition", None) is not None:
        return ("scaffold_only", (f"unsupported_static_condition:{_condition_kind(effect.condition)}",))
    if kind in SUPPORTED_STATIC_EFFECT_KINDS:
        return ("executable", ())
    return ("scaffold_only", (f"unsupported_static_effect:{raw_kind}",))


def _classify_replacement_ability(ability: Any) -> tuple[RuntimeSupportStatus, tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    effects = tuple(ability.effects)
    if not effects:
        return ("source_preserved", ("source_preserved:replacement:no_effects",), ("replacement_source_preserved",), ("replacement_parser",), ())
    statuses = [_classify_replacement_effect_kind(effect)[0] for effect in effects]
    blockers = tuple(blocker for effect in effects for blocker in _classify_replacement_effect_kind(effect)[1])
    status = _combine_statuses(statuses)
    required = ("replacement_parser", "replacement_registry", "eventful_helper_consult", "leave_play_cleanup")
    return (status, tuple(sorted(set(blockers))), ("replacement_effect_exact_classification",), required, required if status == "executable" else ("replacement_parser",))


def _classify_source_replacement_effect(replacement_effect: Any) -> tuple[RuntimeSupportStatus, tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    effect = getattr(replacement_effect, "replacement", None)
    if effect is not None:
        status, blockers = _classify_replacement_effect_kind(effect)
        return (status, blockers, ("replacement_effect_exact_classification",), ("replacement_parser", "replacement_registry", "eventful_helper_consult", "leave_play_cleanup"), ())
    raw_kind = str(getattr(replacement_effect, "replaces", "unknown"))
    kind = to_engine_replacement_kind(raw_kind)
    if kind in SUPPORTED_REPLACEMENT_EFFECT_KINDS:
        return ("executable", (), (f"replacement_effect:{kind}",), ("replacement_parser", "replacement_registry", "eventful_helper_consult", "leave_play_cleanup"), ("replacement_parser", "replacement_registry", "eventful_helper_consult", "leave_play_cleanup"))
    return ("scaffold_only", (f"unsupported_replacement_effect:{raw_kind}",), ("replacement_effect_not_in_registry",), ("replacement_parser", "replacement_registry", "eventful_helper_consult", "leave_play_cleanup"), ())


def _classify_replacement_effect_kind(effect: Any) -> tuple[RuntimeSupportStatus, tuple[str, ...]]:
    raw_kind = str(getattr(effect, "kind", "unknown"))
    kind = to_engine_replacement_kind(raw_kind)
    if kind in SUPPORTED_REPLACEMENT_EFFECT_KINDS:
        return ("executable", ())
    return ("scaffold_only", (f"unsupported_replacement_effect:{raw_kind}",))


def _classify_effect_collection(
    effects: tuple[Any, ...],
    *,
    base_required: tuple[str, ...],
) -> tuple[RuntimeSupportStatus, tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    statuses: list[RuntimeSupportStatus] = []
    blockers: list[str] = []
    evidence: list[str] = []
    required: list[str] = list(base_required)
    verified: list[str] = []
    if not effects:
        statuses.append("executable")
    for effect in effects:
        status, effect_blockers, effect_evidence, effect_required, effect_verified = _classify_effect(effect)
        statuses.append(status)
        blockers.extend(effect_blockers)
        evidence.extend(effect_evidence)
        required.extend(effect_required)
        verified.extend(effect_verified)
    return (_combine_statuses(statuses), tuple(sorted(set(blockers))), tuple(sorted(set(evidence))), tuple(sorted(set(required))), tuple(sorted(set(verified))))


def _classify_effect(effect: Any) -> tuple[RuntimeSupportStatus, tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    source_kind = str(getattr(effect, "kind", "unknown"))
    engine_kind = _runtime_effect_kind(source_kind)
    blockers: list[str] = []
    statuses: list[RuntimeSupportStatus] = []
    required = ["EffectResolver"]
    verified: list[str] = []
    evidence = [f"effect_kind:{source_kind}->{engine_kind}"]
    if source_kind == "put-into-inkwell" and not _source_put_into_inkwell_shape_supported(effect):
        statuses.append("unsupported")
        blockers.append("unsupported_effect:put-into-inkwell")
        required.append("eventful:put_into_inkwell")
    elif engine_kind not in SUPPORTED_EFFECT_KINDS:
        statuses.append("unsupported")
        blockers.append(f"unsupported_effect:{source_kind}")
    else:
        statuses.append("executable")
        verified.append("EffectResolver")

    target = getattr(effect, "target", None)
    if target is not None and getattr(target, "execution_status", ExecutionStatus.EXECUTABLE) != ExecutionStatus.EXECUTABLE:
        if _source_target_shape_supported(target):
            statuses.append("executable")
            required.append("pending_target_resolution")
            verified.extend((
                "legal_actions:target_selection",
                "apply_action:PLAY_CARD",
                "targeting:chosen_selector",
                "targeting:protection_filters",
            ))
            evidence.append("source_target_shape_supported:chosen")
        else:
            statuses.append("projected_but_requires_pending_input")
            blockers.append(f"unsupported_target:{getattr(target, 'kind', 'unknown')}:{getattr(target, 'selector', None) or getattr(target, 'alias', None) or 'unknown'}")
            required.append("pending_target_resolution")

    condition = getattr(effect, "condition", None)
    condition_status, condition_blockers = _classify_condition(condition)
    statuses.append(condition_status)
    blockers.extend(condition_blockers)

    if isinstance(effect, SourceEffectDef):
        requirements = analyze_resolution_requirements(effect)
        for requirement in requirements.unsupported_requirements:
            if _source_scry_requirement_supported(effect, requirement):
                statuses.append("executable")
                required.append(f"pending:{requirement}")
                verified.extend((
                    "legal_actions:RESOLVE_PENDING_EFFECT",
                    "apply_action:RESOLVE_PENDING_EFFECT",
                    "pending:scry_destinations",
                    "automation:RESOLVE_EFFECT",
                ))
                evidence.append(f"scry_requirement_supported:{requirement}")
                continue
            if requirement == "opponent_choice" and _source_opponent_choice_requirement_supported(effect):
                statuses.append("executable")
                required.append("pending:opponent_choice")
                verified.extend((
                    "legal_actions:RESOLVE_PENDING_EFFECT",
                    "apply_action:RESOLVE_PENDING_EFFECT",
                    "pending:opponent_choice",
                    "bag_completion:pure_input",
                ))
                evidence.append("opponent_choice_requirement_supported")
                continue
            statuses.append("projected_but_requires_pending_input")
            blockers.append(f"unsupported_resolution_requirement:{requirement}")
            required.append(f"pending:{requirement}")

    for child in (*tuple(getattr(effect, "effects", ()) or ()), *tuple(getattr(effect, "branches", ()) or ())):
        child_status, child_blockers, child_evidence, child_required, child_verified = _classify_effect(child)
        statuses.append(child_status)
        blockers.extend(child_blockers)
        evidence.extend(child_evidence)
        required.extend(child_required)
        verified.extend(child_verified)

    return (_combine_statuses(statuses), tuple(sorted(set(blockers))), tuple(sorted(set(evidence))), tuple(sorted(set(required))), tuple(sorted(set(verified))))


def _source_put_into_inkwell_shape_supported(effect: Any) -> bool:
    target = getattr(effect, "target", None)
    if target is None:
        return False
    raw = getattr(effect, "raw", {}) or {}
    if raw.get("source") not in {None, "chosen-character"}:
        return False
    if raw.get("facedown") not in {None, True}:
        return False
    if raw.get("exerted") not in {None, True, False}:
        return False
    return _source_target_shape_supported(target)


def _source_target_shape_supported(target: Any) -> bool:
    if getattr(target, "alias", None) in {"CHOSEN_CHARACTER", "CHOSEN_EXERTED_CHARACTER"}:
        return True
    if getattr(target, "kind", None) != "selector" or getattr(target, "selector", None) != "chosen":
        return False
    raw = getattr(target, "raw", {}) or {}
    zones = tuple(raw.get("zones", (raw.get("zone"),) if raw.get("zone") else ("play",)))
    if any(zone != "play" for zone in zones):
        return False
    if "cardTypes" not in raw and "cardType" not in raw:
        return False
    card_types = tuple(raw.get("cardTypes", (raw.get("cardType"),) if raw.get("cardType") else ()))
    if any(card_type not in {"character", "item", "location"} for card_type in card_types):
        return False
    count = raw.get("count", 1)
    if isinstance(count, dict):
        if not (set(count) <= {"upTo", "up_to", "min", "max"}):
            return False
    elif count not in {1, "1"}:
        return False
    filters = raw.get("filters", raw.get("filter", ()))
    if isinstance(filters, dict):
        filters = (filters,)
    for filter_def in filters or ():
        if not isinstance(filter_def, dict):
            return False
        if filter_def.get("type") not in {None, "damaged", "exerted", "ready", "strength-comparison", "cost-comparison", "classification", "has-classification", "card-type"}:
            return False
    return True


def _source_opponent_choice_requirement_supported(effect: SourceEffectDef) -> bool:
    raw = effect.raw or {}

    def walk(value: Any) -> bool:
        if isinstance(value, dict):
            if str(value.get("chosenBy", value.get("chosen_by", ""))).casefold() == "opponent":
                return True
            if str(value.get("chooser", "")).casefold() == "opponent":
                return True
            return any(walk(child) for child in value.values())
        if isinstance(value, (list, tuple)):
            return any(walk(child) for child in value)
        return False

    return walk(raw)


def _source_scry_requirement_supported(effect: SourceEffectDef, requirement: str) -> bool:
    if effect.kind != "scry" or requirement not in {"destination", "ordering"}:
        return False
    destinations = effect.raw.get("destinations")
    if not isinstance(destinations, list) or not destinations:
        return requirement == "ordering"
    supported_zones = {"hand", "deck-bottom", "deck-top", "discard", "inkwell"}
    for destination in destinations:
        if not isinstance(destination, dict):
            return False
        zone = destination.get("zone")
        if zone not in supported_zones:
            return False
        if destination.get("filter") or destination.get("filters"):
            return False
    return True


def _classify_condition(condition: Any | None) -> tuple[RuntimeSupportStatus, tuple[str, ...]]:
    if condition is None:
        return ("executable", ())
    kind = _condition_kind(condition)
    if kind in SUPPORTED_EFFECT_CONDITIONS:
        return ("executable", ())
    return ("unsupported", (f"unsupported_condition:{kind}",))


def _condition_kind(condition: Any) -> str:
    if hasattr(condition, "kind"):
        return str(condition.kind)
    if isinstance(condition, dict):
        return str(condition.get("kind") or condition.get("type") or "unknown")
    return "unknown"


def _runtime_effect_kind(source_kind: str) -> str:
    return ENGINE_EFFECT_MAP.get(source_kind) or to_engine_effect_kind(source_kind)


def _classify_keywords(card: CardDef) -> tuple[RuntimeSupportStatus, tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]] | None:
    names = {str(keyword).upper() for keyword in card.keywords}
    names.update(str(keyword.keyword).upper() for keyword in card.keyword_defs)
    statuses: list[RuntimeSupportStatus] = []
    blockers: list[str] = []
    evidence: list[str] = []
    required: list[str] = []
    verified: list[str] = []
    if any("SHIFT" in name for name in names):
        rules = get_shift_rules(card)
        required.extend(("legal_actions:PLAY_SHIFTED", "apply_action:PLAY_SHIFTED", "ZONE_UNDER", "used_shift_event", "automation:PLAY_SHIFTED"))
        if rules is None:
            statuses.append("unsupported")
            blockers.append("unsupported_shift:missing_rules")
        elif rules.unsupported_reason:
            statuses.append("unsupported")
            blockers.append(f"unsupported_shift:{rules.unsupported_reason}")
        elif rules.ink_cost is None:
            statuses.append("unsupported")
            blockers.append("unsupported_shift:missing_cost")
        else:
            statuses.append("executable")
            evidence.append("shift_rules:ink_cost")
            verified.extend(("legal_actions:PLAY_SHIFTED", "apply_action:PLAY_SHIFTED", "ZONE_UNDER", "used_shift_event", "automation:PLAY_SHIFTED"))
    if "SINGER" in names or any(name.startswith("SINGER") for name in names):
        statuses.append("executable")
        evidence.append("singer:song_threshold")
        required.extend(("legal_actions:SING_SONG", "apply_action:SING_SONG", "singer_exert_cost", "EffectResolver", "automation:SING_SONG"))
        verified.extend(("legal_actions:SING_SONG", "apply_action:SING_SONG", "singer_exert_cost", "EffectResolver", "automation:SING_SONG"))
    if "SING_TOGETHER" in names or "SINGTOGETHER" in names:
        statuses.append("unsupported")
        blockers.append("keyword:SING_TOGETHER")
        evidence.append("sing_together:not_implemented")
        required.append("multi_singer_prompt")
    if not statuses:
        return None
    return (_combine_statuses(statuses), tuple(sorted(set(blockers))), tuple(sorted(set(evidence))), tuple(sorted(set(required))), tuple(sorted(set(verified))))


def _combine_statuses(statuses: list[RuntimeSupportStatus] | tuple[RuntimeSupportStatus, ...]) -> RuntimeSupportStatus:
    if not statuses:
        return "executable"
    for status in ("unsupported", "source_preserved", "scaffold_only", "projected_but_requires_pending_input"):
        if status in statuses:
            return status  # type: ignore[return-value]
    return "executable"


def _deck_playability(deck: ResolvedDeck, card_results: tuple[CardRuntimeSupport, ...], blockers_by_copies: Counter[str]) -> str:
    validation = deck.validation or {}
    if validation.get("valid") is False or validation.get("unresolved_cards") or validation.get("ambiguous_cards") or validation.get("banned_cards"):
        return "invalid"
    if len(deck.playable_decklist_ids) != deck.deck_total_declared:
        return "invalid"
    if not blockers_by_copies and all(result.status == "executable" for result in card_results):
        return "fully_executable"
    if any(result.status in {"unsupported", "source_preserved", "scaffold_only"} for result in card_results):
        if _blocked_copies(deck, card_results) > max(deck.deck_total_declared, 1) * 0.50:
            return "source_only"
        return "partially_executable"
    total_blocked = sum(blockers_by_copies.values())
    total = max(deck.deck_total_declared, 1)
    if total_blocked <= total * 0.10:
        return "mostly_executable"
    return "partially_executable"


def _blocked_copies(deck: ResolvedDeck, card_results: tuple[CardRuntimeSupport, ...]) -> int:
    count_by_card_id = {card.card_id or card.raw_name: card.count for card in deck.cards}
    return sum(count_by_card_id.get(result.card_id, 1) for result in card_results if result.blockers or result.status != "executable")
