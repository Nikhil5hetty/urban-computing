"""Summary miner (UC-023). SummaryRecord is the frozen interface; `mine` is a stub."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from urban_computing.fuzzy.vocabulary import Vocabulary


@dataclass(frozen=True)
class SummaryRecord:
    protoform: str  # "simple" | "restricted"
    quantifier: str  # e.g. "most"
    summarizer: str  # e.g. "arrival_delay_minutes:on_time"
    restriction: str | None  # e.g. "time_band=morning_peak&product=IC"; None = whole segment
    segment: str  # e.g. "hub=Olten" or "network"
    n: int  # rows in the segment (crisp count)
    truth: float
    coverage: float | None
    quality: float | None
    half: str | None  # "first" | "second" | None (both)
    sentence: str  # deterministic English rendering
    small_n: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def mine(
    values: dict[str, np.ndarray],
    restrictions: dict[str, np.ndarray],
    vocab: Vocabulary,
    beta: float = 0.6,
    segment: str = "network",
    half: str | None = None,
    quantifier_set: str = "core",
    tnorm: str = "product",
) -> list[SummaryRecord]:
    """Enumerate Q x S (x R) summaries over one segment.

    values: attribute name -> raw values (e.g. {"arrival_delay_minutes": delays})
    restrictions: restriction label -> membership array (crisp masks as 0/1 floats)
    Returns ALL records (valid and invalid); callers filter on truth >= beta.
    """
    raise NotImplementedError("UC-023")
