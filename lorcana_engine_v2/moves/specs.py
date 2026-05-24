from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lorcana_engine_v2.core.ids import InstanceId, PlayerId


@dataclass(frozen=True, slots=True)
class MoveSpec:
    """A legal move candidate exposed by v2.

    This is v2's Python analogue to Lorcanito RuntimeLegalMove entries. It uses
    v2 string-branded IDs instead of the scaffold-era integer fields.
    """
    kind: str
    actor: PlayerId
    card: InstanceId | None = None
    target: InstanceId | None = None
    payload: dict[str, Any] = field(default_factory=dict)