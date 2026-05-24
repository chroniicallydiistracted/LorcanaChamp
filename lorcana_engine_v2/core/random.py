from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, TypeVar

from .state import CtxRandom


T = TypeVar("T")

_WIDTH = 256
_CHUNKS = 6
_DIGITS = 52
_START_DENOM = float(_WIDTH**_CHUNKS)
_SIGNIFICANCE = float(2**_DIGITS)
_OVERFLOW = _SIGNIFICANCE * 2.0
_MASK = _WIDTH - 1


class _Arc4:
    def __init__(self, key: Sequence[int]) -> None:
        key_values = list(key)
        if not key_values:
            key_values = [0]
        key_len = len(key_values)
        self.i = 0
        self.j = 0
        self.S = list(range(_WIDTH))
        j = 0
        for i in range(_WIDTH):
            t = self.S[i]
            j = _MASK & (j + key_values[i % key_len] + t)
            self.S[i] = self.S[j]
            self.S[j] = t
        self.g(_WIDTH)

    def g(self, count: int) -> int:
        r = 0
        for _ in range(count):
            self.i = _MASK & (self.i + 1)
            t = self.S[self.i]
            self.j = _MASK & (self.j + t)
            self.S[self.i] = self.S[self.j]
            self.S[self.j] = t
            r = r * _WIDTH + self.S[_MASK & (self.S[self.i] + self.S[self.j])]
        return r


def _mix_key(seed: str) -> list[int]:
    key: list[int] = []
    smear = 0
    for index, char in enumerate(seed):
        key_index = _MASK & index
        while len(key) <= key_index:
            key.append(0)
        smear = (smear ^ (key[key_index] * 19)) & 0xFFFFFFFF
        key[key_index] = _MASK & (smear + ord(char))
    return key


def seedrandom(seed: str) -> float:
    """Return the same first double as npm `seedrandom@3.0.5` for string seeds.

    Lorcanito calls `seedrandom(f"{seed}:{draw}")()` for each random draw.
    The v2 kernel only needs that explicit string-seed path for deterministic
    runtime parity.
    """

    arc4 = _Arc4(_mix_key(str(seed)))
    n = float(arc4.g(_CHUNKS))
    d = _START_DENOM
    x = 0
    while n < _SIGNIFICANCE:
        n = (n + x) * _WIDTH
        d *= _WIDTH
        x = arc4.g(1)
    while n >= _OVERFLOW:
        n /= 2.0
        d /= 2.0
        x >>= 1
    return (n + x) / d


@dataclass(slots=True)
class RandomAPI:
    ctx_random: CtxRandom

    def random(self) -> float:
        draws = self.ctx_random.draws + 1
        value = seedrandom(f"{self.ctx_random.seed}:{draws}")
        self.ctx_random = CtxRandom(
            seed=self.ctx_random.seed,
            state=self.ctx_random.state,
            draws=draws,
        )
        return value

    def shuffle(self, values: Sequence[T]) -> tuple[T, ...]:
        result = list(values)
        for index in range(len(result) - 1, 0, -1):
            swap_index = int(self.random() * (index + 1))
            result[index], result[swap_index] = result[swap_index], result[index]
        return tuple(result)


def create_random_api_for_ctx(ctx_random: CtxRandom) -> RandomAPI:
    return RandomAPI(ctx_random=ctx_random)


def create_random_api_for_state(state) -> RandomAPI:
    return create_random_api_for_ctx(state.ctx.random)
