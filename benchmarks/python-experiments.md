# Python optimization experiments

## Implementations

The `python` engine remains the unchanged baseline. Both new engines use the
existing schema, exact millionth-unit spend arithmetic, arbitrary-precision
campaign sums, ranking and output writer. Invalid input fails before outputs
are published. No rows are skipped, and duplicate records remain additive.

`optimized` retains streaming CSV parsing. It resolves column indices and binds
compiled regex match methods once per stream. The hot loop uses direct field
access, explicit count checks and four scalar accumulator updates. This removes
per-row generators, the counts tuple, the temporary values list on repeated
campaigns, and the accumulator enumeration. Valid-date caching is retained;
calendar validation still occurs for every distinct date. The six field-length
checks, count/spend syntax and Int64 input bounds remain enforced on every row.
The resource checks are necessary even though they cost time.

`multiprocessing` uses the optimized validator inside four spawned processes.
The parent opens the file once and uses strict `csv.reader` parsing before
grouping 25,000 logical records per task. This safely handles embedded CR/LF,
escaped quotes, UTF-8, BOMs, reordered headers and a missing final newline.
There is no newline-only splitting or assumption that byte offsets are record
boundaries. Each worker validates its chunk and returns campaign totals; the
parent merges exact integer sums in submission order. Logical error record
numbers include the original header. Worker failures propagate to the caller.

At most eight tasks are outstanding (two per worker), including running tasks.
This avoids submitting the entire dataset. Memory depends on chunk row sizes,
serialization buffers, worker copies, date sets and campaign cardinality; it is
not a fixed byte cap. Each chunk builds its own date cache. CSV parsing and
serialization remain serial work in the parent, which can limit scaling.
These are deliberate limits of this experiment, not evidence about every
possible parallel CSV implementation. The public Python API accepts `workers`
and `chunk_rows` keyword arguments; the CLI uses the documented defaults.
Programs calling multiprocessing must use a `if __name__ == "__main__":` guard.

## Reproduction and measurement

```sh
uv sync --frozen --extra dev --python 3.12
uv run --no-sync python scripts/benchmark.py --engines python optimized multiprocessing polars --repeats 2 --workers 4 --chunk-rows 25000 --report benchmarks/python-experiments.json
uv run --no-sync pytest -q
uv run --no-sync ruff check src scripts tests aggregator.py
uv run --no-sync ruff format --check src scripts tests aggregator.py
```

The recorded execution used `.venv/Scripts/python.exe` and the environment's
Ruff executable directly. The raw report stores the exact command, source hashes,
input SHA256/size, versions, hardware and each repetition. No dependencies were
added. The input is read for hashing before timing and checked again afterward.
Runs use fresh sequential subprocesses, reversing engine order for the second
repetition. OS caches are not flushed; desktop background activity is uncontrolled.
Wall time includes startup/imports, CSV parsing, validation, aggregation, process
creation/IPC/merge where applicable, ranking, writing and result hashing.

For comparable RAM accounting, all new runs use the maximum sampled sum of
simultaneous resident memory across the engine process tree, including workers.
The requested interval is 10 ms; scheduler and process enumeration overhead can
lengthen it and short peaks may be missed. Shared pages can be counted more than
once. The benchmark controller is excluded. The parent OS high-water mark is
also stored separately. Earlier reports used only the parent high-water mark,
so their memory figures should not be directly mixed with this table.

Each run hashes **all campaign totals**, not just the top ten, and both output
files. Any mismatch aborts the comparison. The tests compare against independent
Decimal/reference sums and rankings, and cover invalid values, oversized fields,
leading zeros, overflow, blank/malformed records, invalid UTF-8, dates, output
preservation and CLI behavior for both variants. Additional spawn tests force
one- and two-record chunks across quoted multiline records and verify a late
validation error's original logical record number.

## Measured results

Executed 2026-11-05 16:48–17:03 UTC (local date crossed into November 6).
Input: **1,043,304,870 bytes**, **50 campaigns**, SHA256
`4e9c87cc0b408f043917f5f7ee0101ba09899ad79f154358e9a2da374cfd60eb`.
Windows 11, Intel i7-11700F (8 physical/16 logical CPUs), 31.86 GiB RAM,
Python 3.12.12, Polars 1.35.2 (16 threads), psutil 7.1.3.

| Engine | Run 1 / run 2 (s) | Median (s) | Max sampled tree RAM (MiB) | Median run throughput (MiB/s) |
| --- | ---: | ---: | ---: | ---: |
| Python baseline | 179.597 / 256.475 | 218.036 | 27.8 | 4.71 |
| Optimized streaming | 126.008 / 150.782 | 138.395 | 27.6 | 7.25 |
| Multiprocessing, 4 × 25,000 records | 92.033 / 90.159 | 91.096 | 248.6 | 10.92 |
| Polars reference | 4.407 / 4.253 | 4.330 | 1,999.5 | 229.87 |

Time is the median of two runs; RAM is the larger sampled peak. Throughput is
the median of each run's input MiB / wall seconds, so it need not equal input
size divided by median time. All eight runs matched all campaign totals and
both CSVs. The aggregate SHA256 was
`3c979d5a88ec65718218625eeef3176d2770807bb9080aa65e6d02fb194774e0`.
The complete machine-readable evidence is [python-experiments.json](python-experiments.json).

Optimized streaming reduced median elapsed time **36.5%** (1.58× baseline
speed) with essentially unchanged RAM. Multiprocessing reduced it **58.2%**
(2.39× baseline speed), and took **34.2% less time** than optimized streaming,
using about **9.0×** its RAM (roughly 221 MiB more). The four-worker speedup over
the optimized single process was only **1.52×**: serial parsing, serialization,
chunk allocation, merging and process overhead constrain the full pipeline.
Their individual costs were not profiled, so no specific bottleneck is claimed
as measured. Polars was **21.0× faster** than multiprocessing, using about
**8.0×** its sampled RAM.

Baseline timings differed by 42.8% between repetitions; optimized streaming
differed by 19.7%, multiprocessing by 2.1%. Both repetitions independently show
the same engine ordering, but two samples on an uncontrolled desktop do not
establish precise speedup estimates or confidence intervals. Monitoring adds
overhead and consumes CPU outside the measured process tree. These results
describe warm-cache execution on this machine and this dataset, not cold disk
performance or scaling to many distinct campaigns. Worker counts and chunk sizes
were not swept, and direct byte-range parallel parsing was not implemented.

## Recommendation and verification

Keep **Polars as the default** for throughput when about 2 GiB RAM is available.
Choose **optimized streaming** for the best measured low-memory trade-off: it
preserves the baseline's approximately 28 MiB footprint and materially reduces
runtime. Choose **multiprocessing** when standard-library execution is required,
roughly 250 MiB is affordable and shorter runtime matters more than minimum RAM.
It is the fastest of the three Python approaches tested, but its extra processes
and memory are not justified for a strict low-memory requirement. Retain the
unchanged baseline as the reproducible comparison, rather than replacing it.

Executed checks (all commands prefixed with the repository-required `rtk proxy`):

```text
.venv/Scripts/python.exe -m pytest -q
194 passed in 15.78s
.venv/Scripts/ruff.exe check src scripts tests aggregator.py
All checks passed!
.venv/Scripts/ruff.exe format --check src scripts tests aggregator.py
15 files already formatted
```

The full benchmark command above completed all eight runs, verified input
SHA256/size after execution and marked the report `complete: true`. The baseline
source hash matches the prior reviewed benchmark. `PROMPTS.md` was not edited.
