"""Independent correctness and reproducibility checks for study inputs."""

import importlib
import json
from pathlib import Path

import pytest

from ad_aggregator import polars_baseline, polars_engine, python_engine


@pytest.fixture
def study(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "scripts"))
    return importlib.import_module("generate_scalability")


@pytest.mark.parametrize("campaigns", [1, 7, 101])
def test_generator_matches_independent_parser(tmp_path, study, campaigns):
    path = tmp_path / "input.csv"
    manifest = study.generate_dataset(path, campaigns, 20000, seed=123)
    oracle = study.expected_totals(campaigns, manifest["rows"], 123)
    assert len(oracle) == campaigns
    for aggregate in (
        python_engine.aggregate,
        polars_baseline.aggregate,
        polars_engine.aggregate,
    ):
        assert aggregate(path) == oracle
    assert 20000 <= path.stat().st_size < 20000 + manifest["row_bytes"]
    assert (
        manifest["rows_per_campaign_max"] - manifest["rows_per_campaign_min"]
        <= 1
    )
    assert json.loads(path.with_suffix(".expected.json").read_text()) == (
        json.loads(study.canonical_totals(oracle))
    )


def test_fixed_width_and_known_metrics(study):
    assert study.metrics(0) == (0, 0, 1000001, 0)
    assert study.metrics(1) == (100001, 101, 1007920, 2)
    assert len({len(study.record(i)) for i in [0, 1, 999, 99999, 999999]}) == 1


def test_reproducibility_and_seed(tmp_path, study):
    first = study.generate_dataset(tmp_path / "a.csv", 100, 20000, 42)
    second = study.generate_dataset(tmp_path / "b.csv", 100, 20000, 42)
    third = study.generate_dataset(tmp_path / "c.csv", 100, 20000, 43)
    assert first == second
    assert first["input_sha256"] != third["input_sha256"]


@pytest.mark.parametrize(
    "campaigns,target", [(0, 1000), (-1, 1000), (1000001, 1000), (100, 100)]
)
def test_invalid_generator_arguments(tmp_path, study, campaigns, target):
    path = tmp_path / "input.csv"
    with pytest.raises(ValueError):
        study.generate_dataset(path, campaigns, target)
    assert not path.exists()


def test_generator_does_not_replace_existing_data(tmp_path, study):
    path = tmp_path / "input.csv"
    path.write_bytes(b"preserve source")
    with pytest.raises(FileExistsError):
        study.generate_dataset(path, 10, 20000)
    assert path.read_bytes() == b"preserve source"
