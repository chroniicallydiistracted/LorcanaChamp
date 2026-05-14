from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .mapping_status import ExecutionStatus, MappingStatus
from .targets import SourceTargetDef


@dataclass(frozen=True)
class SourceCostDef:
    kind: str
    amount: int | str | None = None
    selector: SourceTargetDef | None = None
    components: tuple["SourceCostDef", ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)
    mapping_status: str = MappingStatus.UNKNOWN
    execution_status: str = ExecutionStatus.UNKNOWN

