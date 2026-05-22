from __future__ import annotations

from dataclasses import dataclass

from .effects import SourceEffectDef


@dataclass(frozen=True)
class ResolutionRequirementReport:
    requires_target: bool = False
    requires_optional: bool = False
    requires_choice: bool = False
    requires_named_card: bool = False
    requires_amount: bool = False
    requires_destination: bool = False
    requires_ordering: bool = False
    requires_opponent_choice: bool = False
    unsupported_requirements: tuple[str, ...] = ()


def analyze_resolution_requirements(effect: SourceEffectDef) -> ResolutionRequirementReport:
    values = {
        "requires_target": _requires_target(effect),
        "requires_optional": effect.kind == "optional" or bool(effect.optional),
        "requires_choice": effect.kind in {"choice", "or"},
        "requires_named_card": effect.kind == "name-a-card",
        "requires_amount": _has_amount_choice(effect),
        "requires_destination": _has_destination_choice(effect),
        "requires_ordering": effect.kind == "scry" or _has_ordering(effect),
        "requires_opponent_choice": _has_opponent_choice(effect),
    }
    unsupported = tuple(
        key.removeprefix("requires_")
        for key, required in values.items()
        if required and key not in {"requires_optional", "requires_choice", "requires_target"}
    )
    child_reports = [analyze_resolution_requirements(child) for child in (*effect.effects, *effect.branches)]
    for report in child_reports:
        for key in values:
            values[key] = values[key] or getattr(report, key)
        unsupported += report.unsupported_requirements
    return ResolutionRequirementReport(**values, unsupported_requirements=tuple(sorted(set(unsupported))))


def _requires_target(effect: SourceEffectDef) -> bool:
    if effect.target is None:
        return False
    return effect.target.alias in {
        "CHOSEN_CHARACTER",
        "CHOSEN_OPPOSING_CHARACTER",
        "CHOSEN_DAMAGED_CHARACTER",
        "CHOSEN_ITEM",
        "CHOSEN_LOCATION",
    } or effect.target.kind in {"chosen", "selector"}


def _has_amount_choice(effect: SourceEffectDef) -> bool:
    return isinstance(effect.amount, dict) and str(effect.amount.get("type", "")).endswith("choice")


def _has_destination_choice(effect: SourceEffectDef) -> bool:
    raw = effect.raw
    destinations = raw.get("destinations")
    return isinstance(destinations, list) and len(destinations) > 1 and any(item.get("remainder") for item in destinations if isinstance(item, dict))


def _has_ordering(effect: SourceEffectDef) -> bool:
    destinations = effect.raw.get("destinations")
    if not isinstance(destinations, list):
        return False
    return any(isinstance(item, dict) and item.get("ordering") == "player-choice" for item in destinations)


def _has_opponent_choice(effect: SourceEffectDef) -> bool:
    def walk(value) -> bool:
        if isinstance(value, dict):
            if str(value.get("chosenBy", value.get("chosen_by", ""))).casefold() == "opponent":
                return True
            if str(value.get("chooser", "")).casefold() in {"opponent", "opponents"}:
                return True
            return any(walk(child) for child in value.values())
        if isinstance(value, (list, tuple)):
            return any(walk(child) for child in value)
        return False

    return walk(effect.raw)
