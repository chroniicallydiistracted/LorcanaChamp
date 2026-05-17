from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .card_logic import (
    SourceAbilityDef,
    SourceEffectDef,
    SourceReplacementEffectDef,
    SourceStaticEffectDef,
    SourceTriggerDef,
)
from .constants import CARD_TYPES, FORMAT_CORE_CONSTRUCTED, INKS

_CARD_TYPE_MAP = {
    "character": "character",
    "action": "action",
    "item": "item",
    "location": "location",
}

_RARITY_MAP = {
    "common": "common",
    "uncommon": "uncommon",
    "rare": "rare",
    "super rare": "super_rare",
    "legendary": "legendary",
    "enchanted": "enchanted",
    "special": "special",
    "epic": "epic",
    "iconic": "iconic",
}


@dataclass(frozen=True, slots=True)
class EffectDef:
    """Declarative card effect interpreted by lorcana_bot.effects."""

    kind: str
    amount: int = 0
    target: str | None = None  # None, "opposing_character", "chosen_character"
    value: Any | None = None
    keyword: str | None = None
    effects: tuple["EffectDef", ...] = ()
    condition: dict[str, Any] | None = None
    optional: bool = False
    duration: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @classmethod
    def from_dict(cls, raw: dict) -> "EffectDef":
        return cls(
            kind=raw["kind"],
            amount=int(raw.get("amount", 0)),
            target=raw.get("target"),
            value=raw.get("value"),
            keyword=raw.get("keyword"),
            effects=tuple(cls.from_dict(effect) for effect in raw.get("effects", [])),
            condition=dict(raw["condition"]) if isinstance(raw.get("condition"), dict) else None,
            optional=bool(raw.get("optional", False)),
            duration=raw.get("duration"),
            raw=dict(raw.get("raw", {})),
        )

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "amount": self.amount,
            "target": self.target,
            "value": self.value,
            "keyword": self.keyword,
            "effects": [effect.to_dict() for effect in self.effects],
            "condition": self.condition,
            "optional": self.optional,
            "duration": self.duration,
            "raw": self.raw,
        }


@dataclass(frozen=True, slots=True)
class AbilityCostDef:
    kind: str
    amount: int = 1
    selector: Any | None = None

    @classmethod
    def from_dict(cls, raw: dict) -> "AbilityCostDef":
        return cls(kind=str(raw["kind"]), amount=int(raw.get("amount", 1)), selector=raw.get("selector"))

    def to_dict(self) -> dict:
        return {"kind": self.kind, "amount": self.amount, "selector": self.selector}


@dataclass(frozen=True, slots=True)
class AbilityDef:
    id: str
    name: str | None
    type: str
    effects: tuple[EffectDef, ...]
    costs: tuple[AbilityCostDef, ...] = ()
    once_per_turn: bool = True
    source_zones: tuple[str, ...] = ("play",)
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @classmethod
    def from_dict(cls, raw: dict) -> "AbilityDef":
        return cls(
            id=str(raw["id"]),
            name=raw.get("name"),
            type=str(raw.get("type", "activated")),
            effects=tuple(EffectDef.from_dict(effect) for effect in raw.get("effects", [])),
            costs=tuple(AbilityCostDef.from_dict(cost) for cost in raw.get("costs", [])),
            once_per_turn=bool(raw.get("once_per_turn", True)),
            source_zones=tuple(raw.get("source_zones", ("play",))),
            raw=dict(raw.get("raw", {})),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "effects": [effect.to_dict() for effect in self.effects],
            "costs": [cost.to_dict() for cost in self.costs],
            "once_per_turn": self.once_per_turn,
            "source_zones": list(self.source_zones),
            "raw": self.raw,
        }


@dataclass(frozen=True, slots=True)
class TriggerDef:
    id: str
    event: str
    effects: tuple[EffectDef, ...] = ()
    source_zones: tuple[str, ...] = ("play",)
    condition: dict[str, Any] | None = None
    timing: str | None = None  # "at", "when", "whenever"
    on: Any | None = None  # Subject filter (SELF, YOU, YOUR_CHARACTERS, etc.)
    subject: Any | None = None  # Alternative subject specification
    restrictions: tuple[dict[str, Any], ...] = ()  # Trigger restrictions
    optional: bool = False  # Whether the trigger is optional
    auto_resolve: bool | None = None  # Auto-resolve without choice
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @classmethod
    def from_dict(cls, raw: dict) -> "TriggerDef":
        return cls(
            id=str(raw["id"]),
            event=str(raw["event"]),
            effects=tuple(EffectDef.from_dict(effect) for effect in raw.get("effects", [])),
            source_zones=tuple(raw.get("source_zones", ("play",))),
            condition=dict(raw["condition"]) if isinstance(raw.get("condition"), dict) else None,
            timing=raw.get("timing"),
            on=raw.get("on"),
            subject=raw.get("subject"),
            restrictions=tuple(raw.get("restrictions", ()) if isinstance(raw.get("restrictions"), list) else ()),
            optional=bool(raw.get("optional", False)),
            auto_resolve=raw.get("auto_resolve") if "auto_resolve" in raw else None,
            raw=dict(raw.get("raw", {})),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "event": self.event,
            "effects": [effect.to_dict() for effect in self.effects],
            "source_zones": list(self.source_zones),
            "condition": self.condition,
            "timing": self.timing,
            "on": self.on,
            "subject": self.subject,
            "restrictions": list(self.restrictions),
            "optional": self.optional,
            "auto_resolve": self.auto_resolve,
            "raw": self.raw,
        }


@dataclass(frozen=True, slots=True)
class KeywordDef:
    keyword: str
    value: int | str | None = None
    target_name: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @classmethod
    def from_dict(cls, raw: dict) -> "KeywordDef":
        return cls(
            keyword=str(raw["keyword"]),
            value=raw.get("value"),
            target_name=raw.get("target_name"),
            raw=dict(raw.get("raw", {})),
        )

    def to_dict(self) -> dict:
        return {"keyword": self.keyword, "value": self.value, "target_name": self.target_name, "raw": self.raw}


@dataclass(frozen=True, slots=True)
class CardDef:
    id: str
    full_name: str
    ink: str
    cost: int
    inkable: bool
    card_type: str
    strength: int | None = None
    willpower: int | None = None
    lore: int | None = None
    keywords: tuple[str, ...] = ()
    effects: tuple[EffectDef, ...] = ()
    move_cost: int | None = None
    version: str = "demo-0.1"
    colors: tuple[str, ...] = ()
    name: str | None = None
    simple_name: str | None = None
    subtypes: tuple[str, ...] = ()
    rarity: str | None = None
    set_code: str | None = None
    set_name: str | None = None
    collector_number: str | None = None
    full_identifier: str | None = None
    rules_text: str | None = None
    flavor_text: str | None = None
    abilities: tuple[dict[str, Any], ...] = ()
    keyword_defs: tuple[KeywordDef, ...] = ()
    activated_abilities: tuple[AbilityDef, ...] = ()
    triggers: tuple[TriggerDef, ...] = ()
    unsupported_abilities: tuple[dict[str, Any], ...] = ()
    source_abilities: tuple[SourceAbilityDef, ...] = ()
    source_effects: tuple[SourceEffectDef, ...] = ()
    source_triggers: tuple[SourceTriggerDef, ...] = ()
    source_static_abilities: tuple[SourceStaticEffectDef, ...] = ()
    source_replacement_abilities: tuple[SourceReplacementEffectDef, ...] = ()
    # B10: Play modes support
    action_subtype: str | None = None  # "song" for song actions
    raw_lorcanito_source: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)
    source_mapping_status: str = "unknown"
    source_execution_status: str = "unknown"
    text_effects: tuple[str, ...] = ()
    images: dict[str, Any] = field(default_factory=dict)
    external_links: dict[str, Any] = field(default_factory=dict)
    allowed_in_formats: dict[str, Any] = field(default_factory=dict)
    allowed_in_tournaments_from_date: str | None = None
    reprint_of_id: str | None = None
    base_id: str | None = None
    max_copies_in_deck: int | None = None
    has_max_copies_override: bool = False
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    def __post_init__(self) -> None:
        colors = self.colors or ((self.ink,) if self.ink else ())
        object.__setattr__(self, "colors", tuple(colors))
        if self.ink and self.ink not in INKS:
            raise ValueError(f"Unsupported ink {self.ink!r} on {self.id}")
        unsupported_colors = [color for color in self.colors if color not in INKS]
        if unsupported_colors:
            raise ValueError(f"Unsupported colors {unsupported_colors!r} on {self.id}")
        if self.card_type not in CARD_TYPES:
            raise ValueError(f"Unsupported card type {self.card_type!r} on {self.id}")
        if self.cost < 0:
            raise ValueError("Card cost cannot be negative")
        if self.card_type == "character":
            required = (self.strength, self.willpower, self.lore)
            if any(value is None for value in required):
                raise ValueError(f"Character {self.id} needs strength/willpower/lore")

    @classmethod
    def from_dict(cls, raw: dict) -> "CardDef":
        raw_effects = raw.get("effects", [])
        effects: tuple[EffectDef, ...]
        text_effects: tuple[str, ...]
        if all(isinstance(effect, dict) for effect in raw_effects):
            effects = tuple(EffectDef.from_dict(e) for e in raw_effects)
            text_effects = tuple(raw.get("text_effects", []))
        else:
            effects = ()
            text_effects = tuple(str(effect) for effect in raw_effects)
        return cls(
            id=str(raw["id"]),
            full_name=raw["full_name"],
            ink=raw["ink"],
            cost=int(raw["cost"]),
            inkable=bool(raw["inkable"]),
            card_type=raw["card_type"],
            strength=raw.get("strength"),
            willpower=raw.get("willpower"),
            lore=raw.get("lore"),
            keywords=tuple(raw.get("keywords", [])),
            effects=effects,
            move_cost=raw.get("move_cost"),
            version=raw.get("version", "unknown"),
            colors=tuple(raw.get("colors", [])),
            name=raw.get("name"),
            simple_name=raw.get("simple_name"),
            subtypes=tuple(raw.get("subtypes", [])),
            rarity=raw.get("rarity"),
            set_code=raw.get("set_code"),
            set_name=raw.get("set_name"),
            collector_number=raw.get("collector_number"),
            full_identifier=raw.get("full_identifier"),
            rules_text=raw.get("rules_text"),
            flavor_text=raw.get("flavor_text"),
            abilities=tuple(raw.get("abilities", [])),
            keyword_defs=tuple(KeywordDef.from_dict(keyword) for keyword in raw.get("keyword_defs", [])),
            activated_abilities=tuple(AbilityDef.from_dict(ability) for ability in raw.get("activated_abilities", [])),
            triggers=tuple(TriggerDef.from_dict(trigger) for trigger in raw.get("triggers", [])),
            unsupported_abilities=tuple(raw.get("unsupported_abilities", [])),
            raw_lorcanito_source=dict(raw.get("raw_lorcanito_source", {})),
            source_mapping_status=str(raw.get("source_mapping_status", "unknown")),
            source_execution_status=str(raw.get("source_execution_status", "unknown")),
            text_effects=text_effects,
            images=dict(raw.get("images", {})),
            external_links=dict(raw.get("external_links", {})),
            allowed_in_formats=dict(raw.get("allowed_in_formats", {})),
            allowed_in_tournaments_from_date=raw.get("allowed_in_tournaments_from_date"),
            reprint_of_id=str(raw["reprint_of_id"]) if raw.get("reprint_of_id") is not None else None,
            base_id=str(raw["base_id"]) if raw.get("base_id") is not None else None,
            max_copies_in_deck=raw.get("max_copies_in_deck"),
            has_max_copies_override=bool(raw.get("has_max_copies_override", "max_copies_in_deck" in raw)),
            raw=dict(raw.get("raw", {})),
        )

    @classmethod
    def from_official_card(cls, raw: dict, set_metadata: dict) -> "CardDef":
        colors = _normalize_colors(raw)
        card_type = _normalize_card_type(raw["type"])
        keywords = _normalize_keywords(raw)
        return cls(
            id=str(raw["id"]),
            full_name=raw["fullName"],
            ink=colors[0] if colors else "",
            cost=int(raw["cost"]),
            inkable=bool(raw["inkwell"]),
            card_type=card_type,
            strength=raw.get("strength"),
            willpower=raw.get("willpower"),
            lore=raw.get("lore"),
            keywords=keywords,
            effects=(),
            move_cost=raw.get("moveCost"),
            version=str(raw.get("version") or ""),
            colors=colors,
            name=raw.get("name"),
            simple_name=raw.get("simpleName"),
            subtypes=tuple(raw.get("subtypes", [])),
            rarity=_normalize_rarity(raw.get("rarity")),
            set_code=str(set_metadata.get("code") or raw.get("code") or ""),
            set_name=set_metadata.get("name"),
            collector_number=str(raw.get("number") or ""),
            full_identifier=raw.get("fullIdentifier"),
            rules_text=raw.get("fullText"),
            flavor_text=raw.get("flavorText"),
            abilities=tuple(raw.get("abilities", [])),
            keyword_defs=(),
            activated_abilities=tuple(),
            triggers=tuple(),
            unsupported_abilities=tuple(_unsupported_ability_records(raw)),
            raw_lorcanito_source={},
            source_mapping_status="unknown",
            source_execution_status="unknown",
            text_effects=tuple(str(effect) for effect in raw.get("effects", [])),
            images=dict(raw.get("images", {})),
            external_links=dict(raw.get("externalLinks", {})),
            allowed_in_formats=dict(raw.get("allowedInFormats", {})),
            allowed_in_tournaments_from_date=raw.get("allowedInTournamentsFromDate"),
            reprint_of_id=str(raw["reprintOfId"]) if raw.get("reprintOfId") is not None else None,
            base_id=str(raw["baseId"]) if raw.get("baseId") is not None else None,
            max_copies_in_deck=raw.get("maxCopiesInDeck"),
            has_max_copies_override="maxCopiesInDeck" in raw,
            raw=dict(raw),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "full_name": self.full_name,
            "ink": self.ink,
            "cost": self.cost,
            "inkable": self.inkable,
            "card_type": self.card_type,
            "strength": self.strength,
            "willpower": self.willpower,
            "lore": self.lore,
            "keywords": list(self.keywords),
            "effects": [effect.to_dict() for effect in self.effects],
            "move_cost": self.move_cost,
            "version": self.version,
            "colors": list(self.colors),
            "name": self.name,
            "simple_name": self.simple_name,
            "subtypes": list(self.subtypes),
            "rarity": self.rarity,
            "set_code": self.set_code,
            "set_name": self.set_name,
            "collector_number": self.collector_number,
            "full_identifier": self.full_identifier,
            "rules_text": self.rules_text,
            "flavor_text": self.flavor_text,
            "abilities": list(self.abilities),
            "keyword_defs": [keyword.to_dict() for keyword in self.keyword_defs],
            "activated_abilities": [ability.to_dict() for ability in self.activated_abilities],
            "triggers": [trigger.to_dict() for trigger in self.triggers],
            "unsupported_abilities": list(self.unsupported_abilities),
            "source_abilities": [asdict(ability) for ability in self.source_abilities],
            "source_effects": [asdict(effect) for effect in self.source_effects],
            "source_triggers": [asdict(trigger) for trigger in self.source_triggers],
            "source_static_abilities": [asdict(effect) for effect in self.source_static_abilities],
            "source_replacement_abilities": [asdict(effect) for effect in self.source_replacement_abilities],
            "raw_lorcanito_source": self.raw_lorcanito_source,
            "source_mapping_status": self.source_mapping_status,
            "source_execution_status": self.source_execution_status,
            "text_effects": list(self.text_effects),
            "images": self.images,
            "external_links": self.external_links,
            "allowed_in_formats": self.allowed_in_formats,
            "allowed_in_tournaments_from_date": self.allowed_in_tournaments_from_date,
            "reprint_of_id": self.reprint_of_id,
            "base_id": self.base_id,
            "max_copies_in_deck": self.max_copies_in_deck,
            "has_max_copies_override": self.has_max_copies_override,
            "raw": self.raw,
        }

    @property
    def deck_building_id(self) -> str:
        """Identity used for constructed copy limits across reprints/variants."""

        return self.full_name.casefold()

    def is_allowed_in_format(self, format_name: str) -> bool | None:
        entry = self.allowed_in_formats.get(format_name)
        if entry is None:
            return None
        if isinstance(entry, dict):
            allowed = entry.get("allowed")
            return bool(allowed) if allowed is not None else None
        return bool(entry)


@dataclass(frozen=True, slots=True)
class FormatRules:
    name: str = FORMAT_CORE_CONSTRUCTED
    min_cards: int = 60
    max_copies_by_full_name: int = 4
    max_inks: int = 2
    banned_full_names: frozenset[str] = field(default_factory=frozenset)
    banned_card_ids: frozenset[str] = field(default_factory=frozenset)
    format_name: str = "Core"
    require_format_legal: bool = True


class CardDatabase:
    def __init__(self, cards: Iterable[CardDef]):
        card_list = list(cards)
        self._cards_by_id = {card.id: card for card in card_list}
        if len(self._cards_by_id) != len(card_list):
            raise ValueError("Card ids must be unique in this database")
        self._cards_by_name: dict[str, list[CardDef]] = {}
        for card in self._cards_by_id.values():
            self._cards_by_name.setdefault(card.full_name, []).append(card)

    def __len__(self) -> int:
        return len(self._cards_by_id)

    def get(self, card_id_or_name: str | int) -> CardDef:
        key = str(card_id_or_name)
        if key in self._cards_by_id:
            return self._cards_by_id[key]
        matches = self._cards_by_name.get(key)
        if matches:
            if len(matches) > 1:
                ids = ", ".join(card.id for card in matches[:8])
                raise KeyError(f"Ambiguous card name {key!r}; use a card id. Matching ids: {ids}")
            return matches[0]
        raise KeyError(f"Unknown card {card_id_or_name!r}")

    def find_by_full_name(self, full_name: str) -> list[CardDef]:
        return list(self._cards_by_name.get(full_name, []))

    def all_cards(self) -> list[CardDef]:
        return list(self._cards_by_id.values())

    def save_json(self, path: str | Path) -> None:
        raw = [card.to_dict() for card in self.all_cards()]
        Path(path).write_text(json.dumps(raw, indent=2, sort_keys=True), encoding="utf-8")

    @classmethod
    def load_json(cls, path: str | Path) -> "CardDatabase":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(CardDef.from_dict(item) for item in raw)


def validate_deck(deck: Iterable[str], db: CardDatabase, rules: FormatRules | None = None) -> list[str]:
    """Return validation errors for a Core Constructed decklist.

    The input may contain card ids or full names. Validation uses full card
    names for copy limits, matching the physical TCG deck-construction model.
    """

    rules = rules or FormatRules()
    resolved = [db.get(card) for card in deck]
    errors: list[str] = []

    if len(resolved) < rules.min_cards:
        errors.append(f"Deck has {len(resolved)} cards; minimum is {rules.min_cards}")

    inks = {color for card in resolved for color in card.colors}
    if len(inks) > rules.max_inks:
        errors.append(f"Deck uses {len(inks)} inks {sorted(inks)}; maximum is {rules.max_inks}")

    cards_by_deck_id: dict[str, CardDef] = {}
    counts = Counter(card.deck_building_id for card in resolved)
    for card in resolved:
        cards_by_deck_id.setdefault(card.deck_building_id, card)
    for deck_building_id, count in sorted(counts.items()):
        card = cards_by_deck_id[deck_building_id]
        max_copies = None if card.has_max_copies_override else rules.max_copies_by_full_name
        if card.has_max_copies_override and card.max_copies_in_deck is not None:
            max_copies = card.max_copies_in_deck
        if max_copies is None:
            continue
        if count > max_copies:
            errors.append(f"Deck has {count} copies of {card.full_name}; maximum is {max_copies}")

    for card in resolved:
        if card.full_name in rules.banned_full_names or card.id in rules.banned_card_ids:
            errors.append(f"{card.full_name} is banned in {rules.name}")
        allowed = card.is_allowed_in_format(rules.format_name)
        if rules.require_format_legal and allowed is False:
            errors.append(f"{card.full_name} is not legal in {rules.format_name}")

    return errors


def load_official_database(path: str | Path = "data/cards") -> CardDatabase:
    """Load user-provided official-style set JSON files.

    Files are expected to use the observed `setdata.*.json` shape: a set-level
    metadata object containing a `cards` list with card catalog entries.
    """

    from .importers.lorcanito_importer import load_lorcanito_database

    return load_lorcanito_database(path)


def load_card_database(source: str | Path = "demo", *, card_data_path: str | Path = "data/cards") -> CardDatabase:
    """Load either the fast demo database or the imported card database."""

    source_text = str(source)
    if source_text == "demo":
        return load_demo_database()
    if source_text in {"official", "lorcanito", "imported"}:
        return load_official_database(card_data_path)
    return CardDatabase.load_json(source)


def _normalize_colors(raw: dict) -> tuple[str, ...]:
    raw_colors = raw.get("colors")
    if isinstance(raw_colors, list) and raw_colors:
        values = raw_colors
    elif raw.get("color"):
        values = str(raw["color"]).split("-")
    else:
        values = []
    return tuple(value.strip().lower() for value in values if value.strip())


def _normalize_card_type(value: str) -> str:
    key = value.strip().lower()
    try:
        return _CARD_TYPE_MAP[key]
    except KeyError as exc:
        raise ValueError(f"Unsupported official card type {value!r}") from exc


def _normalize_keywords(raw: dict) -> tuple[str, ...]:
    keywords: set[str] = set()
    for keyword in raw.get("keywordAbilities", []):
        keywords.add(_keyword_constant(keyword))
    for ability in raw.get("abilities", []):
        keyword = ability.get("keyword")
        if keyword:
            keywords.add(_keyword_constant(keyword))
    return tuple(sorted(keywords))


def _keyword_constant(keyword: str) -> str:
    return keyword.strip().upper().replace(" ", "_")


def _normalize_rarity(value: str | None) -> str | None:
    if value is None:
        return None
    return _RARITY_MAP.get(value.strip().lower(), value.strip().lower().replace(" ", "_"))


def _unsupported_ability_records(raw: dict) -> tuple[dict[str, Any], ...]:
    records: list[dict[str, Any]] = []
    for ability in raw.get("abilities", []):
        if not isinstance(ability, dict):
            records.append({"source": "ability", "reason": "non_object_ability", "raw": ability})
            continue
        if ability.get("type") == "keyword":
            continue
        records.append(
            {
                "source": "ability",
                "type": ability.get("type"),
                "name": ability.get("name"),
                "effect": ability.get("effect"),
                "full_text": ability.get("fullText"),
                "raw": dict(ability),
            }
        )
    for effect in raw.get("effects", []):
        records.append({"source": "effects", "type": "text", "effect": str(effect), "full_text": str(effect), "raw": effect})
    return tuple(records)


DEMO_FEATURE_CARD_IDS: dict[str, str] = {
    "basic_character": "amber_recruit",
    "bodyguard_character": "amber_guard",
    "evasive_character": "emerald_scout",
    "rush_character": "ruby_charger",
    "ward_character": "demo_ward_sentinel",
    "challenger_character": "demo_challenger",
    "resist_character": "demo_resist_wall",
    "singer_character": "demo_singer",
    "item": "demo_item",
    "location": "demo_location",
    "action": "steel_cannon",
    "song": "demo_song",
    "target_character_action": "demo_target_character_action",
    "target_item_action": "demo_target_item_action",
    "target_location_action": "demo_target_location_action",
    "target_player_action": "demo_target_player_action",
    "target_damaged_action": "demo_target_damaged_action",
    "fixed_opponent_action": "demo_fixed_opponent_action",
    "shift_base": "demo_shift_base",
    "shift_same_name": "demo_shift_same_name",
    "shift_classification_base": "demo_shift_sorcerer_base",
    "shift_classification": "demo_shift_sorcerer",
    "shift_universal": "demo_shift_universal",
    "shift_non_ink_cost": "demo_shift_discard_cost",
}


def load_demo_database() -> CardDatabase:
    """Small non-official card pool for engine tests and bot smoke runs.

    It intentionally avoids copyrighted card text. Replace with a licensed or
    user-provided card database for full production play.

    The pool also contains a curated feature subset for migration tests. These
    cards are synthetic, stable, and deliberately cover target filtering,
    locations, items, songs, keywords, and Shift modes without requiring every
    unit test to load the full imported Lorcanito card database.
    """

    cards = [
        CardDef("amber_recruit", "Amber Recruit", "amber", 1, True, "character", 1, 2, 1),
        CardDef("amber_guard", "Amber Guard", "amber", 2, True, "character", 1, 4, 1, keywords=("BODYGUARD",)),
        CardDef("amber_storyteller", "Amber Storyteller", "amber", 3, True, "character", 1, 3, 3),
        CardDef("amethyst_scholar", "Amethyst Scholar", "amethyst", 2, True, "character", 1, 3, 2),
        CardDef("emerald_scout", "Emerald Scout", "emerald", 2, True, "character", 2, 2, 1, keywords=("EVASIVE",)),
        CardDef("ruby_charger", "Ruby Charger", "ruby", 3, True, "character", 3, 2, 1, keywords=("RUSH",)),
        CardDef("sapphire_helper", "Sapphire Helper", "sapphire", 1, True, "character", 1, 1, 1),
        CardDef("steel_bruiser", "Steel Bruiser", "steel", 2, True, "character", 3, 3, 1),
        CardDef("steel_cannon", "Steel Cannon", "steel", 2, True, "action", effects=(EffectDef("deal_damage", 2, "opposing_character"),)),
        CardDef("amethyst_insight", "Amethyst Insight", "amethyst", 2, True, "action", effects=(EffectDef("draw", 2),)),
        CardDef("ruby_lore_burst", "Ruby Lore Burst", "ruby", 4, False, "action", effects=(EffectDef("gain_lore", 2),)),
        CardDef("demo_ward_sentinel", "Demo Ward Sentinel", "emerald", 2, True, "character", 1, 3, 1, keywords=("WARD",)),
        CardDef("demo_challenger", "Demo Challenger", "ruby", 3, True, "character", 2, 3, 1, keywords=("CHALLENGER",)),
        CardDef("demo_resist_wall", "Demo Resist Wall", "steel", 3, True, "character", 1, 5, 1, keywords=("RESIST:2",)),
        CardDef("demo_singer", "Demo Singer", "amber", 3, True, "character", 1, 3, 1, keywords=("SINGER",)),
        CardDef("demo_item", "Demo Item", "sapphire", 1, True, "item"),
        CardDef("demo_location", "Demo Location", "amber", 2, True, "location", willpower=5, lore=1, move_cost=1),
        CardDef(
            "demo_song",
            "Demo Song",
            "amethyst",
            2,
            True,
            "action",
            effects=(EffectDef("draw", 1),),
            action_subtype="song",
            subtypes=("Song",),
        ),
        CardDef(
            "demo_target_character_action",
            "Demo Target Character Action",
            "steel",
            1,
            True,
            "action",
            effects=(EffectDef("deal_damage", 1, "chosen_character"),),
        ),
        CardDef(
            "demo_target_item_action",
            "Demo Target Item Action",
            "sapphire",
            1,
            True,
            "action",
            effects=(EffectDef("ready", target="chosen_item"),),
        ),
        CardDef(
            "demo_target_location_action",
            "Demo Target Location Action",
            "amber",
            1,
            True,
            "action",
            effects=(EffectDef("ready", target="chosen_location"),),
        ),
        CardDef(
            "demo_target_player_action",
            "Demo Target Player Action",
            "emerald",
            1,
            True,
            "action",
            effects=(EffectDef("gain_lore", 1, "chosen_player"),),
        ),
        CardDef(
            "demo_target_damaged_action",
            "Demo Target Damaged Action",
            "ruby",
            1,
            True,
            "action",
            effects=(EffectDef("remove_damage", 1, "chosen_damaged_character"),),
        ),
        CardDef(
            "demo_fixed_opponent_action",
            "Demo Fixed Opponent Action",
            "emerald",
            1,
            True,
            "action",
            effects=(EffectDef("lose_lore", 1, "opponent"),),
        ),
        CardDef(
            "demo_shift_base",
            "Demo Hero - Original",
            "amber",
            2,
            True,
            "character",
            1,
            3,
            1,
            name="Demo Hero",
            simple_name="Demo Hero",
            subtypes=("Storyborn", "Hero"),
        ),
        CardDef(
            "demo_shift_same_name",
            "Demo Hero - Shifted",
            "amber",
            5,
            True,
            "character",
            3,
            5,
            2,
            keywords=("SHIFT:2",),
            name="Demo Hero",
            simple_name="Demo Hero",
            subtypes=("Floodborn", "Hero"),
            rules_text="Shift 2. You may play this on top of one of your characters named Demo Hero.",
        ),
        CardDef(
            "demo_shift_sorcerer_base",
            "Demo Sorcerer - Apprentice",
            "amethyst",
            2,
            True,
            "character",
            1,
            3,
            1,
            name="Demo Sorcerer",
            simple_name="Demo Sorcerer",
            subtypes=("Storyborn", "Sorcerer"),
        ),
        CardDef(
            "demo_shift_sorcerer",
            "Demo Archmage - Shifted",
            "amethyst",
            6,
            True,
            "character",
            4,
            5,
            2,
            keywords=("SORCERER SHIFT:3",),
            name="Demo Archmage",
            simple_name="Demo Archmage",
            subtypes=("Floodborn", "Sorcerer"),
            rules_text="Sorcerer Shift 3. You may play this on top of one of your Sorcerer characters.",
        ),
        CardDef(
            "demo_shift_universal",
            "Demo Universal Shifter",
            "steel",
            6,
            True,
            "character",
            4,
            5,
            2,
            keywords=("UNIVERSAL SHIFT:3",),
            subtypes=("Floodborn",),
            rules_text="Universal Shift 3. You may play this on top of any one of your characters.",
        ),
        CardDef(
            "demo_shift_discard_cost",
            "Demo Discard Shifter",
            "ruby",
            5,
            True,
            "character",
            3,
            4,
            1,
            keywords=("SHIFT",),
            abilities=(
                {
                    "type": "keyword",
                    "keyword": "shift",
                    "text": "Shift by discarding a card.",
                    "cost": {"discardCards": 1},
                },
            ),
            rules_text="Shift by discarding a card.",
        ),
    ]
    return CardDatabase(cards)


def make_demo_deck(card_names: list[str] | None = None, size: int = 60) -> list[str]:
    names = card_names or [
        "Amber Recruit",
        "Amber Guard",
        "Amber Storyteller",
        "Amethyst Scholar",
        "Amethyst Insight",
    ]
    deck: list[str] = []
    while len(deck) < size:
        deck.extend(names)
    return deck[:size]
