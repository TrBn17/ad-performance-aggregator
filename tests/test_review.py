"""Regression and independent ranking checks from the implementation review."""

import csv
import hashlib
import random
import subprocess
import sys
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from ad_aggregator import (
    core,
    multiprocessing_engine,
    optimized_engine,
    polars_engine,
    python_engine,
)
from ad_aggregator.cli import main
from ad_aggregator.core import FIELDS, OUTPUT_FIELDS, write_results

ENGINES = [
    python_engine.aggregate,
    polars_engine.aggregate,
    optimized_engine.aggregate,
    multiprocessing_engine.aggregate,
]
HEADER = ",".join(FIELDS) + "\n"


def write_input(path: Path, rows: list[list]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(FIELDS)
        writer.writerows(rows)
    return path


@pytest.mark.parametrize("engine", ENGINES)
def test_literal_filename(tmp_path, engine):
    path = write_input(
        tmp_path / "campaign[1].csv", [["A", "2025-01-01", 1, 1, 1, 1]]
    )
    assert engine(path) == {"A": (1, 1, 1000000, 1)}


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize(
    "record",
    [
        "A,2025-01-01,1,1,1,1,\n",
        "A,2025-01-01,1,1,1\n",
        '"A"x,2025-01-01,1,1,1,1\n',
        '"A,2025-01-01,1,1,1,1\n',
        "\nA,2025-01-01,1,1,1,1\n",
        "A,2025-01-01,1,1,1,1\n\n",
        "\x1c,2025-01-01,1,1,1,1\n",
        " \x1c ,2025-01-01,1,1,1,1\n",
    ],
)
def test_malformed_records(tmp_path, engine, record):
    path = tmp_path / "input.csv"
    path.write_text(HEADER + record, encoding="utf-8", newline="")
    with pytest.raises((ValueError, csv.Error)):
        engine(path)


@pytest.mark.parametrize("engine", ENGINES)
def test_invalid_utf8(tmp_path, engine):
    path = tmp_path / "input.csv"
    path.write_bytes(HEADER.encode() + b"\xff,2025-01-01,1,1,1,1\n")
    assert (
        main(
            [
                "--input",
                str(path),
                "--output",
                str(tmp_path / "out"),
                "--engine",
                {
                    python_engine.aggregate: "python",
                    polars_engine.aggregate: "polars",
                    optimized_engine.aggregate: "optimized",
                    multiprocessing_engine.aggregate: "multiprocessing",
                }[engine],
            ]
        )
        == 1
    )
    assert not (tmp_path / "out").exists()


def test_independent_rankings_and_shuffled_equivalence(tmp_path):
    rng = random.Random(912)
    rows = [
        [
            f"C{i:02}",
            "2025-01-01",
            100000 + i,
            2000 + i,
            f"{100000 + i * 5}.000001",
            i % 7,
        ]
        for i in range(25)
    ]
    # Equal ratios straddle the top-ten boundary; IDs decide membership.
    rows += [[f"T{i:02}", "2025-01-01", 10, 10, "0.01", 10] for i in range(12)]
    rows += [["ZERO", "2025-01-01", 0, 0, "0", 0]]
    reference = {r[0]: r for r in rows}
    with localcontext() as context:
        context.prec = 80
        expected_ctr = sorted(
            reference,
            key=lambda key: (
                reference[key][2] == 0,
                -Decimal(reference[key][3]) / Decimal(reference[key][2])
                if reference[key][2]
                else Decimal(0),
                key,
            ),
        )[:10]
        expected_cpa = sorted(
            (key for key in reference if reference[key][5]),
            key=lambda key: (
                Decimal(reference[key][4]) / Decimal(reference[key][5]),
                key,
            ),
        )[:10]
    hashes = []
    for index, engine in enumerate(ENGINES * 2):
        rng.shuffle(rows)
        source = write_input(tmp_path / "input.csv", rows)
        destination = tmp_path / str(index)
        write_results(engine(source), destination)
        current = []
        for filename, expected in [
            ("top10_ctr.csv", expected_ctr),
            ("top10_cpa.csv", expected_cpa),
        ]:
            path = destination / filename
            with path.open(encoding="utf-8", newline="") as stream:
                reader = csv.DictReader(stream)
                assert reader.fieldnames == OUTPUT_FIELDS
                assert [r["campaign_id"] for r in reader] == expected
            current.append(hashlib.sha256(path.read_bytes()).hexdigest())
        hashes.append(current)
    assert all(value == hashes[0] for value in hashes)


def test_output_hardlink_cannot_modify_source(tmp_path):
    source = write_input(
        tmp_path / "input.csv", [["A", "2025-01-01", 1, 1, 1, 1]]
    )
    output = tmp_path / "out"
    output.mkdir()
    (output / "top10_ctr.csv").hardlink_to(source)
    before = source.read_bytes()
    main(["--input", str(source), "--output", str(output)])
    assert source.read_bytes() == before


@pytest.mark.parametrize("engine", ENGINES)
def test_field_resource_limit(tmp_path, engine):
    source = write_input(
        tmp_path / "input.csv",
        [["A" * 131073, "2025-01-01", 1, 1, 1, 1]],
    )
    with pytest.raises((ValueError, csv.Error)):
        engine(source)


def test_failed_staging_preserves_existing_files(tmp_path, monkeypatch):
    for name in ("top10_ctr.csv", "top10_cpa.csv"):
        (tmp_path / name).write_text("keep this", encoding="utf-8")
    original = core._write_csv

    def fail_second(path, keys, totals):
        if path.name == "top10_cpa.csv":
            raise OSError("simulated disk failure")
        original(path, keys, totals)

    monkeypatch.setattr(core, "_write_csv", fail_second)
    with pytest.raises(OSError, match="simulated disk failure"):
        write_results({"A": (1, 1, 1000000, 1)}, tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "top10_cpa.csv",
        "top10_ctr.csv",
    ]
    for path in tmp_path.iterdir():
        assert path.read_text() == "keep this"


@pytest.mark.parametrize("engine", ENGINES)
def test_long_leading_zeros(tmp_path, engine):
    zeros = "0" * 5000
    source = write_input(
        tmp_path / "input.csv",
        [
            ["A", "2025-01-01", zeros + "1", zeros, zeros + "1.000001", "1"],
        ],
    )
    assert engine(source) == {"A": (1, 0, 1000001, 1)}


@pytest.mark.parametrize("engine", ENGINES)
def test_spend_cannot_wrap_decimal_storage(tmp_path, engine):
    units = 2**122
    spend = f"{units // 1000000}.{units % 1000000:06d}"
    source = write_input(
        tmp_path / "input.csv",
        [
            ["A", "2025-01-01", "1", "1", spend, "1"],
        ],
    )
    with pytest.raises(ValueError):
        engine(source)


def test_rows_without_filesystem():
    assert python_engine.aggregate_rows(
        iter(
            [
                ["A", "2025-01-01", "10", "2", "1.005", "1"],
                ["A", "2025-01-01", "20", "3", "2.005", "0"],
            ]
        ),
        FIELDS,
    ) == {"A": (30, 5, 3010000, 1)}
    with pytest.raises(ValueError, match="record 2"):
        python_engine.aggregate_rows(iter([["A"]]), FIELDS)


@pytest.mark.parametrize("entry", ["script", "module", "console"])
@pytest.mark.parametrize(
    "engine", ["python", "polars", "optimized", "multiprocessing"]
)
def test_cli_subprocess(tmp_path, entry, engine):
    if entry == "script":
        command = [sys.executable, "aggregator.py"]
    elif entry == "module":
        command = [sys.executable, "-m", "ad_aggregator"]
    else:
        suffix = ".exe" if sys.platform == "win32" else ""
        command = [
            str(Path(sys.executable).with_name("ad-aggregate" + suffix))
        ]
    source = write_input(
        tmp_path / "input.csv",
        [
            ["A", "2025-01-01", 10, 2, "1.005", 1],
        ],
    )
    args = [
        "--input",
        str(source),
        "--output",
        str(tmp_path / "out"),
        "--engine",
        engine,
    ]
    completed = subprocess.run(command + args, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    with (tmp_path / "out/top10_ctr.csv").open() as stream:
        assert list(csv.DictReader(stream)) == [
            {
                "campaign_id": "A",
                "total_impressions": "10",
                "total_clicks": "2",
                "total_spend": "1.00",
                "total_conversions": "1",
                "CTR": "0.2000",
                "CPA": "1.00",
            }
        ]
    help_result = subprocess.run(
        command + ["--help"], capture_output=True, text=True
    )
    assert help_result.returncode == 0 and "--engine" in help_result.stdout
    bad = subprocess.run(
        command + args + ["--engine", "unknown"],
        capture_output=True,
        text=True,
    )
    assert bad.returncode == 2 and "invalid choice" in bad.stderr
