import csv
import random
from decimal import Decimal
from fractions import Fraction

import pytest

from ad_aggregator import polars_engine, python_engine
from ad_aggregator.cli import main
from ad_aggregator.core import FIELDS, InputError, fixed, write_results

ENGINES = [python_engine.aggregate, polars_engine.aggregate]


def make_csv(tmp_path, rows, header=FIELDS):
    path = tmp_path / "input.csv"
    with path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.writer(target)
        writer.writerow(header)
        writer.writerows(rows)
    return path


@pytest.mark.parametrize("engine", ENGINES)
def test_reference_and_outputs(tmp_path, engine):
    rows = [
        ["B", "2025-01-01", 10, 2, "1.005", 1],
        ["A", "2024-02-29", 20, 4, "2.000001", 2],
        ["B", "2025-01-01", 10, 2, "1.005", 1],
        ["Z", "2025-01-01", 0, 0, "0", 0],
    ]
    totals = engine(make_csv(tmp_path, rows))
    assert totals == {
        "A": (20, 4, 2000001, 2),
        "B": (20, 4, 2010000, 2),
        "Z": (0, 0, 0, 0),
    }
    write_results(totals, tmp_path / "out")
    with (tmp_path / "out/top10_ctr.csv").open() as source:
        result = list(csv.DictReader(source))
    assert [row["campaign_id"] for row in result] == ["A", "B", "Z"]
    assert result[0]["CTR"] == "0.2000"
    assert result[0]["CPA"] == "1.00"
    assert result[1]["total_spend"] == "2.01"
    assert result[1]["CPA"] == "1.00"  # 1.005, half even
    assert result[2]["CTR"] == result[2]["CPA"] == ""
    with (tmp_path / "out/top10_cpa.csv").open() as source:
        assert [row["campaign_id"] for row in csv.DictReader(source)] == [
            "A",
            "B",
        ]


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("date", "2025-02-29"),
        ("date", "2025-1-01"),
        ("date", "0000-01-01"),
        ("campaign_id", " "),
        ("impressions", "-1"),
        ("clicks", "1.0"),
        ("clicks", ""),
        ("conversions", "NaN"),
        ("spend", "NaN"),
        ("spend", "inf"),
        ("spend", "-0.01"),
        ("spend", "0.0000001"),
        ("spend", "1e2"),
        ("impressions", str(2**63)),
        ("spend", "9223372036854.775808"),
        ("date", "2025-01-01x"),
        ("clicks", "１２"),
    ],
)
def test_invalid_values(tmp_path, engine, column, value):
    row = ["A", "2025-01-01", "10", "1", "1.00", "1"]
    row[FIELDS.index(column)] = value
    with pytest.raises(InputError):
        engine(make_csv(tmp_path, [row]))


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize("rows", [[], [["A", "2025-01-01", 1, 1, 1, 1]]])
def test_reordered_header(tmp_path, engine, rows):
    result = engine(
        make_csv(tmp_path, [row[::-1] for row in rows], FIELDS[::-1])
    )
    assert len(result) == len(rows)


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize(
    "text",
    [
        "",
        "a,b\n",
        ",".join(FIELDS) + "\nA,2025-01-01,1\n",
        ",".join(FIELDS) + "\nA,2025-01-01,1,1,1,1,extra\n",
    ],
)
def test_bad_schema_or_width(tmp_path, engine, text):
    path = tmp_path / "bad.csv"
    path.write_text(text)
    with pytest.raises((InputError, csv.Error)):
        engine(path)


@pytest.mark.parametrize("engine", ENGINES)
def test_header_only(tmp_path, engine):
    path = make_csv(tmp_path, [])
    assert engine(path) == {}
    write_results({}, tmp_path / "out")
    assert len((tmp_path / "out/top10_ctr.csv").read_text().splitlines()) == 1


@pytest.mark.parametrize("engine", ENGINES)
def test_blank_records_rejected(tmp_path, engine):
    with pytest.raises(InputError):
        engine(make_csv(tmp_path, [[], []]))


def test_randomized_independent_reference(tmp_path):
    rng = random.Random(42)
    rows = [
        [
            f"C{rng.randrange(30):02}",
            "2025-01-01",
            rng.randrange(100),
            rng.randrange(30),
            f"{rng.randrange(10000) / 100:.2f}",
            rng.randrange(10),
        ]
        for _ in range(1000)
    ]
    expected = {}
    for campaign in {row[0] for row in rows}:
        subset = [row for row in rows if row[0] == campaign]
        expected[campaign] = (
            sum(row[2] for row in subset),
            sum(row[3] for row in subset),
            int(sum(Decimal(row[4]) for row in subset) * 1000000),
            sum(row[5] for row in subset),
        )
    path = make_csv(tmp_path, rows)
    for index, engine in enumerate(ENGINES):
        totals = engine(path)
        assert totals == expected
        write_results(totals, tmp_path / str(index))
    for filename in ["top10_ctr.csv", "top10_cpa.csv"]:
        assert (tmp_path / "0" / filename).read_bytes() == (
            tmp_path / "1" / filename
        ).read_bytes()
        assert len((tmp_path / "0" / filename).read_text().splitlines()) == 11


@pytest.mark.parametrize("engine", ENGINES)
def test_large_sums_quotes_and_bom(tmp_path, engine):
    rows = [['A,"B\nC', "9999-12-31", 2**63 - 1, 1, "0.000001", 0]] * 2
    path = make_csv(tmp_path, rows)
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
    assert engine(path) == {'A,"B\nC': (2 * (2**63 - 1), 2, 2, 0)}


def test_ranking_before_rounding(tmp_path):
    totals = {"A": (100000, 1, 1000001, 1), "B": (100000, 2, 1000000, 1)}
    write_results(totals, tmp_path)
    for filename in ["top10_ctr.csv", "top10_cpa.csv"]:
        with (tmp_path / filename).open() as source:
            assert next(csv.DictReader(source))["campaign_id"] == "B"
    assert fixed(Fraction(1005, 1000), 2) == "1.00"
    assert fixed(Fraction(1015, 1000), 2) == "1.02"


@pytest.mark.parametrize("engine", ["python", "polars"])
def test_cli(tmp_path, engine, capsys):
    path = make_csv(tmp_path, [["A", "2025-01-01", 10, 1, 1, 1]])
    assert (
        main(
            [
                "--input",
                str(path),
                "--output",
                str(tmp_path / "out"),
                "--engine",
                engine,
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "--input",
                str(tmp_path / "missing"),
                "--output",
                str(tmp_path / "no"),
                "--engine",
                engine,
            ]
        )
        == 1
    )
    assert "error:" in capsys.readouterr().err
    assert not (tmp_path / "no").exists()


def test_cli_preserves_input_and_existing_output_on_invalid_data(tmp_path):
    path = make_csv(tmp_path, [["A", "2025-01-01", -1, 1, 1, 1]])
    existing = tmp_path / "top10_ctr.csv"
    existing.write_text("keep this")
    assert main(["--input", str(path), "--output", str(tmp_path)]) == 1
    assert existing.read_text() == "keep this"
    existing.write_bytes(path.read_bytes())
    before = existing.read_bytes()
    assert main(["--input", str(existing), "--output", str(tmp_path)]) == 1
    assert existing.read_bytes() == before


@pytest.mark.parametrize("engine", ENGINES)
def test_numeric_boundary_and_early_year(tmp_path, engine):
    row = ["A", "0001-01-01", "00010", "0001", "9223372036854.775807", "0"]
    assert engine(make_csv(tmp_path, [row])) == {"A": (10, 1, 2**63 - 1, 0)}


def test_default_engine(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(
        polars_engine, "aggregate", lambda path: called.append(path) or {}
    )
    path = tmp_path / "input.csv"
    assert main(["--input", str(path), "--output", str(tmp_path / "out")]) == 0
    assert called == [path]
