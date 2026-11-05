"""Chunk boundaries and error locations across spawned workers."""

import csv

import pytest

from ad_aggregator.core import FIELDS, InputError
from ad_aggregator.multiprocessing_engine import aggregate
from ad_aggregator.python_engine import aggregate as baseline


@pytest.mark.parametrize("chunk_rows", [1, 2, 5])
def test_multiline_chunk_boundaries(tmp_path, chunk_rows):
    path = tmp_path / "chunks.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.writer(target, lineterminator="\r\n")
        writer.writerow(FIELDS[::-1])
        for i in range(13):
            writer.writerow(
                [
                    f'c,"{i % 3}\r\nend',
                    "2024-02-29",
                    2**63 - 1,
                    i,
                    "0.000001",
                    0,
                ][::-1]
            )
    # Remove the final record terminator to exercise EOF at a boundary.
    path.write_bytes(path.read_bytes()[:-2])
    assert aggregate(path, workers=2, chunk_rows=chunk_rows) == baseline(path)


def test_late_chunk_error_location(tmp_path):
    path = tmp_path / "bad.csv"
    with path.open("w", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(FIELDS)
        writer.writerows([["A\nB", "2024-01-01", 1, 1, 1, 1]] * 7)
        writer.writerow(["A", "2024-02-30", 1, 1, 1, 1])
    with pytest.raises(InputError, match="CSV record 9"):
        aggregate(path, workers=2, chunk_rows=2)


@pytest.mark.parametrize("kwargs", [{"workers": 0}, {"chunk_rows": 0}])
def test_invalid_chunk_configuration(tmp_path, kwargs):
    with pytest.raises(ValueError, match="must be positive"):
        aggregate(tmp_path / "unused.csv", **kwargs)
