"""Repeat isolated runs; persist timings, OS peak RSS, and result hashes."""

import argparse
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil


def digest(path: Path) -> str:
    """Hash a file with bounded memory."""
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def worker(args: argparse.Namespace) -> None:
    """Run one pipeline and report all aggregate and output identities."""
    from ad_aggregator.core import write_results

    if args.worker == "python":
        from ad_aggregator.python_engine import aggregate
    elif args.worker == "optimized":
        from ad_aggregator.optimized_engine import aggregate
    elif args.worker == "multiprocessing":
        from ad_aggregator.multiprocessing_engine import aggregate
    else:
        from ad_aggregator.polars_engine import aggregate
    if args.worker == "multiprocessing":
        totals = aggregate(
            args.input, workers=args.workers, chunk_rows=args.chunk_rows
        )
    else:
        totals = aggregate(args.input)
    write_results(totals, args.output)
    aggregate_hash = hashlib.sha256(
        json.dumps(sorted(totals.items())).encode()
    ).hexdigest()
    hashes = {
        name: digest(args.output / name)
        for name in ("top10_ctr.csv", "top10_cpa.csv")
    }
    if sys.platform == "win32":
        peak = psutil.Process().memory_info().peak_wset
    else:
        import resource

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform != "darwin":
            peak *= 1024
    print(
        json.dumps(
            {
                "parent_os_peak_rss_bytes": peak,
                "campaigns": len(totals),
                "aggregate_sha256": aggregate_hash,
                "output_sha256": hashes,
            }
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/ad_data.csv"))
    parser.add_argument(
        "--output", type=Path, default=Path("benchmark-output")
    )
    parser.add_argument(
        "--report", type=Path, default=Path("benchmarks/results.json")
    )
    parser.add_argument("--repeats", type=int, default=3)
    engines = ["python", "polars", "optimized", "multiprocessing"]
    parser.add_argument("--worker", choices=engines)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--chunk-rows", type=int, default=25_000)
    parser.add_argument(
        "--engines",
        nargs="+",
        choices=engines,
        default=["python", "polars"],
    )
    parser.add_argument("--polars-threads", type=int)
    args = parser.parse_args()
    if args.workers < 1 or args.chunk_rows < 1:
        parser.error("--workers and --chunk-rows must be positive")
    if args.worker:
        worker(args)
        return
    if args.repeats < 2:
        parser.error("--repeats must be >=2")
    if args.polars_threads is not None and args.polars_threads < 1:
        parser.error("--polars-threads must be positive")
    import polars as pl

    input_size = args.input.stat().st_size
    environment = os.environ.copy()
    if args.polars_threads is not None:
        environment["POLARS_MAX_THREADS"] = str(args.polars_threads)
    report = {
        "command": [sys.executable, *sys.argv],
        "source_sha256": {
            str(path): digest(path)
            for path in sorted(
                [*Path("src/ad_aggregator").glob("*.py"), Path(__file__)]
            )
        },
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "complete": False,
        "repeats": args.repeats,
        "engines": args.engines,
        "input": str(args.input),
        "input_bytes": input_size,
        "input_sha256": digest(args.input),
        "python": sys.version,
        "polars": pl.__version__,
        "psutil": psutil.__version__,
        "platform": platform.platform(),
        "processor": platform.processor(),
        "logical_cpus": psutil.cpu_count(),
        "physical_cpus": psutil.cpu_count(logical=False),
        "workers": args.workers,
        "chunk_rows": args.chunk_rows,
        "ram_bytes": psutil.virtual_memory().total,
        "polars_threads": args.polars_threads or pl.thread_pool_size(),
        "environment": {
            key: environment.get(key)
            for key in (
                "POLARS_MAX_THREADS",
                "POLARS_ENGINE_AFFINITY",
                "POLARS_STREAMING_CHUNK_SIZE",
            )
        },
        "conditions": "Fresh sequential subprocesses; alternating engines. "
        "OS cache not flushed. Input SHA256 read before timing. Wall time "
        "includes interpreter startup, imports, validation, aggregation, "
        "ranking, writing, and result hashing. "
        "Peak RSS is maximum sampled sum of simultaneous RSS across the "
        "process tree (10 ms requested interval, not a hard upper bound). "
        "Includes workers and resource tracker; shared pages may be counted "
        "multiple times. Parent OS high-water mark is recorded separately.",
        "runs": [],
    }
    reference = None
    for repeat in range(args.repeats):
        for engine in args.engines if repeat % 2 == 0 else args.engines[::-1]:
            command = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--worker",
                engine,
                "--input",
                str(args.input),
                "--output",
                str(args.output / engine),
                "--workers",
                str(args.workers),
                "--chunk-rows",
                str(args.chunk_rows),
            ]
            start = time.perf_counter()
            try:
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=environment,
                )
                root = psutil.Process(process.pid)
                peak_tree = 0
                samples = 0
                while True:
                    resident = 0
                    try:
                        tree = [root, *root.children(recursive=True)]
                    except psutil.NoSuchProcess:
                        tree = []
                    for member in tree:
                        try:
                            resident += member.memory_info().rss
                        except psutil.NoSuchProcess:
                            pass
                    peak_tree = max(peak_tree, resident)
                    samples += 1
                    try:
                        stdout, stderr = process.communicate(timeout=0.01)
                        break
                    except subprocess.TimeoutExpired:
                        continue
                if process.returncode:
                    raise subprocess.CalledProcessError(
                        process.returncode, command, stdout, stderr
                    )
            except subprocess.CalledProcessError as error:
                raise RuntimeError(
                    f"{engine} benchmark failed: {error.stderr.strip()}"
                ) from error
            elapsed = time.perf_counter() - start
            result = json.loads(stdout)
            result["peak_rss_bytes"] = peak_tree
            result["memory_samples"] = samples
            identity = (result["aggregate_sha256"], result["output_sha256"])
            if reference is None:
                reference = identity
            if identity != reference:
                raise RuntimeError(
                    "Engine results differ; benchmark is invalid"
                )
            result.update(
                engine=engine,
                repetition=repeat + 1,
                seconds=elapsed,
                mib_per_second=input_size / 1024**2 / elapsed,
            )
            report["runs"].append(result)
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(
                json.dumps(report, indent=2) + "\n", encoding="utf-8"
            )
            print(
                f"{engine} #{repeat + 1}: {elapsed:.3f}s, "
                f"{result['peak_rss_bytes'] / 1024**2:.1f} MiB, "
                f"{result['mib_per_second']:.2f} MiB/s",
                flush=True,
            )
    report["complete"] = True
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    if (
        args.input.stat().st_size != input_size
        or digest(args.input) != report["input_sha256"]
    ):
        raise RuntimeError("Input changed during benchmarking")
    args.report.write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    for engine in args.engines:
        runs = [row for row in report["runs"] if row["engine"] == engine]
        median = statistics.median(row["seconds"] for row in runs)
        print(f"{engine} median: {median:.3f}s")


if __name__ == "__main__":
    main()
