#!/usr/bin/env python3
"""Run the configured Apertus study jobs locally on UBELIX, or mock them on CPU."""

from __future__ import annotations

import argparse
from itertools import product
from pathlib import Path

import yaml

from urban_computing.llm import runner


def main(argv: list[str] | None = None) -> None:
    """Run the study matrix or the selected condition, temperature, and seed."""
    config = yaml.safe_load(runner.STUDY_CONFIG.read_text(encoding="utf-8"))
    llm = config["llm"]
    questions_file = Path(config["evaluation"].get("questions_file", "eval/questions.jsonl"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, default=questions_file)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--condition", choices=llm["conditions"])
    parser.add_argument("--temperature", type=float, choices=llm["temperatures"])
    parser.add_argument("--seed", type=int, choices=llm["seeds"])
    parser.add_argument("--array-index", type=int, help="zero-based index into the study matrix")
    parser.add_argument("--mock", action="store_true", help="use deterministic synthetic inference")
    args = parser.parse_args(argv)

    filters = (args.condition, args.temperature, args.seed)
    jobs = list(product(llm["conditions"], llm["temperatures"], llm["seeds"]))
    if args.array_index is not None:
        if any(value is not None for value in filters):
            parser.error(
                "--array-index cannot be combined with --condition, --temperature or --seed"
            )
        if not 0 <= args.array_index < len(jobs):
            parser.error(f"--array-index must be between 0 and {len(jobs) - 1}")
        jobs = [jobs[args.array_index]]
    else:
        jobs = [
            job
            for job in jobs
            if all(want is None or got == want for want, got in zip(filters, job, strict=True))
        ]

    default_dir = Path(config["data"]["interim_dir"]) / ("llm-mock" if args.mock else "llm")
    for condition, temperature, seed in jobs:
        result = runner.run(
            args.questions,
            condition,
            llm["model_id"],
            temperature,
            seed,
            args.out_dir or default_dir,
            mock=args.mock,
        )
        print(result, flush=True)


if __name__ == "__main__":
    main()
