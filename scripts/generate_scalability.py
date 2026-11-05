"""Generate fixed-width, interleaved CSVs and independent aggregate oracles."""

import argparse
import hashlib
import json
import random
from pathlib import Path

from verify_outputs import expected_csv

from ad_aggregator.core import FIELDS, Totals

SEED = 20261106


def metrics(campaign: int) -> tuple[int, int, int, int]:
    """Deterministic per-row counts and exact spend millionths."""
    impressions = 0 if campaign % 101 == 0 else 100000 + campaign % 10000
    clicks = 0 if impressions == 0 else 100 + campaign % 1000
    spend = 1000001 + (campaign * 7919) % 9000000000
    conversions = 0 if campaign % 97 == 0 else 1 + campaign % 100
    return impressions, clicks, spend, conversions


def campaign_order(campaigns: int, seed: int) -> list[int]:
    """Give every campaign one record per cycle, in seeded shuffled order."""
    order = list(range(campaigns))
    random.Random(seed).shuffle(order)
    return order


def record(campaign: int) -> bytes:
    """Keep IDs and numeric field widths identical across cardinalities."""
    impressions, clicks, spend, conversions = metrics(campaign)
    return (
        f"C{campaign:06d},2025-01-{1 + campaign % 28:02d},"
        f"{impressions:010d},{clicks:07d},"
        f"{spend // 1000000:06d}.{spend % 1000000:06d},"
        f"{conversions:06d}\n"
    ).encode("ascii")


def expected_totals(campaigns: int, rows: int, seed: int) -> Totals:
    """Calculate totals analytically, independently of CSV parsing/grouping."""
    cycles, remainder = divmod(rows, campaigns)
    return {
        f"C{campaign:06d}": tuple(
            value * (cycles + (position < remainder))
            for value in metrics(campaign)
        )
        for position, campaign in enumerate(campaign_order(campaigns, seed))
    }


def canonical_totals(totals: Totals) -> bytes:
    """Use the established benchmark's exact aggregate hash representation."""
    return json.dumps(sorted(totals.items())).encode("utf-8")


def digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def generate_dataset(
    path: Path, campaigns: int, target_bytes: int, seed: int = SEED
) -> dict:
    """Create new files only, within one record of requested byte size."""
    if not 1 <= campaigns <= 1000000:
        raise ValueError("campaigns must be between 1 and 1000000")
    header = (",".join(FIELDS) + "\n").encode("ascii")
    row_bytes = len(record(0))
    if target_bytes < len(header) + campaigns * row_bytes:
        raise ValueError("target size must allow every campaign at least once")
    if path.exists() or path.with_suffix(".expected.json").exists():
        raise FileExistsError(path)
    rows = (target_bytes - len(header) + row_bytes - 1) // row_bytes
    cycles, remainder = divmod(rows, campaigns)
    order = campaign_order(campaigns, seed)
    block = b"".join(record(campaign) for campaign in order)
    with path.open("xb", buffering=1024**2) as target:
        target.write(header)
        for _ in range(cycles):
            target.write(block)
        target.write(block[: remainder * row_bytes])
    totals = expected_totals(campaigns, rows, seed)
    canonical = canonical_totals(totals)
    path.with_suffix(".expected.json").write_bytes(canonical)
    manifest = {
        "generator_version": 1,
        "seed": seed,
        "campaigns": campaigns,
        "rows": rows,
        "row_bytes": row_bytes,
        "rows_per_campaign_min": cycles,
        "rows_per_campaign_max": cycles + bool(remainder),
        "target_bytes": target_bytes,
        "input_bytes": path.stat().st_size,
        "input_sha256": digest(path),
        "cycle_sha256": hashlib.sha256(block).hexdigest(),
        "aggregate_sha256": hashlib.sha256(canonical).hexdigest(),
        "output_sha256": {
            f"top10_{metric.lower()}.csv": hashlib.sha256(
                expected_csv(totals, metric)
            ).hexdigest()
            for metric in ("CTR", "CPA")
        },
        "distribution": "uniform interleaved; seeded shuffled cycle repeated; "
        "last partial cycle follows same order; duplicate records additive",
    }
    path.with_suffix(".manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target-bytes", type=int, default=1043304870)
    parser.add_argument(
        "--campaigns", type=int, nargs="+", default=[1000, 10000, 100000]
    )
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for campaigns in args.campaigns:
        manifest = generate_dataset(
            args.output / f"campaigns-{campaigns}.csv",
            campaigns,
            args.target_bytes,
            args.seed,
        )
        print(json.dumps(manifest), flush=True)


if __name__ == "__main__":
    main()
