"""Save optimized and physical plans using the installed pinned Polars."""

from pathlib import Path
from unittest.mock import patch

import polars as pl

from ad_aggregator import polars_baseline, polars_engine
from ad_aggregator.core import FIELDS


def main() -> None:
    plans = {}

    class Captured(Exception):
        pass

    def capture(frame, *args, **kwargs):
        plans["baseline"] = frame
        raise Captured

    with patch.object(pl.LazyFrame, "collect", capture):
        try:
            polars_baseline.aggregate(Path("data/ad_data.csv"))
        except Captured:
            pass
    plans["expressions"] = polars_engine.query(
        pl.scan_csv(
            "data/ad_data.csv",
            schema_overrides=dict.fromkeys(FIELDS, pl.String),
            missing_utf8_is_empty_string=True,
            glob=False,
        )
    )
    plans["batch"] = polars_engine.query(
        pl.DataFrame(
            {field: pl.Series([], dtype=pl.String) for field in FIELDS}
        ).lazy()
    )
    for name, plan in plans.items():
        prefix = Path("benchmarks") / f"polars-{name}"
        prefix.with_suffix(".plan.txt").write_text(
            "\n".join(
                line.rstrip()
                for line in plan.explain(engine="streaming").splitlines()
            )
            + "\n",
            encoding="utf-8",
        )
        prefix.with_suffix(".physical.dot").write_text(
            plan.show_graph(
                raw_output=True,
                show=False,
                engine="streaming",
                plan_stage="physical",
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
