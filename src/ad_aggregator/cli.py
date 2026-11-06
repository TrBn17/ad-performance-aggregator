"""Command-line interface."""

import argparse
import csv
import sys
from pathlib import Path

from .core import InputError, write_results


def main(argv: list[str] | None = None) -> int:
    """Run the chosen engine; return a nonzero exit code on failure."""
    parser = argparse.ArgumentParser(
        description="Aggregate advertising campaign metrics"
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--engine",
        choices=["python", "polars", "optimized", "multiprocessing"],
        default="polars",
    )
    parser.add_argument(
        "--batch-mib",
        type=int,
        help="Polars input batch MiB (default: 32; not an RSS cap)",
    )
    args = parser.parse_args(argv)
    if args.batch_mib is not None:
        if args.batch_mib < 1:
            parser.error("--batch-mib must be a positive integer")
        if args.engine != "polars":
            parser.error("--batch-mib requires --engine polars")
    try:
        if args.input.resolve() in {
            (args.output / name).resolve()
            for name in ("top10_ctr.csv", "top10_cpa.csv")
        }:
            raise InputError("Output files must not overwrite the input CSV")
        if args.engine == "python":
            from .python_engine import aggregate
        elif args.engine == "optimized":
            from .optimized_engine import aggregate
        elif args.engine == "multiprocessing":
            from .multiprocessing_engine import aggregate
        else:
            from .polars_engine import aggregate
        if args.batch_mib is None:
            totals = aggregate(args.input)
        else:
            totals = aggregate(
                args.input, batch_bytes=args.batch_mib * 1024**2
            )
        write_results(totals, args.output)
    except (InputError, OSError, UnicodeError, csv.Error) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0
