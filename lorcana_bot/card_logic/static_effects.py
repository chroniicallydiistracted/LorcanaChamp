from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .conditions import SourceConditionDef
from .effects import SourceEffectDef
from .mapping_status import ExecutionStatus, MappingStatus
from .targets import SourceTargetDef


@dataclass(frozen=True)
class SourceStaticEffectDef:
    kind: str
    target: SourceTargetDef | None = None
    condition: SourceConditionDef | None = None
    effect: SourceEffectDef | None = None
    source_zones: tuple[str, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)
    mapping_status: str = MappingStatus.UNKNOWN
    execution_status: str = ExecutionStatus.UNKNOWN

