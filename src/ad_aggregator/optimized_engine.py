"""Streaming validation with fewer temporary objects in the row loop."""

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
    """Stream CSV records, retaining only campaign totals and valid dates."""
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.reader(source, strict=True)
        return aggregate_rows(reader, next(reader, None))


def aggregate_rows(
    rows: Iterable[list[str]],
    header: list[str] | None,
    start_record: int = 2,
) -> Totals:
    """Validate all rows; start_record preserves locations across chunks."""
    header = validate_header(header)
    ci, di, ii, ki, si, vi = (header.index(field) for field in FIELDS)
    integer_match = re.compile(INTEGER_PATTERN, re.ASCII).fullmatch
    spend_match = re.compile(SPEND_PATTERN, re.ASCII).fullmatch
    date_match = re.compile(DATE_PATTERN, re.ASCII).fullmatch
    valid_dates: set[str] = set()
    totals: dict[str, list[int]] = {}
    for record_number, row in enumerate(rows, start_record):
        try:
            if len(row) != 6:
                raise ValueError("expected six fields")
            campaign, day = row[ci], row[di]
            impressions, clicks = row[ii], row[ki]
            spend, conversions = row[si], row[vi]
            if (
                max(
                    len(campaign),
                    len(day),
                    len(impressions),
                    len(clicks),
                    len(spend),
                    len(conversions),
                )
                > MAX_FIELD_CHARS
            ):
                raise ValueError(f"field exceeds {MAX_FIELD_CHARS} characters")
            if not campaign.strip():
                raise ValueError("campaign_id must not be blank")
            if day not in valid_dates:
                if not date_match(day):
                    raise ValueError("date must be YYYY-MM-DD")
                date.fromisoformat(day)
                valid_dates.add(day)
            if (
                not integer_match(impressions)
                or not integer_match(clicks)
                or not integer_match(conversions)
            ):
                raise ValueError("counts must be nonnegative integers")
            if not spend_match(spend):
                raise ValueError(
                    "spend must be nonnegative decimal with <=6 places"
                )
            whole, _, fraction = spend.partition(".")
            impression_value = int(impressions.lstrip("0") or "0")
            click_value = int(clicks.lstrip("0") or "0")
            spend_value = int(whole.lstrip("0") or "0") * SCALE + int(
                fraction.ljust(6, "0")
            )
            conversion_value = int(conversions.lstrip("0") or "0")
            if (
                max(
                    impression_value,
                    click_value,
                    spend_value,
                    conversion_value,
                )
                > MAX_VALUE
            ):
                raise ValueError(
                    "value exceeds signed 64-bit range in storage units"
                )
        except ValueError as error:
            raise InputError(f"CSV record {record_number}: {error}") from error
        current = totals.get(campaign)
        if current is None:
            totals[campaign] = [
                impression_value,
                click_value,
                spend_value,
                conversion_value,
            ]
        else:
            current[0] += impression_value
            current[1] += click_value
            current[2] += spend_value
            current[3] += conversion_value
    return {key: tuple(values) for key, values in totals.items()}
