"""Compare packaged Polars engines in Linux with OS RSS and exact oracles."""

import argparse
import hashlib
import json
import os
import platform
import resource
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def worker(args: argparse.Namespace) -> None:
    import polars as pl

    from ad_aggregator.core import write_results

    if args.worker == "baseline":
        from ad_aggregator.polars_baseline import aggregate
    else:
        from ad_aggregator.polars_engine import aggregate
    start = time.perf_counter()
    totals = aggregate(args.input)
    aggregated = time.perf_counter()
    write_results(totals, args.output)
    written = time.perf_counter()
    args.output.joinpath("aggregates.json").write_text(
        json.dumps(sorted(totals.items())), encoding="utf-8"
    )
    identity = {
        "aggregate_sha256": digest(args.output / "aggregates.json"),
        "output_sha256": {
            name: digest(args.output / name)
            for name in ("top10_ctr.csv", "top10_cpa.csv")
        },
    }
    print(
        json.dumps(
            {
                **identity,
                "campaigns": len(totals),
                "aggregate_seconds": aggregated - start,
                "rank_and_write_seconds": written - aggregated,
                "identity_seconds": time.perf_counter() - written,
                "peak_rss_bytes": resource.getrusage(
                    resource.RUSAGE_SELF
                ).ru_maxrss
                * 1024,
                "polars": pl.__version__,
                "actual_threads": pl.thread_pool_size(),
            }
        )
    )


def read_optional(path: str) -> str | None:
    try:
        return Path(path).read_text().strip()
    except FileNotFoundError:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--worker", choices=["baseline", "optimized"])
    parser.add_argument("--data", type=Path, default=Path("/study/data"))
    parser.add_argument("--output", type=Path, default=Path("/study/output"))
    parser.add_argument(
        "--report", type=Path, default=Path("/study/linux-scalability.json")
    )
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--threads", type=int, default=16)
    parser.add_argument(
        "--original-reference",
        type=Path,
        default=Path("/repo/benchmarks/polars-memory-final.json"),
    )
    args = parser.parse_args()
    if sys.platform != "linux":
        parser.error("Linux only: ru_maxrss is reported in KiB")
    if args.worker:
        worker(args)
        return
    if args.repeats < 2 or args.threads < 1:
        parser.error("repeats >=2 and threads >=1 required")
    import ad_aggregator

    package = Path(ad_aggregator.__file__).parent
    files = [
        *package.glob("*.py"),
        Path(__file__),
        Path(__file__).with_name("generate_scalability.py"),
    ]
    report = {
        "command": [sys.executable, *sys.argv],
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "complete": False,
        "python": sys.version,
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "cpu_affinity": sorted(os.sched_getaffinity(0)),
        "cpu_info": read_optional("/proc/cpuinfo"),
        "memory_info": read_optional("/proc/meminfo"),
        "cgroup": {
            name: read_optional("/sys/fs/cgroup/" + name)
            for name in ["memory.max", "memory.swap.max", "cpu.max"]
        },
        "source_sha256": {str(p): digest(p) for p in files},
        "conditions": "Fresh sequential subprocesses; engine order reversed "
        "on alternate repetitions. Warm Linux page cache (input SHA256 read "
        "before timing). OS cache not flushed; background load uncontrolled. "
        "Elapsed includes startup, imports, validation, aggregation, ranking, "
        "CSVs, complete aggregate JSON export and hashes. RSS is Linux "
        "getrusage(RUSAGE_SELF).ru_maxrss * 1024, per worker. Controller, "
        "Docker/VM overhead and page cache outside process RSS are excluded. "
        "Exact aggregate-oracle comparison occurs in controller after timing.",
        "datasets": [],
    }
    original = json.loads(args.original_reference.read_text())
    descriptors = [
        (
            args.data / "original.csv",
            {
                "input_bytes": original["input_bytes"],
                "input_sha256": original["input_sha256"],
                **{
                    key: original["runs"][0][key]
                    for key in (
                        "campaigns",
                        "aggregate_sha256",
                        "output_sha256",
                    )
                },
            },
        )
    ]
    for path in sorted((args.data / "synthetic-v1").glob("*.manifest.json")):
        descriptors.append(
            (
                path.with_name(path.name.replace(".manifest.json", ".csv")),
                json.loads(path.read_text()),
            )
        )
    if len(descriptors) != 4:
        raise ValueError("Expected original plus three synthetic datasets")
    env = os.environ.copy()
    for key in (
        "POLARS_IDEAL_MORSEL_SIZE",
        "POLARS_STREAMING_CHUNK_SIZE",
        "POLARS_ENGINE_AFFINITY",
    ):
        env.pop(key, None)
    env["POLARS_MAX_THREADS"] = str(args.threads)
    for path, expected in descriptors:
        if (
            path.stat().st_size != expected["input_bytes"]
            or digest(path) != expected["input_sha256"]
        ):
            raise ValueError(f"Input identity differs: {path}")
        oracle_path = path.with_suffix(".expected.json")
        oracle = (
            json.loads(oracle_path.read_text())
            if oracle_path.exists()
            else None
        )
        dataset = {"input": str(path), "expected": expected, "runs": []}
        report["datasets"].append(dataset)
        for repetition in range(args.repeats):
            engines = ["baseline", "optimized"]
            if repetition % 2:
                engines.reverse()
            for engine in engines:
                output = args.output / path.stem / engine
                command = [
                    sys.executable,
                    __file__,
                    "--worker",
                    engine,
                    "--input",
                    str(path),
                    "--output",
                    str(output),
                ]
                start = time.perf_counter()
                completed = subprocess.run(
                    command,
                    env=env,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                seconds = time.perf_counter() - start
                result = json.loads(completed.stdout)
                for key in ("campaigns", "aggregate_sha256", "output_sha256"):
                    if result[key] != expected[key]:
                        raise ValueError(f"{path} {engine}: {key} differs")
                if (
                    oracle is not None
                    and json.loads((output / "aggregates.json").read_text())
                    != oracle
                ):
                    raise ValueError(f"Exact aggregate mismatch: {path}")
                result.update(
                    engine=engine,
                    repetition=repetition + 1,
                    seconds=seconds,
                    mib_per_second=path.stat().st_size / 2**20 / seconds,
                    exact_oracle_compared=oracle is not None,
                )
                dataset["runs"].append(result)
                args.report.write_text(json.dumps(report, indent=2) + "\n")
                peak_mib = result["peak_rss_bytes"] / 2**20
                print(
                    f"{path.stem} {engine} #{repetition + 1}: "
                    f"{seconds:.3f}s, {peak_mib:.1f} MiB",
                    flush=True,
                )
        if digest(path) != expected["input_sha256"]:
            raise ValueError(f"Input changed: {path}")
        del oracle
    report["complete"] = True
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    args.report.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
