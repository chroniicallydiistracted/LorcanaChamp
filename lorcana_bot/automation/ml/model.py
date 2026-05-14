from __future__ import annotations

from typing import Protocol, Sequence

from ..candidates import AutomatedActionCandidate


class CandidateRanker(Protocol):
    def score_candidates(self, features: list[list[float]], candidates: Sequence[AutomatedActionCandidate]) -> list[float]:
        ...
