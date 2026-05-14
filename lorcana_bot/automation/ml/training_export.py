from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from ..decision_trace import AutomatedDecisionTrace


def trace_to_training_row(trace: AutomatedDecisionTrace, state_features: list[float] | None = None) -> dict:
    selected_key = trace.selected_candidate["stable_key"] if trace.selected_candidate else None
    candidates = []
    for raw in trace.ordered_candidates:
        candidates.append(
            {
                "stable_key": raw["stable_key"],
                "family": raw["family"],
                "candidate_features": [],
                "score": raw["score"],
                "rank": raw["rank"],
                "selected": raw["stable_key"] == selected_key,
            }
        )
    return {
        "schema_version": 1,
        "trace_id": trace.trace_id,
        "strategy_name": trace.strategy_name,
        "information_policy": trace.information_policy,
        "state_fingerprint": trace.state_fingerprint,
        "actor": trace.actor,
        "turn_number": trace.turn_number,
        "phase": trace.phase,
        "state_features": state_features or [],
        "candidates": candidates,
        "selected_stable_key": selected_key,
        "winner": None,
    }


def export_training_rows(rows: Iterable[dict], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
