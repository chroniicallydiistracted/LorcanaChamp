from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .conditions import SourceConditionDef
from .costs import SourceCostDef
from .effects import SourceEffectDef
from .mapping_status import ExecutionStatus, MappingStatus
from .triggers import SourceTriggerDef


class AbilityKind:
    KEYWORD = "keyword"
    ACTION = "action"
    TRIGGERED = "triggered"
    ACTIVATED = "activated"
    STATIC = "static"
    REPLACEMENT = "replacement"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SourceAbilityDef:
    id: str
    kind: str
    name: str | None = None
    text: str | None = None
    effects: tuple[SourceEffectDef, ...] = ()
    trigger: SourceTriggerDef | None = None
    costs: tuple[SourceCostDef, ...] = ()
    condition: SourceConditionDef | None = None
    restrictions: tuple[Any, ...] = ()
    source_zones: tuple[str, ...] = ()
    auto_resolve: bool | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    mapping_status: str = MappingStatus.UNKNOWN
    execution_status: str = ExecutionStatus.UNKNOWN

