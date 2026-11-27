"""Build the study question set from the processed arrivals and connections."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml

from urban_computing.assistant.crisp import hub_stop_keys
from urban_computing.data import connections as connection_data
from urban_computing.data.arrivals import _stop_key
from urban_computing.evaluation.questions import _question_set, write_questions


def _matched_feeders(connections: pd.DataFrame, arrivals: pd.DataFrame, config: dict) -> pd.Series:
    """Mark pairs whose feeder is a measured arrival at the hub's resolved stops."""
    arrivals = arrivals.loc[~arrivals["cancelled"] & arrivals["delay_min"].notna()]
    stop_keys = _stop_key(arrivals["stop_id"])
    arrival_keys = ["operating_day", "journey_id", "time_band"]
    pair_keys = ["operating_day", "arr_journey_id", "time_band"]
    matched = pd.Series(False, index=connections.index)
    for hub in config["connections"]["hubs"]:
        keys = hub_stop_keys(hub, config)
        if not keys:
            raise ValueError(f"No resolved stop identifiers for {hub}")
        feeders = pd.MultiIndex.from_frame(arrivals.loc[stop_keys.isin(keys), arrival_keys])
        at_hub = connections["hub"].eq(hub)
        pairs = pd.MultiIndex.from_frame(connections.loc[at_hub, pair_keys])
        matched.loc[at_hub] = pairs.isin(feeders)
    return matched


def main() -> None:
    """Read the study configuration and write the JSONL set and adjacent JSON manifest."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/study.yaml"))
    parser.add_argument("--output", type=Path, default=Path("eval/questions.jsonl"))
    args = parser.parse_args()

    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    settings = config["connections"]
    data = config["data"]
    processed = Path(data["processed_dir"])
    atlas = Path(data["service_points_dir"]) / "actual-date-swiss-service-point.csv"
    try:
        pairs = pd.read_parquet(processed / "connections.parquet")
        arrivals = pd.read_parquet(
            processed / "arrivals.parquet",
            columns=[
                "operating_day",
                "journey_id",
                "time_band",
                "cancelled",
                "delay_min",
                "stop_id",
            ],
        )
        if not settings.get("hub_stop_ids"):
            settings["hub_stop_ids"] = connection_data._hub_ids(atlas, settings["hubs"])
        matched = _matched_feeders(pairs, arrivals, config)
        questions, manifest = _question_set(
            pairs, config, config["study"]["seed"], matched_feeders=matched
        )
    except (FileNotFoundError, ValueError) as error:
        parser.exit(1, f"{parser.prog}: {error}\n")

    write_questions(questions, args.output)
    manifest_path = args.output.with_name(f"{args.output.stem}_manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(questions)} questions to {args.output} and {manifest_path}")


if __name__ == "__main__":
    main()
