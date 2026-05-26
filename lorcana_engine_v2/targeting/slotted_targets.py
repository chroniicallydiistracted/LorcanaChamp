from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


SLOTTED_TARGET_KINDS = ("move-to-location",)
SLOTTED_TARGET_SLOT_KEYS = {"move-to-location": ("subject", "location")}


def is_slotted_target_input(value: object) -> bool:
    return (
        isinstance(value, Mapping)
        and isinstance(value.get("kind"), str)
        and value.get("kind") in SLOTTED_TARGET_KINDS
    )


def flatten_slotted_targets(value: object) -> tuple[str, ...]:
    if not is_slotted_target_input(value):
        return ()
    result: list[str] = []
    kind = str(value["kind"])  # type: ignore[index]
    for key in SLOTTED_TARGET_SLOT_KEYS.get(kind, ()):
        slot = value.get(key)  # type: ignore[union-attr]
        if isinstance(slot, str) and slot:
            result.append(slot)
        elif isinstance(slot, Sequence) and not isinstance(slot, (str, bytes, bytearray)):
            result.extend(str(item) for item in slot if isinstance(item, str) and item)
    return tuple(result)


def slot_keys_for(kind: str) -> tuple[str, ...]:
    return tuple(SLOTTED_TARGET_SLOT_KEYS.get(kind, ()))


isSlottedTargetInput = is_slotted_target_input
flattenSlottedTargets = flatten_slotted_targets


__all__ = [
    "SLOTTED_TARGET_KINDS",
    "SLOTTED_TARGET_SLOT_KEYS",
    "flattenSlottedTargets",
    "flatten_slotted_targets",
    "isSlottedTargetInput",
    "is_slotted_target_input",
    "slot_keys_for",
]
