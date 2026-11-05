"""Bounded CSV batches, native validation and exact campaign aggregation."""

from collections.abc import Iterator
from pathlib import Path

import polars as pl

from .core import (
    DATE_PATTERN,
    FIELDS,
    INTEGER_PATTERN,
    MAX_FIELD_CHARS,
    MAX_VALUE,
    METRICS,
    NONBLANK_PATTERN,
    SPEND_PATTERN,
    InputError,
    Totals,
    check_header,
)


class _UseBaseline(Exception):
    """The pinned CSV parser cannot safely batch this uncommon syntax."""


def query(frame: pl.LazyFrame) -> pl.LazyFrame:
    """Validate raw strings once, aggregate with exact wide accumulators."""
    return _query(frame)


def aggregate(
    path: Path,
    *,
    low_memory: bool = False,
    batch_rows: int | None = None,
    batch_bytes: int | None = 32 * 1024**2,
) -> Totals:
    """Aggregate in 32 MiB byte batches by default; retain tuning for studies.

    Batch sizes limit input buffers, not total RSS. Quoted records can extend
    a batch; campaign totals consume memory proportional to unique campaigns.
    Set batch_bytes=None for a native lazy scan, or also pass batch_rows for
    the synchronous native row-batch reader.
    """
    if batch_bytes is not None and batch_bytes < 1:
        raise ValueError("batch_bytes must be positive")
    if batch_rows is not None and batch_rows < 1:
        raise ValueError("batch_rows must be positive")
    check_header(path)
    try:
        frame = pl.scan_csv(
            path,
            schema_overrides={field: pl.String for field in FIELDS},
            missing_utf8_is_empty_string=True,
            glob=False,
            low_memory=low_memory,
        )
        if batch_bytes is None and batch_rows is None:
            result = query(frame).collect(engine="streaming")
            return _totals(result)
        totals: Totals = {}
        batches = (
            _byte_batches(path, batch_bytes)
            if batch_bytes is not None
            else _row_batches(path, batch_rows)
        )
        for batch in batches:
            partial = _totals(query(batch.lazy()).collect())
            for campaign, values in partial.items():
                previous = totals.get(campaign, (0, 0, 0, 0))
                totals[campaign] = tuple(
                    a + b for a, b in zip(previous, values)
                )
            # Release this frame before parsing the next batch.
            del batch
        return totals
    except _UseBaseline:
        from .polars_baseline import aggregate as baseline

        return baseline(path)
    except pl.exceptions.PolarsError as error:
        raise InputError(
            f"Polars could not parse input CSV: {error}"
        ) from error


def _row_batches(path: Path, rows: int) -> Iterator[pl.DataFrame]:
    reader = pl.read_csv_batched(
        path,
        batch_size=rows,
        schema_overrides={field: pl.String for field in FIELDS},
        missing_utf8_is_empty_string=True,
    )
    while batches := reader.next_batches(1):
        yield from batches


def _byte_batches(path: Path, batch_bytes: int) -> Iterator[pl.DataFrame]:
    """Cut only outside quoted CSV fields; release each parsed byte batch."""
    if batch_bytes < 1:
        raise ValueError("batch_bytes must be positive")
    with path.open("rb") as source:
        header = source.readline()
        pending = b""
        while block := source.read(batch_bytes):
            pending += block
            end = _last_record_end(pending)
            if end < 0:
                _check_record_buffer(pending)
                continue
            yield _read_bytes(header + pending[: end + 1])
            pending = pending[end + 1 :]
            _check_record_buffer(pending)
        if pending:
            yield _read_bytes(header + pending)


def _last_record_end(data: bytes) -> int:
    """Find a newline outside quoted fields, allowing literal bare quotes."""
    quoted = False
    outside_start = 0
    last_end = -1
    position = data.find(b'"')
    while position >= 0:
        if quoted:
            if data[position + 1 : position + 2] == b'"':
                position = data.find(b'"', position + 2)
                continue
            quoted = False
            outside_start = position + 1
        elif position == 0 or data[position - 1] in (44, 10):
            # A quote opens a field only at the start of a record or after
            # a comma. Quotes inside unquoted fields are literal CSV data.
            end = data.rfind(b"\n", outside_start, position)
            if end >= 0:
                last_end = end
            quoted = True
        else:
            # Polars 1.35.2 handles bare quotes differently depending on the
            # surrounding input. Preserve that behavior with its original
            # whole-file parser rather than accepting/rejecting by batch size.
            raise _UseBaseline
        position = data.find(b'"', position + 1)
    if not quoted:
        end = data.rfind(b"\n", outside_start)
        if end >= 0:
            last_end = end
    return last_end


def _check_record_buffer(pending: bytes) -> None:
    # UTF-8 uses at most four bytes per character. Include delimiters,
    # enclosing quotes and CRLF; larger unfinished records cannot be valid.
    if len(pending) > len(FIELDS) * (MAX_FIELD_CHARS * 4 + 3) + 2:
        raise InputError("CSV record exceeds the field length limit")


def _read_bytes(data: bytes) -> pl.DataFrame:
    return pl.read_csv(
        data,
        schema_overrides={field: pl.String for field in FIELDS},
        missing_utf8_is_empty_string=True,
    )


def _query(frame: pl.LazyFrame) -> pl.LazyFrame:
    counts = ["impressions", "clicks", "conversions"]
    numeric = [pl.col("_" + name) for name in counts]
    # Lexical validation prevents Decimal parsing from truncating digits.
    parsed_spend = (
        pl.col("spend")
        .str.strip_chars_start("0")
        .str.pad_start(1, "0")
        .cast(pl.Decimal(precision=38, scale=6), strict=False)
        .to_physical()
        .cast(pl.Int64, strict=False)
    )
    frame = frame.with_columns(
        parsed_spend.alias("_spend"),
        *(
            pl.col(name).cast(pl.Int64, strict=False).alias("_" + name)
            for name in counts
        ),
    )
    spend = pl.col("_spend")
    valid = (
        pl.col("campaign_id").str.contains(NONBLANK_PATTERN)
        & pl.col("date").str.contains(DATE_PATTERN)
        & pl.col("date").str.to_date("%Y-%m-%d", strict=False).is_not_null()
        & (pl.col("date").str.slice(0, 4) != "0000")
        & pl.col("spend").str.contains(SPEND_PATTERN)
        & spend.is_not_null()
        & (spend >= 0)
        & (spend <= MAX_VALUE)
    )
    for name, parsed in zip(counts, numeric):
        valid = (
            valid
            & pl.col(name).str.contains(INTEGER_PATTERN)
            & parsed.is_not_null()
        )
    valid = valid & pl.all_horizontal(
        pl.col(name).str.len_chars() <= MAX_FIELD_CHARS for name in FIELDS
    )
    frame = frame.select(
        "campaign_id",
        valid.fill_null(False).not_().alias("_invalid"),
        spend.alias("spend"),
        *(parsed.alias(name) for name, parsed in zip(counts, numeric)),
    )
    return frame.group_by("campaign_id").agg(
        *(pl.col(name).cast(pl.Int128).sum() for name in METRICS),
        pl.col("_invalid").any(),
    )


def _totals(result: pl.DataFrame) -> Totals:
    if result["_invalid"].any():
        raise InputError(
            "Invalid CSV records: check campaign_id, date, counts, "
            f"field length (<={MAX_FIELD_CHARS} characters), "
            "and spend (<=6 decimal places and signed 64-bit storage range)"
        )
    return {
        row[0]: tuple(row[1:5])
        for row in result.select("campaign_id", *METRICS).iter_rows()
    }
