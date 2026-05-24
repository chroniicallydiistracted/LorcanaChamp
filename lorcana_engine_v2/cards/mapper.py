"""Source-to-runtime mapper boundary.

The scaffold keeps the mapper thin. Future work should convert SourceAbility and
SourceEffect objects into typed runtime specs used by v2 rules/effect services.
This module must not import legacy v1 mapper code.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import SourceAbility


@dataclass(frozen=True, slots=True)
class MappingDecision:
    executable: bool
    reason: str | None = None


def classify_source_ability_for_v2(ability: SourceAbility) -> MappingDecision:
    if ability.kind in {"keyword", "static", "triggered", "activated", "action", "replacement"}:
        return MappingDecision(executable=False, reason="v2_mapper_not_implemented")
    return MappingDecision(executable=False, reason=f"unknown_ability:{ability.kind}")
