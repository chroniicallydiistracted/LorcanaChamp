from __future__ import annotations

from collections.abc import Mapping, Sequence

from lorcana_engine_v2.core.ids import PlayerId
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.effects.triggered_abilities import (
    emit_triggered_lorcana_event,
    finalize_resolution_boundary,
    flush_triggered_events_to_bag,
    open_window,
    queue_triggered_event,
    record_event,
)
from lorcana_engine_v2.resolution.pending import has_any_pending_effects, validate_no_pending_effects


def emit_lorcana_event(
    target: MatchState | object,
    *,
    custom_type: str,
    data: Mapping[str, object],
    triggered_event: Mapping[str, object] | Sequence[Mapping[str, object]] | None = None,
) -> MatchState:
    return emit_triggered_lorcana_event(target, custom_type, data, triggered_event)


class EventPipelineService:
    emit = staticmethod(emit_lorcana_event)
    record_event = staticmethod(record_event)
    open_window = staticmethod(open_window)
    finalize_boundary = staticmethod(finalize_resolution_boundary)
    flush_to_bag = staticmethod(flush_triggered_events_to_bag)
    queue_triggered_event = staticmethod(queue_triggered_event)
    has_pending = staticmethod(has_any_pending_effects)
    validate_empty = staticmethod(validate_no_pending_effects)


__all__ = [
    "EventPipelineService",
    "emit_lorcana_event",
    "emit_triggered_lorcana_event",
    "finalize_resolution_boundary",
    "flush_triggered_events_to_bag",
    "open_window",
    "queue_triggered_event",
    "record_event",
]
