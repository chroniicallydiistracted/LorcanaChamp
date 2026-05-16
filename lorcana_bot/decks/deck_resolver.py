from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from lorcana_bot.card_logic import ExecutionStatus
from lorcana_bot.cards import CardDef
from lorcana_bot.importers.lorcanito_source_importer import import_lorcanito_source_cards

from .deck_loader import load_raw_deck_dir, write_resolved_deck
from .deck_schema import RawDeck, RawDeckCard, ResolvedDeck, ResolvedDeckCard

SCHEMA_VERSION = 1
CRITICAL_KEYWORDS = {"SINGER", "SING_TOGETHER", "SHIFT"}


@dataclass(frozen=True)
class SourceCardIndex:
    by_id: dict[str, dict[str, Any]]
    by_canonical_id: dict[str, tuple[dict[str, Any], ...]]
    by_exact_full_name: dict[str, tuple[dict[str, Any], ...]]
    by_normalized_full_name: dict[str, tuple[dict[str, Any], ...]]
    by_normalized_name_version: dict[tuple[str, str], tuple[dict[str, Any], ...]]
    by_normalized_simple_name: dict[str, tuple[dict[str, Any], ...]]
    by_external_id: dict[str, tuple[dict[str, Any], ...]]
    card_defs_by_id: dict[str, CardDef]


def normalize_card_name(value: str) -> str:
    text = str(value)
    text = text.replace("\u200b", "").replace("\u200c", "").replace("\u200d", "").replace("\ufeff", "")
    text = text.replace("’", "'").replace("‘", "'").replace("`", "'")
    text = text.replace("–", "-").replace("—", "-").replace("−", "-")
    text = text.strip().strip("\"'")
    text = re.sub(r"\s+", " ", text)
    return text.casefold()


def load_source_card_records(path: str | Path) -> list[dict[str, Any]]:
    source_path = Path(path)
    if not source_path.exists():
        raise ValueError(f"Source card JSON does not exist: {source_path}")
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    records = payload.get("cards", payload if isinstance(payload, list) else None)
    if not isinstance(records, list):
        raise ValueError(f"Source card JSON must contain a cards list: {source_path}")
    return [dict(record) for record in records if isinstance(record, dict)]


def build_source_card_index(records: list[dict[str, Any]], source_json_path: str | Path | None = None) -> SourceCardIndex:
    normalized = [_normalize_source_record(record) for record in records]
    card_defs_by_id: dict[str, CardDef] = {}
    if source_json_path is not None:
        db, _report = import_lorcanito_source_cards(source_json_path)
        card_defs_by_id = {card.id: card for card in db.all_cards()}
    by_id = {record["_resolved_id"]: record for record in normalized}
    by_canonical_id = _group(normalized, lambda record: record["_resolved_canonical_id"])
    by_exact_full_name = _group(normalized, lambda record: record["_resolved_full_name"])
    by_normalized_full_name = _group(normalized, lambda record: normalize_card_name(record["_resolved_full_name"]))
    by_normalized_name_version = _group(
        normalized,
        lambda record: (normalize_card_name(record.get("name") or ""), normalize_card_name(record.get("version") or "")),
    )
    by_normalized_simple_name = _group(normalized, lambda record: normalize_card_name(record.get("name") or ""))
    external: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in normalized:
        for key, value in _external_ids(record).items():
            external[f"{key}:{value}"].append(record)
    return SourceCardIndex(
        by_id=by_id,
        by_canonical_id={key: tuple(value) for key, value in sorted(by_canonical_id.items())},
        by_exact_full_name={key: tuple(value) for key, value in sorted(by_exact_full_name.items())},
        by_normalized_full_name={key: tuple(value) for key, value in sorted(by_normalized_full_name.items())},
        by_normalized_name_version={key: tuple(value) for key, value in sorted(by_normalized_name_version.items())},
        by_normalized_simple_name={key: tuple(value) for key, value in sorted(by_normalized_simple_name.items())},
        by_external_id={key: tuple(value) for key, value in sorted(external.items())},
        card_defs_by_id=card_defs_by_id,
    )


def resolve_deck_card(raw_card: RawDeckCard, index: SourceCardIndex) -> ResolvedDeckCard:
    candidates: tuple[dict[str, Any], ...] = ()
    status = "unresolved"
    exact = index.by_exact_full_name.get(raw_card.name)
    if exact:
        candidates, status = exact, "resolved_exact_full_name"
    else:
        normalized = normalize_card_name(raw_card.name)
        candidates = index.by_normalized_full_name.get(normalized, ())
        if candidates:
            status = "resolved_normalized_full_name"
        elif " - " in raw_card.name:
            name, version = raw_card.name.split(" - ", 1)
            candidates = index.by_normalized_name_version.get((normalize_card_name(name), normalize_card_name(version)), ())
            if candidates:
                status = "resolved_name_version"
        if not candidates:
            simple_exact = [record for record in index.by_normalized_simple_name.get(normalize_card_name(raw_card.name), ())]
            if len(simple_exact) == 1:
                candidates, status = tuple(simple_exact), "resolved_unique_simple_name"
            elif len(simple_exact) > 1:
                return _unresolved(raw_card, "ambiguous_name", simple_exact)
        if not candidates and len(normalized) >= 4:
            partial = [
                record
                for key, records in index.by_normalized_full_name.items()
                if normalized in key
                for record in records
            ]
            if len(partial) == 1:
                candidates, status = tuple(partial), "unique_partial_match"
            elif len(partial) > 1:
                return _unresolved(raw_card, "ambiguous_name", partial)
    if not candidates:
        return _unresolved(raw_card, "not_found", ())
    canonical_ids = {record["_resolved_canonical_id"] for record in candidates}
    if len(candidates) > 1 and len(canonical_ids) > 1:
        return _unresolved(raw_card, "ambiguous_name", candidates)
    selected = _representative(candidates)
    if len(candidates) > 1:
        status = "resolved_reprint_group"
    return _resolved(raw_card, selected, candidates, status, index.card_defs_by_id.get(selected["_resolved_id"]))


def resolve_deck(raw_deck: RawDeck, source_json_path: str | Path) -> ResolvedDeck:
    records = load_source_card_records(source_json_path)
    index = build_source_card_index(records, source_json_path)
    cards = tuple(resolve_deck_card(card, index) for card in raw_deck.cards)
    playable = tuple(card_id for card in cards if card.resolved and card.card_id for card_id in [card.card_id] for _ in range(card.count))
    resolved_inks = tuple(sorted({color for card in cards if card.resolved for color in card.colors}))
    resolved = ResolvedDeck(
        schema_version=SCHEMA_VERSION,
        id=raw_deck.id,
        name=raw_deck.name,
        format=raw_deck.format,
        source_site=raw_deck.source_site,
        source_deck_id=raw_deck.source_deck_id,
        player=raw_deck.player,
        placement=raw_deck.placement,
        event=raw_deck.event,
        event_date=raw_deck.event_date,
        raw_ink_colors=raw_deck.ink_colors,
        resolved_ink_colors=resolved_inks,
        archetype=raw_deck.archetype,
        purpose=raw_deck.purpose,
        deck_total_declared=raw_deck.deck_total,
        deck_total_resolved=sum(card.count for card in cards if card.resolved),
        cards=cards,
        playable_decklist_ids=playable,
        validation={},
        mapping_summary={},
        playability="invalid",
    )
    from .deck_mapping_report import build_deck_mapping_summary, classify_deck_playability
    from .deck_validator import validate_resolved_deck

    validation = validate_resolved_deck(resolved)
    resolved = _replace_resolved_metadata(resolved, validation=validation)
    playability = classify_deck_playability(resolved)
    resolved = _replace_resolved_metadata(resolved, playability=playability)
    return _replace_resolved_metadata(resolved, mapping_summary=build_deck_mapping_summary(resolved))


def resolve_deck_suite(deck_dir: str | Path, source_json_path: str | Path, out_dir: str | Path) -> dict[str, Any]:
    raw_decks = load_raw_deck_dir(deck_dir)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    resolved_decks: list[ResolvedDeck] = []
    for raw_deck in raw_decks:
        deck = resolve_deck(raw_deck, source_json_path)
        path = out / f"{deck.id}.resolved.json"
        write_resolved_deck(deck, path)
        written.append(str(path))
        resolved_decks.append(deck)
    unresolved = [
        {"deck_id": deck.id, "card_name": card.raw_name, "reason": card.resolution_error}
        for deck in resolved_decks
        for card in deck.cards
        if not card.resolved and card.resolution_error == "not_found"
    ]
    ambiguous = [
        {"deck_id": deck.id, "card_name": card.raw_name, "candidate_ids": list(card.candidate_ids)}
        for deck in resolved_decks
        for card in deck.cards
        if not card.resolved and card.resolution_error == "ambiguous_name"
    ]
    summary = {
        "schema_version": SCHEMA_VERSION,
        "deck_count": len(raw_decks),
        "resolved_decks": sum(1 for deck in resolved_decks if all(card.resolved for card in deck.cards)),
        "invalid_decks": sum(1 for deck in resolved_decks if not deck.validation.get("valid")),
        "unresolved_cards": unresolved,
        "ambiguous_cards": ambiguous,
        "written_files": sorted(written),
    }
    (out / "suite_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def resolved_deck_from_dict(raw: dict[str, Any]) -> ResolvedDeck:
    cards = tuple(
        ResolvedDeckCard(
            raw_name=str(item["raw_name"]),
            count=int(item["count"]),
            raw_type=item.get("raw_type"),
            resolved=bool(item["resolved"]),
            resolution_status=str(item["resolution_status"]),
            resolution_error=item.get("resolution_error"),
            card_id=item.get("card_id"),
            canonical_id=item.get("canonical_id"),
            name=item.get("name"),
            version=item.get("version"),
            full_name=item.get("full_name"),
            ink=item.get("ink"),
            colors=tuple(item.get("colors", ())),
            card_type=item.get("card_type"),
            cost=item.get("cost"),
            inkable=item.get("inkable"),
            source_mapping_status=item.get("source_mapping_status"),
            source_execution_status=item.get("source_execution_status"),
            keyword_defs=tuple(item.get("keyword_defs", ())),
            ability_type_counts=dict(item.get("ability_type_counts", {})),
            effect_type_counts=dict(item.get("effect_type_counts", {})),
            trigger_event_counts=dict(item.get("trigger_event_counts", {})),
            condition_type_counts=dict(item.get("condition_type_counts", {})),
            cost_type_counts=dict(item.get("cost_type_counts", {})),
            unsupported_blockers=tuple(item.get("unsupported_blockers", ())),
            candidate_ids=tuple(item.get("candidate_ids", ())),
        )
        for item in raw.get("cards", ())
    )
    return ResolvedDeck(
        schema_version=int(raw.get("schema_version", SCHEMA_VERSION)),
        id=str(raw["id"]),
        name=str(raw["name"]),
        format=str(raw["format"]),
        source_site=raw.get("source_site"),
        source_deck_id=raw.get("source_deck_id"),
        player=raw.get("player"),
        placement=raw.get("placement"),
        event=raw.get("event"),
        event_date=raw.get("event_date"),
        raw_ink_colors=tuple(raw.get("raw_ink_colors", ())),
        resolved_ink_colors=tuple(raw.get("resolved_ink_colors", ())),
        archetype=raw.get("archetype"),
        purpose=tuple(raw.get("purpose", ())),
        deck_total_declared=int(raw.get("deck_total_declared", 0)),
        deck_total_resolved=int(raw.get("deck_total_resolved", 0)),
        cards=cards,
        playable_decklist_ids=tuple(raw.get("playable_decklist_ids", ())),
        validation=dict(raw.get("validation", {})),
        mapping_summary=dict(raw.get("mapping_summary", {})),
        playability=str(raw.get("playability", "invalid")),
    )


def _normalize_source_record(record: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(record)
    card_id = str(record.get("id") or record.get("canonicalId") or record.get("sourceFile"))
    canonical_id = str(record.get("canonicalId") or card_id)
    name = str(record.get("name") or card_id)
    version = str(record.get("version") or "")
    full_name = f"{name} - {version}" if version else name
    normalized["_resolved_id"] = card_id
    normalized["_resolved_canonical_id"] = canonical_id
    normalized["_resolved_full_name"] = full_name
    ink_type = record.get("inkType")
    if isinstance(ink_type, str):
        colors = (ink_type.lower(),)
    elif isinstance(ink_type, list):
        colors = tuple(str(color).lower() for color in ink_type if color)
    else:
        colors = ()
    normalized["_resolved_colors"] = colors
    normalized.setdefault("abilities", [])
    normalized.setdefault("raw", {})
    return normalized


def _group(records: list[dict[str, Any]], key_func) -> dict[Any, tuple[dict[str, Any], ...]]:
    grouped: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        key = key_func(record)
        if key not in {"", None, ("", "")}:
            grouped[key].append(record)
    return {key: tuple(sorted(value, key=_representative_key)) for key, value in grouped.items()}


def _external_ids(record: dict[str, Any]) -> dict[str, str]:
    raw = record.get("externalIds") or record.get("external_ids") or {}
    return {str(key): str(value) for key, value in raw.items()} if isinstance(raw, dict) else {}


def _representative(candidates: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    return sorted(candidates, key=_representative_key)[0]


def _representative_key(record: dict[str, Any]) -> tuple[Any, Any, Any, str]:
    return (
        record.get("_resolved_canonical_id") or "",
        _number_or_string(record.get("set")),
        _number_or_string(record.get("cardNumber")),
        record.get("_resolved_id") or "",
    )


def _number_or_string(value: Any) -> tuple[int, Any]:
    text = str(value or "")
    return (0, int(text)) if text.isdigit() else (1, text)


def _unresolved(raw_card: RawDeckCard, error: str, candidates: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> ResolvedDeckCard:
    return ResolvedDeckCard(
        raw_name=raw_card.name,
        count=raw_card.count,
        raw_type=raw_card.type,
        resolved=False,
        resolution_status="unresolved",
        resolution_error=error,
        candidate_ids=tuple(record["_resolved_id"] for record in sorted(candidates, key=_representative_key)),
    )


def _resolved(
    raw_card: RawDeckCard,
    record: dict[str, Any],
    candidates: tuple[dict[str, Any], ...],
    status: str,
    card_def: CardDef | None,
) -> ResolvedDeckCard:
    source = card_def.raw_lorcanito_source if card_def else record
    ability_counts = Counter(str(ability.get("type") or "unknown") for ability in source.get("abilities", []) if isinstance(ability, dict))
    return ResolvedDeckCard(
        raw_name=raw_card.name,
        count=raw_card.count,
        raw_type=raw_card.type,
        resolved=True,
        resolution_status=status,
        card_id=record["_resolved_id"],
        canonical_id=record["_resolved_canonical_id"],
        name=str(record.get("name") or ""),
        version=str(record.get("version") or ""),
        full_name=record["_resolved_full_name"],
        ink=(record["_resolved_colors"][0] if record["_resolved_colors"] else None),
        colors=record["_resolved_colors"],
        card_type=str(record.get("cardType") or "unknown"),
        cost=_int_or_none(record.get("cost")),
        inkable=bool(record.get("inkable")) if record.get("inkable") is not None else None,
        source_mapping_status=(card_def.source_mapping_status if card_def else None),
        source_execution_status=(card_def.source_execution_status if card_def else None),
        keyword_defs=tuple(keyword.to_dict() for keyword in card_def.keyword_defs) if card_def else (),
        ability_type_counts=dict(sorted(ability_counts.items())),
        effect_type_counts=_effect_type_counts(card_def),
        trigger_event_counts=_trigger_event_counts(card_def),
        condition_type_counts=_condition_type_counts(card_def),
        cost_type_counts=_cost_type_counts(card_def),
        unsupported_blockers=_unsupported_blockers(card_def),
        candidate_ids=tuple(candidate["_resolved_id"] for candidate in sorted(candidates, key=_representative_key)),
    )


def _effect_type_counts(card: CardDef | None) -> dict[str, int]:
    if not card:
        return {}
    counts = Counter(effect.kind for effect in card.source_effects)
    for ability in card.source_abilities:
        for effect in ability.effects:
            _count_effect_tree(effect, counts)
    return dict(sorted(counts.items()))


def _count_effect_tree(effect, counts: Counter[str]) -> None:
    counts[effect.kind] += 1
    for child in (*effect.effects, *effect.branches):
        _count_effect_tree(child, counts)


def _trigger_event_counts(card: CardDef | None) -> dict[str, int]:
    return dict(sorted(Counter(trigger.event for trigger in (card.source_triggers if card else ())).items()))


def _condition_type_counts(card: CardDef | None) -> dict[str, int]:
    counts: Counter[str] = Counter()
    if card:
        for ability in card.source_abilities:
            if ability.condition:
                counts[ability.condition.kind] += 1
            for effect in ability.effects:
                _count_effect_conditions(effect, counts)
    return dict(sorted(counts.items()))


def _count_effect_conditions(effect, counts: Counter[str]) -> None:
    if effect.condition:
        counts[effect.condition.kind] += 1
    for child in (*effect.effects, *effect.branches):
        _count_effect_conditions(child, counts)


def _cost_type_counts(card: CardDef | None) -> dict[str, int]:
    counts = Counter(cost.kind for ability in (card.source_abilities if card else ()) for cost in ability.costs)
    return dict(sorted(counts.items()))


def _unsupported_blockers(card: CardDef | None) -> tuple[str, ...]:
    if not card:
        return ("missing_carddef_status",)
    blockers: set[str] = set()

    # B2-FIX: Classify triggers more specifically instead of just broad unsupported_trigger
    if card.source_triggers:
        # Check if any triggers can be projected as executable
        projected_triggers = card.triggers  # These are already projected TriggerDefs
        executable_triggers = len(projected_triggers)
        total_triggers = len(card.source_triggers)

        # If all triggers are executable, don't add any blocker
        # If some are executable, add specific blocker for unprojected ones
        if total_triggers > 0:
            if executable_triggers == 0:
                # No triggers can be projected - classify by specific reason
                for trigger in card.source_triggers:
                    reason = _trigger_blocker_reason(trigger)
                    blockers.add(reason)
            # If some triggers are executable, those are already projected,
            # and we only count the unexecutable ones

    if card.source_static_abilities:
        blockers.add("unsupported_static_effect")
    if card.source_replacement_abilities:
        blockers.add("unsupported_replacement_effect")
    if any(ability.kind == "activated" for ability in card.source_abilities):
        blockers.add("unsupported_activated_ability")
    for keyword in card.keyword_defs:
        if keyword.keyword in CRITICAL_KEYWORDS:
            blockers.add(f"keyword:{keyword.keyword}")
    for ability in card.source_abilities:
        for cost in ability.costs:
            if cost.execution_status != ExecutionStatus.EXECUTABLE:
                blockers.add(f"unsupported_cost:{cost.kind}")
        if ability.trigger and ability.trigger.execution_status != ExecutionStatus.EXECUTABLE:
            # This is for ability-level trigger execution status
            reason = _trigger_blocker_reason(ability.trigger)
            blockers.add(reason)
        for effect in ability.effects:
            _collect_effect_blockers(effect, blockers)
    for item in card.unsupported_abilities:
        reason = item.get("reason") or item.get("type") or item.get("mapping_status")
        if reason and reason not in {
            ExecutionStatus.MAPPED_NOT_EXECUTABLE,
            ExecutionStatus.UNSUPPORTED_CONDITION,
            ExecutionStatus.UNSUPPORTED_COST,
            ExecutionStatus.UNSUPPORTED_ENGINE_MECHANIC,
            ExecutionStatus.UNSUPPORTED_TARGETING,
            ExecutionStatus.UNSUPPORTED_CHOICE,
        }:
            blockers.add(str(reason))
    return tuple(sorted(blockers))


def _trigger_blocker_reason(trigger) -> str:
    """Determine specific blocker reason for a trigger."""
    from lorcana_bot.card_logic import SourceTriggerDef

    if not isinstance(trigger, SourceTriggerDef):
        return "unsupported_trigger"

    # Check event type
    event = getattr(trigger, 'event', None)
    if event:
        supported_events = {"play", "quest", "challenge", "banish", "start-turn", "end-turn", "ink", "move"}
        if event not in supported_events:
            return f"unsupported_trigger_event:{event}"

    # Check condition
    condition = getattr(trigger, 'condition', None) or getattr(trigger, 'raw', {}).get('condition')
    if condition:
        condition_kind = condition.get('kind') or condition.get('type') if isinstance(condition, dict) else None
        if condition_kind:
            supported_conditions = {"always", "your-turn", "opponent-turn", "during-turn",
                                    "has-character-count", "has-item-count", "has-location-count",
                                    "has-character-with-keyword", "has-character-with-classification",
                                    "has-named-character", "is-exerted", "exerted", "has-any-damage",
                                    "no-damage", "self-has-damage", "inkwell-count", "and", "or", "not"}
            if condition_kind not in supported_conditions:
                return f"unsupported_trigger_condition:{condition_kind}"

    # Check target (on filter)
    on_value = getattr(trigger, 'on', None)
    if on_value:
        supported_on = {"SELF", "YOU", "CONTROLLER", "OPPONENT", "YOUR_CHARACTERS",
                        "YOUR_OTHER_CHARACTERS", "OPPOSING_CHARACTERS", "ANY_CHARACTER"}
        if isinstance(on_value, str) and on_value not in supported_on:
            return f"unsupported_trigger_on:{on_value}"
        elif isinstance(on_value, dict):
            return "unsupported_trigger_on:complex_filter"

    # Check for unsupported resolution requirements (chosen targets, scry, etc.)
    raw = getattr(trigger, 'raw', {})
    if raw:
        # Check for scry/search/reveal requirements
        for effect_data in raw.get('effects', []):
            if isinstance(effect_data, dict):
                kind = effect_data.get('type') or effect_data.get('kind')
                if kind in {'scry', 'search-deck', 'reveal', 'reveal-hand', 'reveal-inkwell', 'name-a-card'}:
                    return f"unsupported_trigger_effect:{kind}"
                # Check for chosen target requirements
                target = effect_data.get('target', {})
                if isinstance(target, dict):
                    selector = target.get('selector') or target.get('type')
                    if selector in {'chosen', 'CHOSEN_CHARACTER', 'CHOSEN_OPPOSING_CHARACTER', 'CHOSEN_DAMAGED_CHARACTER'}:
                        return f"unsupported_trigger_target:{selector}"

    # Check execution status
    exec_status = getattr(trigger, 'execution_status', None)
    if exec_status == ExecutionStatus.UNSUPPORTED_TRIGGER:
        return "unsupported_trigger_not_projected"

    # Default to general unsupported trigger
    return "unsupported_trigger"


def _collect_effect_blockers(effect, blockers: set[str]) -> None:
    if effect.execution_status != ExecutionStatus.EXECUTABLE:
        blockers.add(f"unsupported_effect:{effect.kind}")
        if effect.execution_status == ExecutionStatus.UNSUPPORTED_CHOICE:
            blockers.add(str(effect.execution_status))
    if effect.target and effect.target.execution_status != ExecutionStatus.EXECUTABLE:
        blockers.add(f"unsupported_target:{effect.target.selector or effect.target.alias or effect.target.kind}")
    if effect.condition and effect.condition.execution_status != ExecutionStatus.EXECUTABLE:
        blockers.add(f"unsupported_condition:{effect.condition.kind}")
    for child in (*effect.effects, *effect.branches):
        _collect_effect_blockers(child, blockers)


def _replace_resolved_metadata(
    deck: ResolvedDeck,
    *,
    validation: dict[str, Any] | None = None,
    mapping_summary: dict[str, Any] | None = None,
    playability: str | None = None,
) -> ResolvedDeck:
    return ResolvedDeck(
        schema_version=deck.schema_version,
        id=deck.id,
        name=deck.name,
        format=deck.format,
        source_site=deck.source_site,
        source_deck_id=deck.source_deck_id,
        player=deck.player,
        placement=deck.placement,
        event=deck.event,
        event_date=deck.event_date,
        raw_ink_colors=deck.raw_ink_colors,
        resolved_ink_colors=deck.resolved_ink_colors,
        archetype=deck.archetype,
        purpose=deck.purpose,
        deck_total_declared=deck.deck_total_declared,
        deck_total_resolved=deck.deck_total_resolved,
        cards=deck.cards,
        playable_decklist_ids=deck.playable_decklist_ids,
        validation=validation if validation is not None else deck.validation,
        mapping_summary=mapping_summary if mapping_summary is not None else deck.mapping_summary,
        playability=playability if playability is not None else deck.playability,
    )


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
