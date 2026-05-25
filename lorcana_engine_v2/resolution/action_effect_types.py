from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from lorcana_engine_v2.core.ids import InstanceId, PlayerId


def _clone_mapping(value: Mapping[str, object] | None) -> dict[str, object]:
    if value is None:
        return {}
    cloned: dict[str, object] = {}
    for key, item in value.items():
        if isinstance(item, Mapping):
            cloned[str(key)] = _clone_mapping(item)
        elif isinstance(item, list):
            cloned[str(key)] = tuple(item)
        else:
            cloned[str(key)] = item
    return cloned


def _clone_card_played(value: Mapping[str, object] | None) -> dict[str, object]:
    cloned = _clone_mapping(value)
    if "singerIds" in cloned and isinstance(cloned["singerIds"], list):
        cloned["singerIds"] = tuple(cloned["singerIds"])
    return cloned


@dataclass(frozen=True, slots=True)
class ActionResolutionInput:
    targets: object | None = None
    slottedTargets: object | None = None
    currentTargets: object | None = None
    contextTargets: object | None = None
    targetSelectionResolved: bool | None = None
    amount: object | None = None
    namedCard: str | None = None
    resolveOptional: bool | None = None
    enterPlayExerted: bool | None = None
    choiceIndex: int | None = None
    preventAutoResolveTriggeredEffects: bool | None = None
    destinations: tuple[object, ...] | None = None
    eventSnapshot: Mapping[str, object] = field(default_factory=dict)
    triggerContext: Mapping[str, object] = field(default_factory=dict)
    chooserPlayerId: PlayerId | None = None

    @classmethod
    def from_value(cls, value: object | None) -> "ActionResolutionInput":
        if isinstance(value, ActionResolutionInput):
            return value.clone()
        if not isinstance(value, Mapping):
            return cls()
        destinations = value.get("destinations")
        return cls(
            targets=value.get("targets"),
            slottedTargets=value.get("slottedTargets"),
            currentTargets=value.get("currentTargets"),
            contextTargets=value.get("contextTargets"),
            targetSelectionResolved=(
                bool(value["targetSelectionResolved"])
                if value.get("targetSelectionResolved") is not None
                else None
            ),
            amount=value.get("amount"),
            namedCard=str(value["namedCard"]).strip()
            if value.get("namedCard") is not None and str(value["namedCard"]).strip()
            else None,
            resolveOptional=(
                bool(value["resolveOptional"])
                if value.get("resolveOptional") is not None
                else None
            ),
            enterPlayExerted=(
                bool(value["enterPlayExerted"])
                if value.get("enterPlayExerted") is not None
                else None
            ),
            choiceIndex=int(value["choiceIndex"])
            if isinstance(value.get("choiceIndex"), int)
            else None,
            preventAutoResolveTriggeredEffects=(
                bool(value["preventAutoResolveTriggeredEffects"])
                if value.get("preventAutoResolveTriggeredEffects") is not None
                else None
            ),
            destinations=tuple(destinations) if isinstance(destinations, (list, tuple)) else None,
            eventSnapshot=_clone_mapping(value.get("eventSnapshot") if isinstance(value.get("eventSnapshot"), Mapping) else None),
            triggerContext=_clone_mapping(value.get("triggerContext") if isinstance(value.get("triggerContext"), Mapping) else None),
            chooserPlayerId=PlayerId(str(value["chooserPlayerId"]))
            if value.get("chooserPlayerId") is not None
            else None,
        )

    def clone(self) -> "ActionResolutionInput":
        return replace(
            self,
            destinations=tuple(self.destinations) if self.destinations is not None else None,
            eventSnapshot=_clone_mapping(self.eventSnapshot),
            triggerContext=_clone_mapping(self.triggerContext),
        )

    def to_mapping(self) -> dict[str, object]:
        result: dict[str, object] = {}
        for key in (
            "targets",
            "slottedTargets",
            "currentTargets",
            "contextTargets",
            "targetSelectionResolved",
            "amount",
            "namedCard",
            "resolveOptional",
            "enterPlayExerted",
            "choiceIndex",
            "preventAutoResolveTriggeredEffects",
            "destinations",
            "chooserPlayerId",
        ):
            value = getattr(self, key)
            if value is not None:
                result[key] = value
        if self.eventSnapshot:
            result["eventSnapshot"] = dict(self.eventSnapshot)
        if self.triggerContext:
            result["triggerContext"] = dict(self.triggerContext)
        return result

    def merge(self, patch: object | None) -> "ActionResolutionInput":
        merged = self.to_mapping()
        patch_input = ActionResolutionInput.from_value(patch).to_mapping()
        merged.update(patch_input)
        return ActionResolutionInput.from_value(merged)


@dataclass(frozen=True, slots=True)
class PendingActionEffect:
    id: str
    type: str
    kind: str
    sourceId: InstanceId
    sourceCardId: InstanceId
    controllerId: PlayerId
    chooserId: PlayerId
    cardPlayed: Mapping[str, object]
    effect: object
    resolutionInput: ActionResolutionInput = field(default_factory=ActionResolutionInput)
    abilityIndex: int | None = None
    continuation: object | None = None
    selectionContext: object | None = None
    allowSuspendWithZeroTargetCandidates: bool = False

    @classmethod
    def create(
        cls,
        *,
        id: str,
        kind: str,
        sourceCardId: InstanceId | str,
        controllerId: PlayerId | str,
        chooserId: PlayerId | str,
        cardPlayed: Mapping[str, object] | None,
        effect: object,
        resolutionInput: object | None = None,
        abilityIndex: int | None = None,
        continuation: object | None = None,
        selectionContext: object | None = None,
        allowSuspendWithZeroTargetCandidates: bool = False,
    ) -> "PendingActionEffect":
        source_id = InstanceId(str(sourceCardId))
        return cls(
            id=id,
            type="action-effect",
            kind=str(kind),
            sourceId=source_id,
            sourceCardId=source_id,
            controllerId=PlayerId(str(controllerId)),
            chooserId=PlayerId(str(chooserId)),
            cardPlayed=_clone_card_played(cardPlayed),
            effect=effect,
            resolutionInput=ActionResolutionInput.from_value(resolutionInput),
            abilityIndex=abilityIndex,
            continuation=continuation,
            selectionContext=selectionContext,
            allowSuspendWithZeroTargetCandidates=allowSuspendWithZeroTargetCandidates,
        )


@dataclass(frozen=True, slots=True)
class BagItem:
    id: str
    type: str
    kind: str
    abilityId: str
    abilityKey: str
    controllerId: PlayerId
    chooserId: PlayerId
    sourceId: InstanceId
    cardPlayed: Mapping[str, object]
    trigger: Mapping[str, object]
    effect: object
    occurrenceIndex: int
    resolutionInput: ActionResolutionInput = field(default_factory=ActionResolutionInput)
    abilityIndex: int | None = None
    abilityName: str | None = None
    condition: object | None = None
    autoResolve: bool = False

    @classmethod
    def create(
        cls,
        *,
        id: str,
        kind: str = "triggered-ability",
        abilityId: str,
        abilityKey: str,
        controllerId: PlayerId | str,
        chooserId: PlayerId | str | None = None,
        sourceId: InstanceId | str,
        cardPlayed: Mapping[str, object] | None,
        trigger: Mapping[str, object],
        effect: object,
        occurrenceIndex: int,
        resolutionInput: object | None = None,
        abilityIndex: int | None = None,
        abilityName: str | None = None,
        condition: object | None = None,
        autoResolve: bool = False,
    ) -> "BagItem":
        controller = PlayerId(str(controllerId))
        return cls(
            id=id,
            type="bag-effect",
            kind=kind,
            abilityId=str(abilityId),
            abilityKey=str(abilityKey),
            controllerId=controller,
            chooserId=PlayerId(str(chooserId)) if chooserId is not None else controller,
            sourceId=InstanceId(str(sourceId)),
            cardPlayed=_clone_card_played(cardPlayed),
            trigger=dict(trigger),
            effect=effect,
            occurrenceIndex=int(occurrenceIndex),
            resolutionInput=ActionResolutionInput.from_value(resolutionInput),
            abilityIndex=abilityIndex,
            abilityName=abilityName,
            condition=condition,
            autoResolve=autoResolve,
        )


@dataclass(frozen=True, slots=True)
class PendingResolutionResult:
    status: str
    state: object
    pendingEffect: PendingActionEffect | None = None
    bagItem: BagItem | None = None
    resolutionInput: ActionResolutionInput = field(default_factory=ActionResolutionInput)


def clone_action_resolution_input(value: object | None) -> ActionResolutionInput:
    return ActionResolutionInput.from_value(value)


__all__ = [
    "ActionResolutionInput",
    "BagItem",
    "PendingActionEffect",
    "PendingResolutionResult",
    "clone_action_resolution_input",
]
