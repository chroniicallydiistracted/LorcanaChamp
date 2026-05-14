from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from lorcana_bot.cards import AbilityCostDef, AbilityDef, CardDef, EffectDef, load_card_database


@dataclass(frozen=True)
class AbilityMappingReport:
    schema_version: int
    total_cards: int
    total_ability_records: int
    mapped_effects: int
    mapped_triggers: int
    mapped_activated_abilities: int
    mapped_static_abilities: int
    fully_mapped_cards: int
    partially_mapped_cards: int
    classified_only_cards: int
    unsupported_records: int
    unsupported_by_reason: dict[str, int]
    top_unsupported_patterns: list[dict[str, Any]]
    card_ids_with_unsupported_gameplay_critical_text: list[str]
    set_coverage: dict[str, dict[str, int]] = field(default_factory=dict)
    mechanic_coverage: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def map_effect_from_text(text: str) -> EffectDef | None:
    lowered = text.casefold()
    amount = _first_int(lowered, default=1)
    if "draw" in lowered:
        return EffectDef("draw", amount)
    if "gain" in lowered and "lore" in lowered:
        return EffectDef("gain_lore", amount)
    if "loses" in lowered and "lore" in lowered:
        return EffectDef("lose_lore", amount, "opponent")
    if "damage" in lowered:
        return EffectDef("deal_damage", amount, "chosen_character")
    if "remove" in lowered and "damage" in lowered:
        return EffectDef("remove_damage", amount, "chosen_character")
    if "banish" in lowered:
        return EffectDef("banish", 1, "chosen_character")
    if "discard" in lowered:
        return EffectDef("discard", amount, "opponent")
    if "return" in lowered and "hand" in lowered:
        return EffectDef("return_to_hand", 1, "chosen_character")
    if "ready" in lowered:
        return EffectDef("ready", 1, "chosen_character")
    if "exert" in lowered:
        return EffectDef("exert", 1, "chosen_character")
    return None


def map_activated_ability(raw: dict[str, Any], card_id: str, index: int = 0) -> AbilityDef | None:
    text = str(raw.get("fullText") or raw.get("effect") or raw.get("name") or "")
    lowered = text.casefold()
    costs: list[AbilityCostDef] = []
    if "exert" in lowered or "{e}" in lowered or "↷" in lowered:
        costs.append(AbilityCostDef("exert_source"))
    if "pay" in lowered and "ink" in lowered:
        costs.append(AbilityCostDef("pay_ink", _first_int(lowered, default=1)))
    if "discard" in lowered and "to" in lowered:
        costs.append(AbilityCostDef("discard_cards", _first_int(lowered, default=1)))
    if "banish this" in lowered:
        costs.append(AbilityCostDef("banish_source"))
    if not costs and raw.get("type") not in {"activated", "static-triggered"}:
        return None
    effect = map_effect_from_text(text)
    effects = (effect,) if effect else ()
    return AbilityDef(id=f"{card_id}:activated:{index}", name=raw.get("name"), type="activated", effects=effects, costs=tuple(costs), raw=dict(raw))


def build_ability_mapping_report(db=None) -> AbilityMappingReport:
    if db is None:
        db = load_card_database("imported")
    total_records = mapped_effects = mapped_triggers = mapped_activated = mapped_static = 0
    fully = partial = classified = unsupported = 0
    unsupported_by_reason: Counter[str] = Counter()
    patterns: Counter[str] = Counter()
    critical: list[str] = []
    set_counts: dict[str, Counter[str]] = defaultdict(Counter)
    mechanics: Counter[str] = Counter()

    for card in sorted(db.all_cards(), key=lambda c: c.id):
        records = list(card.abilities) + list(card.unsupported_abilities) + [{"source": "text_effect", "effect": effect} for effect in card.text_effects]
        total_records += len(records)
        card_mapped = 0
        card_unsupported = 0
        for index, record in enumerate(records):
            text = str(record.get("full_text") or record.get("fullText") or record.get("effect") or record.get("name") or record)
            effect = map_effect_from_text(text)
            if effect is not None:
                mapped_effects += 1
                card_mapped += 1
                mechanics[effect.kind] += 1
            ability = map_activated_ability(record, card.id, index) if isinstance(record, dict) else None
            if ability is not None:
                mapped_activated += 1
                card_mapped += 1
                mechanics["activated"] += 1
            if record.get("type") in {"static", "keyword"}:
                mapped_static += 1
                card_mapped += 1
            if record.get("type") in {"triggered", "static-triggered"} or "whenever" in text.casefold() or "when you play" in text.casefold():
                mapped_triggers += 1
                card_mapped += 1
            if card_mapped == 0 or (effect is None and ability is None and record.get("type") not in {"static", "keyword", "triggered", "static-triggered"}):
                reason = _unsupported_reason(text, record)
                unsupported_by_reason[reason] += 1
                patterns[_pattern(text)] += 1
                card_unsupported += 1
        if records and card_unsupported == 0:
            fully += 1
        elif card_mapped and card_unsupported:
            partial += 1
        elif records:
            classified += 1
        set_key = card.set_code or "unknown"
        set_counts[set_key]["cards"] += 1
        if card_unsupported:
            set_counts[set_key]["unsupported_cards"] += 1
            if _critical_text(card):
                critical.append(card.id)
        unsupported += card_unsupported

    top_patterns = [{"pattern": pattern, "count": count} for pattern, count in patterns.most_common(20)]
    return AbilityMappingReport(
        schema_version=1,
        total_cards=len(db.all_cards()),
        total_ability_records=total_records,
        mapped_effects=mapped_effects,
        mapped_triggers=mapped_triggers,
        mapped_activated_abilities=mapped_activated,
        mapped_static_abilities=mapped_static,
        fully_mapped_cards=fully,
        partially_mapped_cards=partial,
        classified_only_cards=classified,
        unsupported_records=unsupported,
        unsupported_by_reason=dict(sorted(unsupported_by_reason.items())),
        top_unsupported_patterns=top_patterns,
        card_ids_with_unsupported_gameplay_critical_text=critical[:100],
        set_coverage={key: dict(value) for key, value in sorted(set_counts.items())},
        mechanic_coverage=dict(sorted(mechanics.items())),
    )


def _first_int(text: str, default: int) -> int:
    for token in text.replace(".", " ").replace(",", " ").split():
        if token.isdigit():
            return int(token)
    return default


def _unsupported_reason(text: str, record: dict[str, Any]) -> str:
    lowered = text.casefold()
    if any(word in lowered for word in ("instead", "prevent", "can't", "cannot")):
        return "replacement_or_restriction"
    if any(word in lowered for word in ("choose", "named", "reveal", "search")):
        return "complex_choice_or_search"
    if record.get("type"):
        return f"unmapped_type:{record.get('type')}"
    return "unmapped_text"


def _pattern(text: str) -> str:
    normalized = " ".join(text.casefold().split())
    return normalized[:120] or "<empty>"


def _critical_text(card: CardDef) -> bool:
    text = " ".join([card.rules_text or "", *card.text_effects, *(str(a) for a in card.unsupported_abilities)]).casefold()
    return any(word in text for word in ("banish", "damage", "draw", "lore", "instead", "can't", "discard", "exert"))
