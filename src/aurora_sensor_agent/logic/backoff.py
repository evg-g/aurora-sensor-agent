"""Exponential backoff with full jitter, as pure maths over an injected RNG.

When the uplink is down, retrying immediately and forever just hammers a broker that is already
struggling, and a whole fleet retrying in lockstep produces a "thundering herd" the instant the
network returns. The fix is two-fold: wait longer after each failure (exponential), and randomise
the wait (jitter) so devices spread out.

This uses **full jitter** (delay drawn uniformly in ``[0, cap]``), which AWS's well-known analysis
found gives the best spread with the fewest collisions. The RNG is injected, so a seeded RNG makes
the "random" delays reproducible in tests.
"""

from __future__ import annotations

import random


def compute_delay(
    attempt: int,
    *,
    base_seconds: float,
    factor: float,
    max_seconds: float,
    jitter: bool,
    rng: random.Random,
) -> float:
    """Delay before retry number ``attempt`` (0-based).

    ``base * factor**attempt`` capped at ``max_seconds``; with jitter, drawn uniformly in
    ``[0, that cap]``. Without jitter it returns the cap itself (deterministic, for illustration).
    """
    if attempt < 0:
        raise ValueError(f"attempt must be >= 0, got {attempt}")
    uncapped = base_seconds * (factor**attempt)
    capped = min(max_seconds, uncapped)
    if jitter:
        return rng.uniform(0.0, capped)
    return capped


class Backoff:
    """Stateful helper: tracks the attempt count and produces the next delay.

    ``next_delay`` returns the wait before the next retry and advances the counter; ``reset`` is
    called after a success so the next failure starts from the base delay again.
    """

    def __init__(
        self,
        *,
        base_seconds: float,
        factor: float,
        max_seconds: float,
        jitter: bool,
        rng: random.Random | None = None,
    ) -> None:
        self._base = base_seconds
        self._factor = factor
        self._max = max_seconds
        self._jitter = jitter
        self._rng = rng if rng is not None else random.Random()
        self._attempt = 0

    @property
    def attempt(self) -> int:
        return self._attempt

    def next_delay(self) -> float:
        delay = compute_delay(
            self._attempt,
            base_seconds=self._base,
            factor=self._factor,
            max_seconds=self._max,
            jitter=self._jitter,
            rng=self._rng,
        )
        self._attempt += 1
        return delay

    def reset(self) -> None:
        self._attempt = 0


__all__ = ["Backoff", "compute_delay"]
