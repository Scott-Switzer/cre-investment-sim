"""
Deterministic RNG helpers.

All random outcomes in the simulation are reproducible from a seed.
"""

from __future__ import annotations

from typing import Optional
import numpy as np


def make_generator(seed: Optional[int] = None) -> np.random.Generator:
    if seed is None:
        seed = 20240331
    return np.random.default_rng(seed)
