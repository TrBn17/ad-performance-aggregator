"""Strict validation and exact arithmetic across memory experiments."""

import csv
from functools import partial

import pytest

from ad_aggregator import polars_baseline, polars_experimental, python_engine
from ad_aggregator.core import FIELDS

ENGINES = [
    polars_baseline.aggregate,
    polars_experimental.aggregate,
    partial(polars_experimental.aggregate, low_memory=True),
    partial(polars_experimental.aggregate, batch_rows=2),
    partial(polars_experimental.aggregate, batch_bytes=53),
]


def write_csv(path, rows, fields=FIELDS):
    with path.open("w", newline="", encoding="utf-8-sig") as target:
        writer = csv.writer(target)
        writer.writerow(fields)
        writer.writerows(rows)
    return path


@pytest.mark.parametrize("engine", ENGINES)
def test_exact_totals_and_csv_boundaries(tmp_path, engine):
    zeros = "0" * 5000
    rows = [
        [
            'A\n"quoted",comma',
            "2024-02-29",
            2**63 - 1,
            1,
            "9223372036854.775807",
            2**63 - 1,
        ],
        [
            'A\n"quoted",comma',
            "2024-02-29",
            2**63 - 1,
            1,
            "9223372036854.775807",
            2**63 - 1,
        ],
        ["é🙂", "0001-01-01", zeros + "1", zeros, zeros + ".000001", 0],
        ["Z", "9999-12-31", 0, 0, "0", 0],
    ]
    path = write_csv(
        tmp_path / "input.csv", [r[::-1] for r in rows], FIELDS[::-1]
    )
    assert engine(path) == python_engine.aggregate(path)
    assert engine(write_csv(path, [])) == {}


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("campaign_id", " \x1c "),
        ("date", "2025-02-29"),
        ("date", "0000-01-01"),
        ("date", "2025-1-01"),
        ("impressions", str(2**63)),
        ("clicks", "-1"),
        ("conversions", "NaN"),
        ("spend", "inf"),
        ("spend", "1e2"),
        ("spend", "0.0000001"),
        ("spend", "9223372036854.775808"),
        ("spend", str(2**122)),
        ("spend", "-0.1"),
        ("campaign_id", "x" * 131073),
        ("clicks", ""),
    ],
    ids=lambda value: str(value)[:40],
)
def test_invalid_after_valid_batches(tmp_path, engine, column, value):
    row = ["A", "2025-01-01", "1", "1", "1.000001", "1"]
    invalid = row.copy()
    invalid[FIELDS.index(column)] = value
    path = write_csv(tmp_path / "input.csv", [row] * 7 + [invalid])
    with pytest.raises(ValueError):
        engine(path)


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize(
    "record",
    [
        b"A,2025-01-01,1,1,1\n",
        b"A,2025-01-01,1,1,1,1,extra\n",
        b'"A"x,2025-01-01,1,1,1,1\n',
        b'"A,2025-01-01,1,1,1,1\n',
        b"\xff,2025-01-01,1,1,1,1\n",
        b"\n",
    ],
)
def test_malformed_batches(tmp_path, engine, record):
    path = tmp_path / "input.csv"
    path.write_bytes((",".join(FIELDS) + "\n").encode() + record)
    with pytest.raises(ValueError):
        engine(path)


@pytest.mark.parametrize("batch_bytes", [1, 2, 7, 53, 4096])
@pytest.mark.parametrize("ending", [b"\n", b"\r\n", b""])
def test_byte_boundaries_and_final_record(tmp_path, batch_bytes, ending):
    path = write_csv(
        tmp_path / "input.csv",
        [
            ['a"\n\r\n,b', "2024-02-29", 1, 2, "0.000001", 3],
            ["é🙂", "2025-01-01", 4, 5, "1.2", 6],
        ],
    )
    data = path.read_bytes().removesuffix(b"\r\n") + ending
    path.write_bytes(data)
    assert polars_experimental.aggregate(
        path, batch_bytes=batch_bytes
    ) == python_engine.aggregate(path)


def test_unfinished_oversized_record_is_bounded(tmp_path):
    path = tmp_path / "input.csv"
    path.write_bytes((",".join(FIELDS) + '\n"').encode() + b"x" * 3200000)
    with pytest.raises(ValueError, match="field length limit"):
        polars_experimental.aggregate(path, batch_bytes=65536)


@pytest.mark.parametrize("batch_bytes", [1, 2, 7, 53, 65536])
@pytest.mark.parametrize("following_rows", [0, 10])
def test_literal_unquoted_quote_does_not_hold_following_rows(
    tmp_path, batch_bytes, following_rows
):
    path = tmp_path / "input.csv"
    path.write_text(
        ",".join(FIELDS)
        + '\nA"B,2025-01-01,1,1,1,1\n'
        + "Z,2025-01-01,1,1,1,1\n" * following_rows,
        encoding="utf-8",
    )
    try:
        expected = polars_baseline.aggregate(path)
    except ValueError:
        with pytest.raises(ValueError):
            polars_experimental.aggregate(path, batch_bytes=batch_bytes)
    else:
        assert (
            polars_experimental.aggregate(path, batch_bytes=batch_bytes)
            == expected
        )
