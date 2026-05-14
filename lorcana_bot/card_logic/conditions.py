from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .mapping_status import ExecutionStatus, MappingStatus


@dataclass(frozen=True)
class SourceConditionDef:
    kind: str
    operands: tuple["SourceConditionDef", ...] = ()
    subject: Any | None = None
    comparison: Any | None = None
    value: Any | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    mapping_status: str = MappingStatus.UNKNOWN
    execution_status: str = ExecutionStatus.UNKNOWN

