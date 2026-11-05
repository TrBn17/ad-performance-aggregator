"""Native lazy expressions, validation, and streaming group aggregation."""

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
    SCALE,
    SPEND_PATTERN,
    InputError,
    Totals,
    check_header,
)


def aggregate(path: Path) -> Totals:
    """Scan strings, validate in native expressions, and sum using Int128."""
    check_header(path)
    try:
        frame = pl.scan_csv(
            path,
            schema_overrides={field: pl.String for field in FIELDS},
            missing_utf8_is_empty_string=True,
            glob=False,
        )
        counts = ["impressions", "clicks", "conversions"]
        numeric = [
            pl.col(name).cast(pl.Int64, strict=False) for name in counts
        ]
        # Lexical validation prevents Decimal parsing from truncating digits.
        spend = (
            pl.col("spend")
            .str.strip_chars_start("0")
            .str.pad_start(1, "0")
            .cast(pl.Decimal(precision=38, scale=6), strict=False)
            * SCALE
        ).cast(pl.Int64, strict=False)
        valid = (
            pl.col("campaign_id").str.contains(NONBLANK_PATTERN)
            & pl.col("date").str.contains(DATE_PATTERN)
            & pl.col("date")
            .str.to_date("%Y-%m-%d", strict=False)
            .is_not_null()
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
        frame = frame.with_columns(
            valid.fill_null(False).not_().alias("_invalid"),
            spend.cast(pl.Int128).alias("spend"),
            *(
                parsed.cast(pl.Int128).alias(name)
                for name, parsed in zip(counts, numeric)
            ),
        )
        result = (
            frame.group_by("campaign_id")
            .agg(
                *(pl.col(name).sum() for name in METRICS),
                pl.col("_invalid").any(),
            )
            .collect(engine="streaming")
        )
    except pl.exceptions.PolarsError as error:
        raise InputError(
            f"Polars could not parse input CSV: {error}"
        ) from error
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
