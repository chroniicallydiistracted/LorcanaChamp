from __future__ import annotations

from collections.abc import Iterable

from .results import ProjectedLogEntry


def append_log(
    existing: tuple[ProjectedLogEntry, ...],
    entries: ProjectedLogEntry | Iterable[ProjectedLogEntry],
) -> tuple[ProjectedLogEntry, ...]:
    if isinstance(entries, ProjectedLogEntry):
        return existing + (entries,)
    return existing + tuple(entries)
