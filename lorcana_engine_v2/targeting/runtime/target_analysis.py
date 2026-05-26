from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.core.results import RuntimeValidationResult
from lorcana_engine_v2.targeting.runtime.target_resolver import (
    resolve_candidate_targets,
    resolve_target_player_ids,
    target_allows_player_selection,
)
from lorcana_engine_v2.targeting.slotted_targets import flatten_slotted_targets, is_slotted_target_input


@dataclass(frozen=True, slots=True)
class TargetAnalysis:
    targetDsl: tuple[object, ...] = ()
    cardCandidates: tuple[InstanceId, ...] = ()
    playerCandidates: tuple[PlayerId, ...] = ()
    allowedZones: tuple[str, ...] = ("play",)
    minSelections: int = 0
    maxSelections: int = 0
    declaredMaxSelections: int | None = None
    requiresExplicitSelection: bool = False
    allowsDeferredResolutionWithoutInitialSelection: bool = False
    allowDuplicateTargets: bool = False


@dataclass(frozen=True, slots=True)
class NormalizedTargetSelection:
    cardIds: tuple[InstanceId, ...] = ()
    playerIds: tuple[PlayerId, ...] = ()


def _as_targets(value: object | None) -> tuple[str, ...]:
    if is_slotted_target_input(value):
        return flatten_slotted_targets(value)
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(str(item) for item in value if isinstance(item, str) and item)
    return ()


def _is_chosen_card_target(target: object) -> bool:
    if isinstance(target, str):
        return "CHOSEN" in target.upper() and "PLAYER" not in target.upper()
    return isinstance(target, Mapping) and target.get("selector") == "chosen"


def _target_signature(target: object) -> str:
    return repr(target)


def _nested_effects(record: Mapping[str, object]) -> tuple[object, ...]:
    nested: list[object] = []
    for key in ("effect", "then", "else", "ifTrue", "ifFalse", "trueEffect", "falseEffect"):
        if key in record:
            nested.append(record[key])
    for key in ("effects", "steps", "options", "choices"):
        value = record.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            nested.extend(value)
    return tuple(nested)


def _collect_explicit_targets(effect: object) -> tuple[object, ...]:
    if not isinstance(effect, Mapping):
        return ()
    collected: list[object] = []
    target = effect.get("target")
    if _is_chosen_card_target(target) or target_allows_player_selection(target):
        collected.append(target)
    for nested in _nested_effects(effect):
        collected.extend(_collect_explicit_targets(nested))
    deduped: list[object] = []
    seen: set[str] = set()
    for target in collected:
        signature = _target_signature(target)
        if signature in seen:
            continue
        seen.add(signature)
        deduped.append(target)
    return tuple(deduped)


def _descriptor_bounds(target: object, candidate_count: int) -> tuple[int, int, int]:
    if isinstance(target, Mapping):
        count = target.get("count")
        if isinstance(count, Mapping) and isinstance(count.get("upTo"), int):
            declared = max(0, int(count["upTo"]))
            return 0, min(declared, candidate_count), declared
        if isinstance(count, int):
            declared = max(0, count)
            return declared, min(declared, candidate_count), declared
    return 1, min(1, candidate_count), 1


def analyze_effect_targets(
    effect_or_ability: object,
    context,
    card_played: Mapping[str, object] | None = None,
    resolution_input: object | None = None,
    **_: object,
) -> TargetAnalysis:
    explicit_targets = _collect_explicit_targets(effect_or_ability)
    card_candidates: list[InstanceId] = []
    player_candidates: list[PlayerId] = []
    allowed_zones: set[str] = set()
    min_count = 0
    max_count = 0
    declared_max = 0
    for target in explicit_targets:
        if target_allows_player_selection(target):
            candidates = resolve_target_player_ids(context, card_played, target)
            for player_id in candidates:
                if player_id not in player_candidates:
                    player_candidates.append(player_id)
            d_min, d_max, d_declared = _descriptor_bounds(target, len(candidates))
        else:
            candidates = resolve_candidate_targets(context, card_played, target)
            for card_id in candidates:
                if card_id not in card_candidates:
                    card_candidates.append(card_id)
            d_min, d_max, d_declared = _descriptor_bounds(target, len(candidates))
            if isinstance(target, Mapping):
                zones = target.get("zones") or target.get("zone") or ("play",)
                if isinstance(zones, str):
                    allowed_zones.add(zones)
                elif isinstance(zones, Sequence):
                    allowed_zones.update(str(zone) for zone in zones)
            else:
                allowed_zones.add("play")
        min_count += d_min
        max_count += d_max
        declared_max += d_declared
    requires_explicit = bool(explicit_targets)
    return TargetAnalysis(
        targetDsl=explicit_targets,
        cardCandidates=tuple(card_candidates),
        playerCandidates=tuple(player_candidates),
        allowedZones=tuple(sorted(allowed_zones)) if allowed_zones else (),
        minSelections=min_count if requires_explicit else 0,
        maxSelections=max(1, max_count) if requires_explicit else 0,
        declaredMaxSelections=max(1, declared_max) if requires_explicit else 0,
        requiresExplicitSelection=requires_explicit,
        allowsDeferredResolutionWithoutInitialSelection=not requires_explicit,
        allowDuplicateTargets=len(explicit_targets) > 1 and not any(
            isinstance(target, Mapping) and target.get("requireDifferentTargets") is True
            for target in explicit_targets
        ),
    )


def validate_and_normalize_target_selection(
    targets: object,
    analysis: TargetAnalysis,
    context: object | None = None,
) -> RuntimeValidationResult | object:
    raw_targets = _as_targets(targets)
    card_candidates = set(analysis.cardCandidates)
    player_candidates = set(analysis.playerCandidates)
    card_ids: list[InstanceId] = []
    player_ids: list[PlayerId] = []
    if not analysis.allowDuplicateTargets and len(set(raw_targets)) != len(raw_targets):
        return RuntimeValidationResult.fail("Duplicate targets are not allowed", "DUPLICATE_TARGETS")
    for target in raw_targets:
        card_id = InstanceId(str(target))
        player_id = PlayerId(str(target))
        if card_id in card_candidates:
            card_ids.append(card_id)
        elif player_id in player_candidates:
            player_ids.append(player_id)
        else:
            return RuntimeValidationResult.fail(f"Target {target} is not a legal target", "INVALID_ACTION_TARGET")
    total = len(card_ids) + len(player_ids)
    if total < analysis.minSelections:
        return RuntimeValidationResult.fail("Too few targets selected", "TOO_FEW_TARGETS")
    if analysis.maxSelections >= 0 and total > analysis.maxSelections:
        return RuntimeValidationResult.fail("Too many targets selected", "TOO_MANY_TARGETS")
    return type(
        "TargetValidationSuccess",
        (),
        {"valid": True, "selection": NormalizedTargetSelection(tuple(card_ids), tuple(player_ids))},
    )()


def flatten_normalized_target_selection(selection: NormalizedTargetSelection) -> tuple[str, ...]:
    return tuple(str(item) for item in (*selection.cardIds, *selection.playerIds))


def analyze_target_selection_availability_from_analysis(
    effect_or_ability: object,
    analysis: TargetAnalysis,
) -> RuntimeValidationResult:
    if analysis.minSelections > 0 and len(analysis.cardCandidates) + len(analysis.playerCandidates) < analysis.minSelections:
        return RuntimeValidationResult.fail("No legal targets are available", "NO_VALID_TARGETS")
    return RuntimeValidationResult.ok()


analyzeEffectTargets = analyze_effect_targets
analyzeTargetSelectionAvailabilityFromAnalysis = analyze_target_selection_availability_from_analysis
flattenNormalizedTargetSelection = flatten_normalized_target_selection
validateAndNormalizeTargetSelection = validate_and_normalize_target_selection


__all__ = [
    "NormalizedTargetSelection",
    "TargetAnalysis",
    "analyzeEffectTargets",
    "analyzeTargetSelectionAvailabilityFromAnalysis",
    "analyze_effect_targets",
    "analyze_target_selection_availability_from_analysis",
    "flattenNormalizedTargetSelection",
    "flatten_normalized_target_selection",
    "validateAndNormalizeTargetSelection",
    "validate_and_normalize_target_selection",
]
