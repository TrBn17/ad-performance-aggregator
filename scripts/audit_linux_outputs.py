"""Directly compare every aggregate and independently reconstruct both CSVs."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

from verify_outputs import expected_csv


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("/study/output"))
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    study = json.loads(args.study.read_text())
    if not study["complete"]:
        raise ValueError("Study is incomplete")
    checks = []
    for dataset in study["datasets"]:
        path = Path(dataset["input"])
        outputs = [
            args.output / path.stem / engine
            for engine in ("baseline", "optimized")
        ]
        aggregates = [
            json.loads((p / "aggregates.json").read_text()) for p in outputs
        ]
        if aggregates[0] != aggregates[1]:
            raise ValueError(f"Engine aggregates differ: {path}")
        oracle = path.with_suffix(".expected.json")
        if oracle.exists() and aggregates[0] != json.loads(oracle.read_text()):
            raise ValueError(f"Oracle aggregates differ: {path}")
        totals = {key: tuple(values) for key, values in aggregates[0]}
        if len(totals) != dataset["expected"]["campaigns"]:
            raise ValueError(f"Campaign cardinality differs: {path}")
        for metric in ("CTR", "CPA"):
            name = f"top10_{metric.lower()}.csv"
            reference = expected_csv(totals, metric)
            if (
                hashlib.sha256(reference).hexdigest()
                != (dataset["expected"]["output_sha256"][name])
            ):
                raise ValueError(f"Independent CSV hash differs: {path}")
            for output in outputs:
                if (output / name).read_bytes() != reference:
                    raise ValueError(f"CSV bytes differ: {output / name}")
        checks.append(
            {
                "input": str(path),
                "campaigns": len(totals),
                "exact_engine_aggregate_comparison": True,
                "exact_analytical_oracle_comparison": oracle.exists(),
                "independent_decimal_csv_bytes": True,
            }
        )
    args.report.write_text(
        json.dumps(
            {
                "complete": True,
                "command": sys.argv,
                "checks": checks,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"Verified all aggregates and CSV bytes for {len(checks)} datasets")


if __name__ == "__main__":
    main()
