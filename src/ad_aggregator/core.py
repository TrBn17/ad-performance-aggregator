"""Shared schema, exact arithmetic, and deterministic presentation."""

import csv
import tempfile
from fractions import Fraction
from pathlib import Path
from typing import Iterable

FIELDS = [
    "campaign_id",
    "date",
    "impressions",
    "clicks",
    "spend",
    "conversions",
]
METRICS = ["impressions", "clicks", "spend", "conversions"]
OUTPUT_FIELDS = [
    "campaign_id",
    "total_impressions",
    "total_clicks",
    "total_spend",
    "total_conversions",
    "CTR",
    "CPA",
]
SCALE = 1_000_000
MAX_VALUE = 2**63 - 1
INTEGER_PATTERN = r"^[0-9]+$"
SPEND_PATTERN = r"^[0-9]+(?:\.[0-9]{1,6})?$"
DATE_PATTERN = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
# Match Python's csv parser resource limit in the native engine as well.
MAX_FIELD_CHARS = 131072
NONBLANK_PATTERN = r"[^\s\x1c-\x1f]"
Totals = dict[str, tuple[int, int, int, int]]


class InputError(ValueError):
    """Input does not satisfy the documented CSV contract."""


def validate_header(header: list[str] | None) -> list[str]:
    """Require exactly the schema columns, allowing any column order."""
    if (
        header is None
        or len(header) != len(FIELDS)
        or set(header) != set(FIELDS)
    ):
        raise InputError(
            f"Expected CSV header containing exactly: {', '.join(FIELDS)}"
        )
    return header


def check_header(path: Path) -> None:
    """Read and validate a CSV header without scanning data records."""
    with path.open(encoding="utf-8-sig", newline="") as source:
        validate_header(next(csv.reader(source, strict=True), None))


def fixed(value: Fraction, places: int) -> str:
    """Format an exact nonnegative ratio with round-half-even."""
    quotient, remainder = divmod(
        value.numerator * 10**places, value.denominator
    )
    if remainder * 2 > value.denominator or (
        remainder * 2 == value.denominator and quotient % 2
    ):
        quotient += 1
    whole, fraction = divmod(quotient, 10**places)
    return f"{whole}.{fraction:0{places}d}"


def write_results(totals: Totals, output: Path) -> None:
    """Write top tens ranked on exact ratios with campaign ID tie breaks."""
    ctr = sorted(
        totals,
        key=lambda key: (
            totals[key][0] == 0,
            -Fraction(totals[key][1], totals[key][0]) if totals[key][0] else 0,
            key,
        ),
    )[:10]
    cpa = sorted(
        (key for key in totals if totals[key][3]),
        key=lambda key: (
            Fraction(totals[key][2], totals[key][3]),
            key,
        ),
    )[:10]
    output.mkdir(parents=True, exist_ok=True)
    # Stage both files before publication; replacement also breaks hardlinks
    # instead of truncating another name for the source file.
    with tempfile.TemporaryDirectory(
        prefix=".ad-aggregate-", dir=output
    ) as temp:
        staging = Path(temp)
        for filename, keys in (("top10_ctr.csv", ctr), ("top10_cpa.csv", cpa)):
            _write_csv(staging / filename, keys, totals)
        for filename in ("top10_ctr.csv", "top10_cpa.csv"):
            (staging / filename).replace(output / filename)


def _write_csv(path: Path, keys: Iterable[str], totals: Totals) -> None:
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.writer(target, lineterminator="\n")
        writer.writerow(OUTPUT_FIELDS)
        for key in keys:
            impressions, clicks, spend, conversions = totals[key]
            writer.writerow(
                [
                    key,
                    impressions,
                    clicks,
                    fixed(Fraction(spend, SCALE), 2),
                    conversions,
                    fixed(Fraction(clicks, impressions), 4)
                    if impressions
                    else "",
                    fixed(Fraction(spend, SCALE * conversions), 2)
                    if conversions
                    else "",
                ]
            )
