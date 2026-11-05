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
        "--engine", choices=["python", "polars"], default="polars"
    )
    args = parser.parse_args(argv)
    try:
        if args.input.resolve() in {
            (args.output / name).resolve()
            for name in ("top10_ctr.csv", "top10_cpa.csv")
        }:
            raise InputError("Output files must not overwrite the input CSV")
        if args.engine == "python":
            from .python_engine import aggregate
        else:
            from .polars_engine import aggregate
        totals = aggregate(args.input)
        write_results(totals, args.output)
    except (InputError, OSError, UnicodeError, csv.Error) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0
