"""Standard-library CSV streaming and dictionary aggregation."""

import csv
import re
from collections.abc import Iterable
from datetime import date
from pathlib import Path

from .core import (
    DATE_PATTERN,
    FIELDS,
    INTEGER_PATTERN,
    MAX_FIELD_CHARS,
    MAX_VALUE,
    SCALE,
    SPEND_PATTERN,
    InputError,
    Totals,
    validate_header,
)


def aggregate(path: Path) -> Totals:
    """Validate every record and accumulate exact per-campaign totals."""
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.reader(source, strict=True)
        return aggregate_rows(reader, next(reader, None))


def aggregate_rows(
    rows: Iterable[list[str]], header: list[str] | None
) -> Totals:
    """Validate and aggregate a row iterable independently of filesystem I/O.

    Error locations are logical CSV record numbers, including the header.
    """
    header = validate_header(header)
    totals: dict[str, list[int]] = {}
    # Dates repeat heavily; cache only valid dates, bounded by calendar range.
    valid_dates: set[str] = set()
    integer = re.compile(INTEGER_PATTERN, re.ASCII)
    spend_pattern = re.compile(SPEND_PATTERN, re.ASCII)
    date_pattern = re.compile(DATE_PATTERN, re.ASCII)
    indices = [header.index(field) for field in FIELDS]
    for record_number, row in enumerate(rows, start=2):
        try:
            if len(row) != len(FIELDS):
                raise ValueError("expected six fields")
            if max(map(len, row)) > MAX_FIELD_CHARS:
                raise ValueError(f"field exceeds {MAX_FIELD_CHARS} characters")
            campaign, day, impressions, clicks, spend, conversions = (
                row[index] for index in indices
            )
            if not campaign.strip():
                raise ValueError("campaign_id must not be blank")
            if day not in valid_dates:
                if not date_pattern.fullmatch(day):
                    raise ValueError("date must be YYYY-MM-DD")
                date.fromisoformat(day)
                valid_dates.add(day)
            counts = (impressions, clicks, conversions)
            if not all(integer.fullmatch(value) for value in counts):
                raise ValueError("counts must be nonnegative integers")
            if not spend_pattern.fullmatch(spend):
                raise ValueError(
                    "spend must be nonnegative decimal with <=6 places"
                )
            whole, _, fraction = spend.partition(".")
            values = [
                int(impressions.lstrip("0") or "0"),
                int(clicks.lstrip("0") or "0"),
                int(whole.lstrip("0") or "0") * SCALE
                + int(fraction.ljust(6, "0")),
                int(conversions.lstrip("0") or "0"),
            ]
            if any(value > MAX_VALUE for value in values):
                raise ValueError(
                    "value exceeds signed 64-bit range in storage units"
                )
        except ValueError as error:
            raise InputError(f"CSV record {record_number}: {error}") from error
        current = totals.get(campaign)
        if current is None:
            totals[campaign] = values
        else:
            for index, value in enumerate(values):
                current[index] += value
    return {key: tuple(values) for key, values in totals.items()}
