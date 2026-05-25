from __future__ import annotations

from lorcana_engine_v2.effects.triggered_abilities import (
    flush_triggered_events_to_bag,
    open_window,
    queue_triggered_event,
    record_event,
)


class FloatingTriggerRegistry:
    record_event = staticmethod(record_event)
    queue = staticmethod(queue_triggered_event)
    open_window = staticmethod(open_window)
    flush = staticmethod(flush_triggered_events_to_bag)


__all__ = [
    "FloatingTriggerRegistry",
    "flush_triggered_events_to_bag",
    "open_window",
    "queue_triggered_event",
    "record_event",
]
