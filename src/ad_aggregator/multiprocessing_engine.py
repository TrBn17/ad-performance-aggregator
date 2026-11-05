"""Bounded, record-safe CSV chunks with parallel validation and aggregation."""

import csv
import multiprocessing
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from itertools import islice
from pathlib import Path

from .core import Totals, validate_header
from .optimized_engine import aggregate_rows

# Explicit conservative defaults, independent of the host's CPU count.
DEFAULT_WORKERS = 4
DEFAULT_CHUNK_ROWS = 25_000


def aggregate(
    path: Path,
    *,
    workers: int = DEFAULT_WORKERS,
    chunk_rows: int = DEFAULT_CHUNK_ROWS,
) -> Totals:
    """Merge chunks in input order with at most two chunks per worker queued.

    The parent parses CSV once; workers validate values and aggregate records.
    Chunk sizes count logical records, not physical lines or byte offsets.
    Memory also scales with field sizes and distinct campaign/date counts.
    """
    if workers < 1 or chunk_rows < 1:
        raise ValueError("workers and chunk_rows must be positive")
    totals: dict[str, list[int]] = {}
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.reader(source, strict=True)
        header = validate_header(next(reader, None))
        # Spawn is portable and avoids inheriting open input handles.
        with ProcessPoolExecutor(
            max_workers=workers,
            mp_context=multiprocessing.get_context("spawn"),
        ) as pool:
            pending = deque()
            record = 2
            exhausted = False
            while pending or not exhausted:
                while not exhausted and len(pending) < workers * 2:
                    rows = list(islice(reader, chunk_rows))
                    if not rows:
                        exhausted = True
                        break
                    pending.append(
                        pool.submit(aggregate_rows, rows, header, record)
                    )
                    record += len(rows)
                if not pending:
                    break
                for campaign, values in pending.popleft().result().items():
                    current = totals.get(campaign)
                    if current is None:
                        totals[campaign] = list(values)
                    else:
                        current[0] += values[0]
                        current[1] += values[1]
                        current[2] += values[2]
                        current[3] += values[3]
    return {key: tuple(values) for key, values in totals.items()}
