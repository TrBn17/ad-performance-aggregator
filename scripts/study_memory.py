"""Profile batch lifetimes and compare changes against the old 32 MiB path.

Run in the locked dev environment. Profiling and timing are separate processes;
tracemalloc tracks Python buffers; RSS includes native Polars allocations.
"""

import argparse
import gc
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import polars as pl
import psutil
from benchmark import digest

from ad_aggregator import polars_engine as engine
from ad_aggregator.core import write_results


def original_batches(path: Path, batch_bytes: int) -> Iterator[pl.DataFrame]:
    """Frozen pre-study reader for reproducible comparisons after promotion."""
    with path.open("rb") as source:
        header = source.readline()
        pending = b""
        while block := source.read(batch_bytes):
            pending += block
            end = engine._last_record_end(pending)
            if end < 0:
                engine._check_record_buffer(pending)
                continue
            yield engine._read_bytes(header + pending[: end + 1])
            pending = pending[end + 1 :]
            engine._check_record_buffer(pending)
        if pending:
            yield engine._read_bytes(header + pending)


READERS = {
    "current": original_batches,
    "released": engine._byte_batches,
    "released16": engine._byte_batches,
}
BATCH_MIB = {"current": 32, "released": 32, "released16": 16}


def peak_rss() -> int:
    """Return OS resident high-water mark including native allocations."""
    if sys.platform == "win32":
        return psutil.Process().memory_info().peak_wset
    import resource

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak if sys.platform == "darwin" else peak * 1024


def profile(args: argparse.Namespace) -> dict:
    events = []
    process = psutil.Process()
    tracemalloc.start()

    def record(phase, **extra):
        current, peak = tracemalloc.get_traced_memory()
        events.append(
            dict(
                phase=phase,
                python_live_bytes=current,
                python_peak_bytes=peak,
                rss_bytes=process.memory_info().rss,
                os_peak_rss_bytes=peak_rss(),
                largest_python_sites=[
                    str(site)
                    for site in tracemalloc.take_snapshot().statistics(
                        "lineno"
                    )[:6]
                ],
                **extra,
            )
        )

    read = engine._read_bytes

    def traced_read(data):
        record("before_parse", input_bytes=len(data))
        frame = read(data)
        record("after_parse", frame_bytes=frame.estimated_size())
        return frame

    engine._read_bytes = traced_read
    record("start")
    batches = READERS[args.worker](
        args.input, BATCH_MIB[args.worker] * 1024**2
    )
    totals = {}
    for index in range(3):
        frame = next(batches)
        record("yielded", batch=index)
        grouped = engine.query(frame.lazy()).collect()
        record("grouped", batch=index, grouped_bytes=grouped.estimated_size())
        partial = engine._totals(grouped)
        for campaign, values in partial.items():
            previous = totals.get(campaign, (0, 0, 0, 0))
            totals[campaign] = tuple(a + b for a, b in zip(previous, values))
        del frame, grouped
        gc.collect()
        record("after_merge_gc", batch=index)
    batches.close()
    del batches, totals, partial, previous, values, campaign
    gc.collect()
    record("closed_gc")
    tracemalloc.stop()
    return {"events": events}


def worker(args: argparse.Namespace) -> dict:
    if args.profile:
        return profile(args)
    engine._byte_batches = READERS[args.worker]
    start = time.perf_counter()
    totals = engine.aggregate(
        args.input, batch_bytes=BATCH_MIB[args.worker] * 1024**2
    )
    aggregated = time.perf_counter()
    write_results(totals, args.output)
    written = time.perf_counter()
    canonical = json.dumps(sorted(totals.items())).encode()
    oracle = args.input.with_suffix(".expected.json")
    if oracle.exists() and canonical != oracle.read_bytes():
        raise ValueError("Independent analytical aggregate oracle differs")
    return {
        "campaigns": len(totals),
        "aggregate_sha256": hashlib.sha256(canonical).hexdigest(),
        "output_sha256": {
            name: digest(args.output / name)
            for name in ("top10_ctr.csv", "top10_cpa.csv")
        },
        "oracle_compared": oracle.exists(),
        "aggregate_seconds": aggregated - start,
        "rank_write_seconds": written - aggregated,
        "parent_os_peak_rss_bytes": peak_rss(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, nargs="+", required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument(
        "--output", type=Path, default=Path("benchmark-output/memory-study")
    )
    parser.add_argument("--worker", choices=READERS)
    parser.add_argument(
        "--config", nargs="+", choices=READERS, default=["current", "released"]
    )
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.worker:
        args.input = args.input[0]
        print(json.dumps(worker(args)))
        return
    if args.repeats < 3 or args.report is None:
        parser.error("--report and at least three repetitions required")
    if args.report.exists():
        parser.error("Refusing to overwrite an existing report")
    env = os.environ.copy()
    for key in (
        "POLARS_STREAMING_CHUNK_SIZE",
        "POLARS_IDEAL_MORSEL_SIZE",
        "POLARS_ENGINE_AFFINITY",
    ):
        env.pop(key, None)
    env["POLARS_MAX_THREADS"] = "16"
    report = {
        "command": [sys.executable, *sys.argv],
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "complete": False,
        "profile": args.profile,
        "python": sys.version,
        "polars": pl.__version__,
        "psutil": psutil.__version__,
        "platform": platform.platform(),
        "cpu": platform.processor(),
        "physical_cpus": psutil.cpu_count(logical=False),
        "logical_cpus": psutil.cpu_count(),
        "ram_bytes": psutil.virtual_memory().total,
        "environment": {
            key: value
            for key, value in env.items()
            if key.startswith("POLARS_")
        },
        "source_sha256": {
            str(p): digest(p)
            for p in [Path(__file__), *Path("src/ad_aggregator").glob("*.py")]
        },
        "conditions": (
            "Fresh sequential subprocesses, reverse order each repetition; "
            "warm cache from input hashing; background load uncontrolled. "
            "Wall includes startup/imports, full pipeline and aggregate/CSV "
            "hashes. OS peak RSS includes native allocations; simultaneous "
            "process-tree RSS sampled every 10 ms also includes workers "
            "(shared pages can count twice, short peaks can be missed). "
            "No workers spawned by this engine. Profiling uses only three "
            "batches with tracemalloc and GC; profile timings are not "
            "performance evidence. Analytical oracle read/compare included "
            "for synthetic inputs."
        ),
        "datasets": [],
    }
    for path in args.input:
        size, identity = path.stat().st_size, digest(path)
        dataset = {
            "input": str(path),
            "input_bytes": size,
            "input_sha256": identity,
            "runs": [],
        }
        report["datasets"].append(dataset)
        reference = None
        for repeat in range(1 if args.profile else args.repeats):
            names = args.config.copy()
            if repeat % 2:
                names.reverse()
            for name in names:
                command = [
                    sys.executable,
                    __file__,
                    "--worker",
                    name,
                    "--input",
                    str(path),
                    "--output",
                    str(args.output / path.stem / name),
                ]
                if args.profile:
                    command.append("--profile")
                start = time.perf_counter()
                with tempfile.TemporaryFile() as capture:
                    process = subprocess.Popen(
                        command,
                        env=env,
                        stdout=capture,
                        stderr=subprocess.STDOUT,
                    )
                    tree_peak = 0
                    monitored = psutil.Process(process.pid)
                    while process.poll() is None:
                        try:
                            tree = [
                                monitored,
                                *monitored.children(recursive=True),
                            ]
                            tree_peak = max(
                                tree_peak,
                                sum(
                                    p.memory_info().rss
                                    for p in tree
                                    if p.is_running()
                                ),
                            )
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                        time.sleep(0.01)
                    capture.seek(0)
                    stdout = capture.read().decode()
                elapsed = time.perf_counter() - start
                if process.returncode:
                    raise RuntimeError(stdout)
                result = json.loads(stdout)
                if not args.profile:
                    signature = [
                        result[k]
                        for k in (
                            "campaigns",
                            "aggregate_sha256",
                            "output_sha256",
                        )
                    ]
                    if reference is not None and signature != reference:
                        raise ValueError("Results differ")
                    reference = signature
                result.update(
                    configuration=name,
                    repetition=repeat + 1,
                    command=command,
                    seconds=elapsed,
                    mib_per_second=size / 2**20 / elapsed,
                    sampled_tree_peak_rss_bytes=tree_peak,
                )
                dataset["runs"].append(result)
                args.report.write_text(json.dumps(report, indent=2) + "\n")
                print(
                    f"{path.name} {name} #{repeat + 1}: {elapsed:.3f}s",
                    flush=True,
                )
        if digest(path) != identity:
            raise ValueError("Input changed")
        if not args.profile:
            for name in args.config:
                runs = [
                    r for r in dataset["runs"] if r["configuration"] == name
                ]
                print(
                    name,
                    statistics.median(r["seconds"] for r in runs),
                    max(r["parent_os_peak_rss_bytes"] for r in runs) / 2**20,
                    flush=True,
                )
    report["complete"] = True
    args.report.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
