from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .conditions import SourceConditionDef
from .mapping_status import ExecutionStatus, MappingStatus
from .targets import SourceTargetDef


@dataclass(frozen=True)
class SourceEffectDef:
    kind: str
    amount: Any | None = None
    target: SourceTargetDef | None = None
    duration: Any | None = None
    condition: SourceConditionDef | None = None
    effects: tuple["SourceEffectDef", ...] = ()
    branches: tuple["SourceEffectDef", ...] = ()
    choice: Any | None = None
    optional: bool | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    mapping_status: str = MappingStatus.UNKNOWN
    execution_status: str = ExecutionStatus.UNKNOWN

