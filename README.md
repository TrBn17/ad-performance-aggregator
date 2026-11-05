# FLINTERS ad performance aggregator

Python 3.12+ CLI that generates [top10_ctr.csv](results/top10_ctr.csv) and
[top10_cpa.csv](results/top10_cpa.csv). See [REQUIREMENTS.md](REQUIREMENTS.md)
for the challenge specification.

## Setup and usage

Install [uv](https://docs.astral.sh/uv/), download the
[dataset archive](https://github.com/flinters-vietnam/recruitment/blob/main/fv-sec-001-software-engineer-challenge/ad_data.csv.zip),
and extract it to `data/ad_data.csv`. The dataset is excluded from Git.

```sh
uv sync --frozen --extra dev --python 3.12
uv run --no-sync ad-aggregate --input data/ad_data.csv --output results/
# Select the standard-library baseline:
uv run --no-sync ad-aggregate --engine python --input data/ad_data.csv --output results/python/
```

`--engine python|polars` defaults to **polars**. Equivalent entry points are
`python aggregator.py` and `python -m ad_aggregator` in the installed environment.

## Implementation and behavior

- **Python:** standard-library CSV streaming and dictionary aggregation.
- **Polars:** LazyFrame scanning, native validation and grouping, with streaming
  execution requested. Both engines share exact ranking and CSV formatting.
- Input must match the six-column schema, with real `YYYY-MM-DD` dates,
  nonblank campaign IDs, nonnegative integer counts, and plain decimal spend
  with at most six fractional places. Each input count and spend in millionths
  must fit Int64; fields are limited to 131,072 characters. Invalid records fail
  the run. UTF-8 BOMs and reordered columns are supported; duplicates are additive.
- Rankings use unrounded ratios, with campaign ID ascending as the tie-breaker.
  Zero-impression CTR is blank and ranks last; zero-conversion campaigns are
  excluded from CPA rankings. Spend/CPA use two decimal places and CTR four,
  with round-half-even formatting. Outputs use UTF-8 and LF newlines.
- Validation and staging finish before output replacement. Publication is atomic
  per file, not across both files. Errors return a nonzero exit status.

## Measured performance

Full input: **1,043,304,870 bytes**, 50 campaigns. Two runs per engine on Windows 11,
Intel i7-11700F (8 cores/16 threads), 31.86 GiB RAM, Python 3.12.12 and Polars 1.35.2.
Measured on 2026-11-05 with 16 Polars threads and a warm OS file cache.

| Engine | Median time | Maximum peak RSS | Median run throughput |
| --- | ---: | ---: | ---: |
| Python | 222.504 s | 23.2 MiB | 4.51 MiB/s |
| Polars | 5.471 s | 1,963.9 MiB | 185.26 MiB/s |

**Polars is the default: about 40.7x faster.** Choose Python when memory is limited.
Streaming does not guarantee RSS below input size. Both retain campaign totals;
Python also caches valid dates. All four runs produced identical totals and CSVs.

Timings include subprocess startup, imports, validation, aggregation, output, and
result hashing. RSS is the OS process high-water mark, including native memory.
Background desktop load was uncontrolled; two repetitions show timing variation.
Commands, individual runs, source/input hashes and hardware details are in
[review-results.json](benchmarks/review-results.json). Earlier measurements and
optimization trials remain in `benchmarks/` as supporting evidence.

## Verification

```sh
uv run --no-sync pytest -q
uv run --no-sync ruff check src scripts tests aggregator.py
uv run --no-sync ruff format --check src scripts tests aggregator.py
uv run --no-sync python scripts/verify_outputs.py --outputs results
# Repeat the full benchmark:
uv run --no-sync python scripts/benchmark.py --repeats 2 --report benchmarks/review-results.json
```

The suite has 98 tests covering reference calculations, ranking ties, invalid
input, precision, CLI entry points and output preservation. Full-data CSVs also
passed an independent Decimal ranking/formatting audit. Polars is the only runtime
dependency; pytest, psutil and Ruff support testing, RSS measurement and linting.
Versions and package hashes are pinned in `uv.lock`.

## Docker

With Docker running (the checked-in `results/` directory supplies the output mount):

```sh
docker build -t ad-aggregator .
docker run --rm -v "${PWD}/data:/data:ro" -v "${PWD}/results:/results" ad-aggregator --input /data/ad_data.csv --output /results
```

The image excludes the dataset and installs locked runtime dependencies. Build,
both-engine smoke tests, and full-data Polars execution passed during review;
container outputs matched host outputs. Docker timings are excluded from the
Windows benchmark. Review evidence is in
[review-verification.json](benchmarks/review-verification.json).

## AI disclosure

OpenAI Codex assisted with implementation, tests, review, benchmarking and
documentation. Reported timings and check results come from executed local runs.
