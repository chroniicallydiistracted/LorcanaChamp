from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .mapping_status import ExecutionStatus, MappingStatus


@dataclass(frozen=True)
class SourceTargetDef:
    kind: str
    alias: str | None = None
    selector: str | None = None
    count: int | str | None = None
    owner: str | None = None
    controller: str | None = None
    chooser: str | None = None
    zones: tuple[str, ...] = ()
    card_types: tuple[str, ...] = ()
    classifications: tuple[str, ...] = ()
    filters: tuple[Any, ...] = ()
    exclude_self: bool = False
    raw: dict[str, Any] = field(default_factory=dict)
    mapping_status: str = MappingStatus.UNKNOWN
    execution_status: str = ExecutionStatus.UNKNOWN

