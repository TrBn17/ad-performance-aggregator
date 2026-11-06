"""Check new study identities against retained independent oracles."""

import argparse
import json
import statistics
from pathlib import Path

from benchmark import digest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--reference",
        type=Path,
        default=Path("benchmarks/docker-linux-scalability.json"),
    )
    args = parser.parse_args()
    report = json.loads(args.report.read_text())
    reference = json.loads(args.reference.read_text())
    if not report["complete"] or not reference["complete"]:
        raise ValueError("Incomplete study")
    expected = {
        item["expected"]["input_sha256"]: item["expected"]
        for item in reference["datasets"]
    }
    for dataset in report["datasets"]:
        identity = expected[dataset["input_sha256"]]
        if dataset["input_bytes"] != identity["input_bytes"]:
            raise ValueError("Input size differs")
        path = Path(dataset["input"])
        if digest(path) != dataset["input_sha256"]:
            raise ValueError(f"Input changed: {path}")
        for run in dataset["runs"]:
            for key in ("campaigns", "aggregate_sha256", "output_sha256"):
                if run[key] != identity[key]:
                    raise ValueError(
                        f"Prior independent oracle differs: {key}"
                    )
            command = run["command"]
            output = Path(command[command.index("--output") + 1])
            for name, expected_hash in identity["output_sha256"].items():
                if digest(output / name) != expected_hash:
                    raise ValueError(f"Retained CSV differs: {output / name}")
        for name in sorted({r["configuration"] for r in dataset["runs"]}):
            runs = [r for r in dataset["runs"] if r["configuration"] == name]
            if len(runs) < 3:
                raise ValueError("At least three runs required")
            peak_mib = max(r["parent_os_peak_rss_bytes"] for r in runs) / 2**20
            print(
                f"{identity['campaigns']:>6} {name:>10}: "
                f"{statistics.median(r['seconds'] for r in runs):.3f} s; "
                f"{peak_mib:.1f}"
                " MiB; "
                f"{statistics.median(r['mib_per_second'] for r in runs):.2f}"
                " MiB/s"
            )
    print("Input, full aggregate and CSV identities match prior oracles.")


if __name__ == "__main__":
    main()
