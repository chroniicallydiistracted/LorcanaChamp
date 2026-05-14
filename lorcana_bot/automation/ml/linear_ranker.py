from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from ..candidates import AutomatedActionCandidate


@dataclass
class LinearCandidateRanker:
    weights: list[float] = field(default_factory=list)
    bias: float = 0.0

    def score_candidates(self, features: list[list[float]], candidates: Sequence[AutomatedActionCandidate]) -> list[float]:
        if not features:
            return []
        weights = self.weights or [0.0] * len(features[0])
        return [self.bias + sum(w * x for w, x in zip(weights, row)) for row in features]

    def save_json(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps({"weights": self.weights, "bias": self.bias}, sort_keys=True, indent=2), encoding="utf-8")

    @classmethod
    def load_json(cls, path: str | Path) -> "LinearCandidateRanker":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(weights=[float(v) for v in raw.get("weights", [])], bias=float(raw.get("bias", 0.0)))
