from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .conditions import SourceConditionDef
from .effects import SourceEffectDef
from .mapping_status import ExecutionStatus, MappingStatus


@dataclass(frozen=True)
class SourceReplacementEffectDef:
    replaces: Any
    condition: SourceConditionDef | None = None
    replacement: SourceEffectDef | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    mapping_status: str = MappingStatus.UNKNOWN
    execution_status: str = ExecutionStatus.UNKNOWN

