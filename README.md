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

`--engine python|polars|optimized|multiprocessing` defaults to **polars**.
The two experimental Python variants are described in
[python-experiments.md](benchmarks/python-experiments.md).
Equivalent entry points are
`python aggregator.py` and `python -m ad_aggregator` in the installed environment.

## Implementation and behavior

- **Python:** standard-library CSV streaming and dictionary aggregation.
- **Polars:** 32 MiB CSV byte batches, native validation and Int128 grouping,
  with exact Python-integer merging of campaign partials. Both engines share
  exact ranking and CSV formatting.
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

Full input: **1,043,304,870 bytes**, 50 campaigns. Three runs per implementation on Windows 11,
Intel i7-11700F (8 cores/16 threads), 31.86 GiB RAM, Python 3.12.12 and Polars 1.35.2.
Measured on 2026-11-05–06 with 16 Polars threads and a warm OS file cache.

| Engine | Median time | Maximum peak RSS | Median run throughput |
| --- | ---: | ---: | ---: |
| Preserved Polars baseline | 4.108 s | 2,028.1 MiB | 242.23 MiB/s |
| Polars, selected 32 MiB batches | 5.147 s | 568.9 MiB | 193.32 MiB/s |

**The default meets the under-1-GB / under-10-second goal on this dataset.**
Peak RSS fell about 72%, with a 25% time cost versus the preserved baseline.
All six runs produced identical totals and CSVs. Batch bytes are not an RSS cap:
campaign cardinality and record size also matter. Unusual literal quotes inside
unquoted fields use the original parser for compatibility and lose the batch
memory bound. The standard-library Python engine remains an alternative for
tighter memory budgets; its earlier measured median was 222.504 s / 23.2 MiB.

Timings include subprocess startup, imports, validation, aggregation, output, and
result hashing. RSS is the OS process high-water mark, including native memory.
Background desktop load was uncontrolled; individual runs show timing variation.
Thread, expression, streaming-control and batch experiments, trade-offs and
reproduction commands are in
[polars-memory-experiments.md](benchmarks/polars-memory-experiments.md).
The final comparison is in
[polars-memory-final.json](benchmarks/polars-memory-final.json).
Earlier Python and Polars measurements remain in
[review-results.json](benchmarks/review-results.json).

Docker/Linux validation also passed on the original input and reproducible
~1 GB inputs with 1K, 10K and 100K campaigns. At 100K campaigns, the optimized
engine used **579.6 MiB** peak RSS versus **3,268.4 MiB** for the baseline, with
median runtimes of **14.748 s** and **5.536 s** respectively. Its memory advantage
persists, while the sub-10-second target no longer holds at 100K. Both engines
produced identical aggregates and CSVs. See
[Docker/Linux scalability validation](benchmarks/docker-linux-scalability.md)
for all results, independent oracles, 1 GB container-limit checks and commands.

## Verification

```sh
uv run --no-sync pytest -q
uv run --no-sync ruff check src scripts tests aggregator.py
uv run --no-sync ruff format --check src scripts tests aggregator.py
uv run --no-sync python scripts/verify_outputs.py --outputs results
# Repeat the full benchmark:
uv run --no-sync python scripts/benchmark.py --engines polars-baseline polars --repeats 3 --polars-threads 16 --report benchmarks/polars-memory-final.json
```

The suite has 340 tests covering reference calculations, ranking ties, invalid
input, precision, CLI entry points, output preservation and chunk boundaries.
Full-data CSVs also
passed an independent Decimal ranking/formatting audit. Polars is the only runtime
dependency; pytest, psutil and Ruff support testing, RSS measurement and linting.
Versions and package hashes are pinned in `uv.lock`.

## Docker

With Docker running (the checked-in `results/` directory supplies the output mount):

```sh
docker build -t ad-aggregator .
docker run --rm -v "${PWD}/data:/data:ro" -v "${PWD}/results:/results" ad-aggregator --input /data/ad_data.csv --output /results
```

The image excludes the dataset and installs locked runtime dependencies. Earlier
build, both-engine smoke tests, and full-data Polars execution passed during
review; container outputs matched host outputs. The latest optimized production
image passed all 340 Linux tests and original/100K CLI runs under a 1 GB container
limit, with swap disabled. Separate Linux timings and memory measurements are in
[docker-linux-scalability.md](benchmarks/docker-linux-scalability.md) and are
excluded from the earlier Windows benchmark.
Earlier review evidence is in
[review-verification.json](benchmarks/review-verification.json).

## AI disclosure

OpenAI Codex assisted with implementation, tests, review, benchmarking and
documentation. Reported timings and check results come from executed local runs.
