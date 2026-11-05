"""Isolated full-data Polars experiments with OS peak RSS and exact hashes."""

import argparse
import hashlib
import importlib
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import polars as pl
import psutil
from benchmark import digest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/ad_data.csv"))
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("benchmarks/polars-experiments.json"),
    )
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--module", default="polars_baseline")
    parser.add_argument(
        "--threads", type=int, nargs="+", default=[2, 4, 8, 16]
    )
    parser.add_argument("--chunk-size", type=int)
    parser.add_argument("--morsel-size", type=int)
    parser.add_argument("--batch-rows", type=int)
    parser.add_argument("--batch-bytes", type=int)
    parser.add_argument("--low-memory", action="store_true")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument(
        "--reference",
        type=Path,
        default=Path("benchmarks/polars-thread-tuning.json"),
    )
    args = parser.parse_args()
    if args.worker:
        from ad_aggregator.core import write_results

        if args.chunk_size:
            pl.Config.set_streaming_chunk_size(args.chunk_size)
        aggregate = importlib.import_module(
            "ad_aggregator." + args.module
        ).aggregate
        options = {}
        if args.module == "polars_experimental":
            options = {
                "low_memory": args.low_memory,
                "batch_rows": args.batch_rows,
                "batch_bytes": args.batch_bytes,
            }
        totals = aggregate(args.input, **options)
        output = Path("benchmark-output/polars-experiments")
        write_results(totals, output)
        print(
            json.dumps(
                {
                    "aggregate_sha256": hashlib.sha256(
                        json.dumps(sorted(totals.items())).encode()
                    ).hexdigest(),
                    "output_sha256": {
                        p.name: digest(p) for p in sorted(output.glob("*.csv"))
                    },
                    "campaigns": len(totals),
                    "peak_rss_bytes": psutil.Process().memory_info().peak_wset,
                    "actual_threads": pl.thread_pool_size(),
                }
            )
        )
        return
    if args.repeats < 2 or min(args.threads) < 1:
        parser.error("repeats >=2 and positive threads required")
    report = {
        "command": [sys.executable, *sys.argv],
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "complete": False,
        "input_bytes": args.input.stat().st_size,
        "input_sha256": digest(args.input),
        "python": sys.version,
        "polars": pl.__version__,
        "psutil": psutil.__version__,
        "platform": platform.platform(),
        "processor": platform.processor(),
        "physical_cpus": psutil.cpu_count(logical=False),
        "logical_cpus": psutil.cpu_count(),
        "ram_bytes": psutil.virtual_memory().total,
        "source_sha256": {
            str(p): digest(p)
            for p in sorted(
                [*Path("src/ad_aggregator").glob("*.py"), Path(__file__)]
            )
        },
        "conditions": "Sequential fresh subprocesses; thread order reversed "
        "on alternate repetitions. Warm OS cache (input hashed first), "
        "uncontrolled desktop load. Wall time includes startup, imports, "
        "validation, aggregation, ranking, output and hashing. RSS is Windows "
        "OS peak working set, including native allocations and resident "
        "mapped file pages. No sampled estimate. No cache flush.",
        "options": vars(args)
        | {
            "input": str(args.input),
            "report": str(args.report),
            "reference": str(args.reference),
        },
        "runs": [],
    }
    reference = None
    if args.module != "polars_baseline":
        baseline = json.loads(args.reference.read_text())
        if not baseline["complete"] or (
            baseline["input_sha256"] != report["input_sha256"]
        ):
            raise RuntimeError("Reference incomplete or input differs")
        first = baseline["runs"][0]
        reference = (first["aggregate_sha256"], first["output_sha256"])
    for repeat in range(args.repeats):
        for threads in args.threads[:: 1 if repeat % 2 == 0 else -1]:
            env = os.environ.copy()
            for name in (
                "POLARS_MAX_THREADS",
                "POLARS_STREAMING_CHUNK_SIZE",
                "POLARS_IDEAL_MORSEL_SIZE",
                "POLARS_ENGINE_AFFINITY",
            ):
                env.pop(name, None)
            env["POLARS_MAX_THREADS"] = str(threads)
            if args.morsel_size:
                env["POLARS_IDEAL_MORSEL_SIZE"] = str(args.morsel_size)
            command = [
                sys.executable,
                __file__,
                "--worker",
                "--input",
                str(args.input),
                "--module",
                args.module,
            ]
            if args.chunk_size:
                command += ["--chunk-size", str(args.chunk_size)]
            if args.batch_rows:
                command += ["--batch-rows", str(args.batch_rows)]
            if args.batch_bytes:
                command += ["--batch-bytes", str(args.batch_bytes)]
            if args.low_memory:
                command += ["--low-memory"]
            start = time.perf_counter()
            completed = subprocess.run(
                command, env=env, capture_output=True, text=True, check=True
            )
            elapsed = time.perf_counter() - start
            result = json.loads(completed.stdout)
            identity = (result["aggregate_sha256"], result["output_sha256"])
            if reference is None:
                reference = identity
            if identity != reference:
                raise RuntimeError("Results differ between runs")
            result.update(
                threads=threads,
                repetition=repeat + 1,
                seconds=elapsed,
                mib_per_second=report["input_bytes"] / 2**20 / elapsed,
            )
            report["runs"].append(result)
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2) + "\n")
            print(
                f"{args.module} threads={threads}: {elapsed:.3f}s, "
                f"{result['peak_rss_bytes'] / 2**20:.1f} MiB",
                flush=True,
            )
    if digest(args.input) != report["input_sha256"]:
        raise RuntimeError("Input changed")
    report["complete"] = True
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    for threads in args.threads:
        runs = [r for r in report["runs"] if r["threads"] == threads]
        print(threads, statistics.median(r["seconds"] for r in runs))


if __name__ == "__main__":
    main()
