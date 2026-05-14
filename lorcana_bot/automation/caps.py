from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AutomationSearchCaps:
    target_pool: int = 8
    target_combinations_per_family: int = 16
    choice_indices: int = 8
    singer_combinations: int = 16
    max_execution_failures: int = 3
    max_candidates_per_family: int = 128
