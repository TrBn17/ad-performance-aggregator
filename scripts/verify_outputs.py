"""Audit generated CSVs using independent Decimal ranking and formatting."""

import argparse
import csv
import hashlib
import io
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from pathlib import Path

from ad_aggregator.core import OUTPUT_FIELDS, SCALE, Totals
from ad_aggregator.polars_engine import aggregate


def expected_csv(totals: Totals, metric: str) -> bytes:
    """Build an independent, high-precision reference for the top-ten CSV."""
    with localcontext() as context:
        context.prec = 100
        context.rounding = ROUND_HALF_EVEN
        records = []
        for campaign, (
            impressions,
            clicks,
            spend,
            conversions,
        ) in totals.items():
            ctr = Decimal(clicks) / impressions if impressions else None
            cpa = Decimal(spend) / SCALE / conversions if conversions else None
            records.append(
                (campaign, impressions, clicks, spend, conversions, ctr, cpa)
            )
        if metric == "CTR":
            records.sort(
                key=lambda row: (
                    row[5] is None,
                    -row[5] if row[5] is not None else 0,
                    row[0],
                )
            )
        else:
            records = [row for row in records if row[6] is not None]
            records.sort(key=lambda row: (row[6], row[0]))
        stream = io.StringIO(newline="")
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(OUTPUT_FIELDS)
        for (
            campaign,
            impressions,
            clicks,
            spend,
            conversions,
            ctr,
            cpa,
        ) in records[:10]:
            writer.writerow(
                [
                    campaign,
                    impressions,
                    clicks,
                    f"{Decimal(spend) / SCALE:.2f}",
                    conversions,
                    f"{ctr:.4f}" if ctr is not None else "",
                    f"{cpa:.2f}" if cpa is not None else "",
                ]
            )
        return stream.getvalue().encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/ad_data.csv"))
    parser.add_argument("--outputs", type=Path, nargs="+", required=True)
    args = parser.parse_args()
    totals = aggregate(args.input)
    for metric in ("CTR", "CPA"):
        filename = f"top10_{metric.lower()}.csv"
        reference = expected_csv(totals, metric)
        for output in args.outputs:
            path = output / filename
            if path.read_bytes() != reference:
                raise ValueError(f"CSV differs from Decimal reference: {path}")
            print(f"Verified {path}: {hashlib.sha256(reference).hexdigest()}")
    print(
        "Verified rankings, totals, rounding and CSV bytes: "
        f"{len(totals)} campaigns"
    )


if __name__ == "__main__":
    main()
