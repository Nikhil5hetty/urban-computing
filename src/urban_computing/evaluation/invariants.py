"""Invariant providers loaded by the project evaluation runner."""

from pathlib import Path

import duckdb

from urban_computing.data.ingest import ingest_all
from urban_computing.data.quality import _open_events, _punctuality
from urban_computing.evaluation import registry


@registry.invariant("I5")
def punctual_arrival_sanity(ctx: registry.Context) -> registry.InvariantResult:
    """Check the preregistered band for the share of punctual REAL train arrivals."""
    interim = Path(ctx.paths["interim_dir"])
    if ctx.sample:
        ingest_all(Path(ctx.paths["raw_dir"]), interim / "ist")
    with duckdb.connect() as connection:
        try:
            _open_events(connection, interim)
        except FileNotFoundError as error:
            return registry.InvariantResult(False, {"reason": str(error)})
        i5, _ = _punctuality(connection, ctx.config)
    return registry.InvariantResult(i5["pass"], i5)
