"""Profile a bounded CSV record sample without modifying the dataset."""

import argparse
import cProfile
import csv
import itertools
import pstats
import tempfile
from pathlib import Path

from ad_aggregator.python_engine import aggregate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/ad_data.csv"))
    parser.add_argument("--rows", type=int, default=100000)
    parser.add_argument(
        "--output", type=Path, default=Path("benchmarks/python-profile.txt")
    )
    args = parser.parse_args()
    if args.rows < 1:
        parser.error("--rows must be positive")
    with tempfile.TemporaryDirectory() as directory:
        sample = Path(directory) / "sample.csv"
        with args.input.open(encoding="utf-8-sig", newline="") as source:
            with sample.open("w", encoding="utf-8", newline="") as target:
                writer = csv.writer(target)
                writer.writerows(
                    itertools.islice(csv.reader(source), args.rows + 1)
                )
        profile = cProfile.Profile()
        profile.runcall(aggregate, sample)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as target:
        target.write(f"First {args.rows} records from {args.input}\n")
        pstats.Stats(profile, stream=target).sort_stats(
            "cumulative"
        ).print_stats(20)


if __name__ == "__main__":
    main()
