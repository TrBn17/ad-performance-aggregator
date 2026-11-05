"""Reproduce measured alternatives to the selected byte-batch default."""

from pathlib import Path

from .core import Totals
from .polars_engine import aggregate as _aggregate
from .polars_engine import query

__all__ = ["aggregate", "query"]


def aggregate(
    path: Path,
    *,
    low_memory: bool = False,
    batch_rows: int | None = None,
    batch_bytes: int | None = None,
) -> Totals:
    """Use the optimized lazy scan unless an explicit batch size is given."""
    return _aggregate(
        path,
        low_memory=low_memory,
        batch_rows=batch_rows,
        batch_bytes=batch_bytes,
    )
