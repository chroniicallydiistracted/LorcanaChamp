from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .mapping_status import ExecutionStatus, MappingStatus


@dataclass(frozen=True)
class SourceTriggerDef:
    event: str
    on: str | None = None
    timing: str | None = None
    subject: Any | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    mapping_status: str = MappingStatus.UNKNOWN
    execution_status: str = ExecutionStatus.UNKNOWN

