# Polars memory study

The retained default uses **32 MiB synchronous CSV byte batches** with native
Polars validation and aggregation. On the full dataset, the final alternating
comparison achieved **5.147 s median, 568.9 MiB maximum OS peak RSS, and
193.32 MiB/s median throughput**. All three selected runs were below 10 seconds
and 1,000,000,000 bytes RSS. The original implementation remains unchanged in
[`polars_baseline.py`](../src/ad_aggregator/polars_baseline.py).

## Final comparison

Source: [polars-memory-final.json](polars-memory-final.json). Three fresh
subprocesses per implementation, alternating execution order, 16 Polars threads.
RSS below is the **parent OS high-water mark**, not the sampled process-tree
estimate also present in that report.

| Implementation | Median seconds | Time range | Maximum peak RSS (MiB) | Median MiB/s |
| --- | ---: | ---: | ---: | ---: |
| Preserved baseline | 4.108 | 2.858–4.163 | 2,028.1 | 242.23 |
| Selected 32 MiB batches | 5.147 | 4.431–5.480 | 568.9 | 193.32 |

This trades about **25% more elapsed time (+1.04 s)** for **72% lower peak RSS**.
The selected maximum is about 596 MB in decimal units, comfortably below the
1 GB goal. Results are machine-specific measurements, not a universal limit.

## Conditions and identities

- Input: `data/ad_data.csv`, **1,043,304,870 bytes**, 50 campaigns.
- SHA256: `4e9c87cc0b408f043917f5f7ee0101ba09899ad79f154358e9a2da374cfd60eb`.
- Windows 11, Intel i7-11700F, 8 physical / 16 logical CPUs, 31.86 GiB RAM.
- Python 3.12.12, Polars 1.35.2, psutil 7.1.3, existing isolated `.venv` and
  locked dependencies; no dependency changes.
- Executed November 5–6, 2026 local time. Each configuration has three runs.
  Subprocesses run sequentially. Thread order reverses on alternate repetitions.
- Wall time includes startup, imports, strict validation, aggregation, ranking,
  CSV writing and aggregate/output hashing. Throughput is input MiB / wall time.
- RSS uses Windows `peak_wset`, including native allocations and resident mapped
  pages. The final harness also samples simultaneous process-tree RSS every
  approximately 10 ms; its slightly higher launcher-inclusive values are separate.
- Input hashing warms the OS file cache before measurement and checks input
  identity again afterwards. No cache flush, CPU affinity or clock control;
  background desktop load is uncontrolled. Timing variation is visible in the
  individual records. Do not attribute differences of a few tenths of a second
  between separate sweeps to a configuration alone.
- The retained chunk/morsel/batch sweeps and final comparison ran without
  concurrent test workloads. Preliminary smoke runs were superseded by these
  sweeps. Earlier expression and low-memory scan trials are exploratory; test
  activity occurred near those trials. The final alternating comparison is the
  strongest evidence for the selected implementation.

The JSON reports retain exact commands, source hashes, versions, input identity,
individual timings, RSS, throughput and output identities. Source hashes in the
final comparison match the retained implementation. Earlier source hashes
reflect intermediate development; `polars_experimental.aggregate` now forwards
the same experiment options to the retained engine.

## Thread tuning: unchanged baseline

Source: [polars-thread-tuning.json](polars-thread-tuning.json).

| POLARS_MAX_THREADS | Median seconds | Maximum RSS (MiB) | Median MiB/s |
| ---: | ---: | ---: | ---: |
| 2 | 17.328 | 1,441.1 | 57.42 |
| 4 | 10.527 | 1,899.7 | 94.52 |
| 8 | 6.456 | 1,916.7 | 154.11 |
| 16 | 4.321 | 2,001.8 | 230.26 |

Reducing threads alone missed the memory target. Two threads also exceeded the
time budget. Threads are configured before the child imports Polars. Production
does not alter the process-wide thread setting; the retained measurements use
16 threads on this 16-logical-CPU machine.

## Expressions and streaming controls

| Configuration (16 threads) | Median seconds | Maximum RSS (MiB) | Median MiB/s | Evidence |
| --- | ---: | ---: | ---: | --- |
| Optimized expressions, lazy scan | 2.682 | 2,023.1 | 370.96 | [JSON](polars-expressions.json) |
| Same expressions, scan low_memory=True | 2.697 | 2,049.4 | 368.91 | [JSON](polars-scan-low-memory.json) |
| Baseline, Config chunk size 1,000 | 2.810 | 2,119.5 | 354.05 | [JSON](polars-chunk-1000.json) |
| Baseline, Config chunk size 10,000 | 4.033 | 2,019.3 | 246.70 | [JSON](polars-chunk-10000.json) |
| Baseline, Config chunk size 100,000 | 3.945 | 2,016.5 | 252.18 | [JSON](polars-chunk-100000.json) |
| Baseline, native morsel size 1,000 | 2.847 | 2,062.7 | 349.54 | [JSON](polars-morsel-1000.json) |
| Baseline, native morsel size 10,000 | 3.990 | 2,012.7 | 249.39 | [JSON](polars-morsel-10000.json) |
| Baseline, native morsel size 100,000 | 3.937 | 2,068.0 | 252.76 | [JSON](polars-morsel-100000.json) |
| Optimized, read_csv_batched, 100,000 rows | 18.039 | 1,211.8 | 55.16 | [JSON](polars-row-batches.json) |

The expression changes stage parsed Int64 values once for reuse in validation
and summation. Spend still passes the lexical precision check and Decimal(38,6)
conversion, but `to_physical()` obtains exact millionths directly, avoiding
Decimal multiplication by 1,000,000. Leading-zero normalization and range checks
remain. A narrow projection discards raw fields after validation. Int128 sums
remain necessary: replacing them with Int64 sums could overflow on valid input.

Saved optimized and physical plans: [baseline](polars-baseline.plan.txt),
[baseline physical](polars-baseline.physical.dot),
[expressions](polars-expressions.plan.txt),
[expressions physical](polars-expressions.physical.dot),
[per-batch query](polars-batch.plan.txt),
[per-batch physical](polars-batch.physical.dot).
The baseline and revised lazy scans both show native streaming group-by, with
no in-memory-engine fallback. Moving Int128 casts into aggregation expressions
does not eliminate the physical cast projection; the optimizer lifts it ahead
of grouping. Expression optimization improves the exploratory timing but does
not solve whole-file RSS. No allocation-profiler attribution is claimed.

Version-specific detail: in **1.35.2**, the public
[`set_streaming_chunk_size` implementation](https://github.com/pola-rs/polars/blob/py-1.35.2/py-polars/src/polars/config.py)
sets `POLARS_STREAMING_CHUNK_SIZE`, while the native streaming
[`morsel` implementation](https://github.com/pola-rs/polars/blob/py-1.35.2/crates/polars-stream/src/morsel.rs)
reads `POLARS_IDEAL_MORSEL_SIZE` (default 100,000). Both controls were tested
separately. Neither achieved the memory target; no unstable environment tuning
is required by the selected implementation.

`LazyFrame.collect_batches(chunk_size=2)` was rejected before full-data timing:
on a small ragged CSV, Polars 1.35.2 ended iteration normally and raised the
parsing error only in `BatchCollector.__del__` as an unraisable exception. This
could produce a success-shaped partial result, violating strict validation.
It is not used or exposed by the retained engine. The synchronous
`read_csv_batched().next_batches(1)` alternative passed validation fixtures and
was benchmarked on the full input, but failed both resource targets.

## Byte-bounded processing

Each byte batch ends at a complete CSV record outside quoted fields. Polars
parses the original bytes as strings, validates them, and computes per-campaign
Int128 partial sums. Python integers merge the small partial dictionaries
exactly. Validation finishes before the shared output writer runs. No source
data or intermediate dataset copies are written to disk.

| Input batch (MiB) | Threads | Median seconds | Maximum RSS (MiB) | Median MiB/s |
| ---: | ---: | ---: | ---: | ---: |
| 8 | 8 | 8.848 | 178.1 | 112.46 |
| 8 | 16 | 8.902 | 190.5 | 111.77 |
| 16 | 8 | 7.635 | 296.0 | 130.31 |
| 16 | 16 | 6.581 | 308.5 | 151.20 |
| 32 | 8 | 6.243 | 551.9 | 159.38 |
| 32 | 16 | 5.608 | 541.4 | 177.41 |
| 64 | 8 | 6.321 | 982.8 | 157.40 |
| 64 | 16 | 5.748 | 1,155.6 | 173.09 |

Evidence: [8 MiB](polars-byte-8m.json), [16 MiB](polars-byte-16m.json),
[32 MiB](polars-byte-32m.json), [64 MiB](polars-byte-64m.json).
The sweep predates the final explicit previous-frame release and quote-boundary
compatibility correction; the final comparison above measures the retained code.

**Decision:** retain 32 MiB. It improves throughput over smaller batches while
leaving substantial memory headroom. The 64 MiB option was slower in this sweep
and exceeded **decimal 1 GB even at eight threads**. For a tighter memory budget,
16 MiB is a measured alternative, with approximately 309 MiB peak and 6.58 s
median at 16 threads. The expression-only scan is faster but misses the memory
goal by a wide margin.

Memory scales with batch buffers, an unfinished record and unique campaign
totals. Batch bytes are not an RSS cap. UTF-8 field limits bound an unfinished
valid record; impossible oversized unfinished records fail early. Quoted
multiline fields and doubled quotes are supported. For unusual **literal quotes
inside unquoted fields**, the pinned Polars parser has input-dependent behavior;
the engine delegates the whole input to the preserved baseline to keep exactly
that behavior. Those inputs lose the byte-batch memory bound. The measured input
does not trigger that fallback. High-cardinality campaign data, other hardware,
other Polars versions and cold-cache performance require new measurements.

## Correctness and verification

All retained full-data experiments have the same aggregate hash:
`3c979d5a88ec65718218625eeef3176d2770807bb9080aa65e6d02fb194774e0`.
Both CSV hashes also match across the study and final comparison:

- CTR: `c8a50e2870b1bf0386818252a8c54a0bdc109469eb0c7ad791f749bd49cd3052`.
- CPA: `0bb724eb8ca9237e188e5eb46b5c63ddf24804c1a353668eaf94c81c86c9cedc`.

Executed checks on the retained code:

```powershell
.venv/Scripts/python.exe -m pytest -q
# 330 passed in 16.99 s
.venv/Scripts/python.exe -m ruff check src scripts tests aggregator.py
# All checks passed
.venv/Scripts/python.exe -m ruff format --check src scripts tests aggregator.py
# 20 files already formatted
.venv/Scripts/python.exe scripts/verify_outputs.py --outputs benchmark-output/polars benchmark-output/polars-baseline results
# All six CSVs matched independent high-precision Decimal ranking/formatting
git diff --check -- README.md scripts/benchmark.py src/ad_aggregator/polars_engine.py
# Passed for changed tracked files in this task
```

The whole-working-tree `git diff --check` failed on pre-existing whitespace in
`PROMPTS.md`; that user-maintained file was left untouched. `AGENTS.md` and
`REQUIREMENTS.md` were also left untouched. Existing unrelated Python experiment
changes were preserved. A final audit verified 15 complete study reports / 69
recorded full-data runs with identical input, aggregate and output identities,
and confirmed that the final report's source hashes match retained source files.

Tests use small synthetic inputs and an independent Python/Decimal reference.
Coverage includes existing schema/value failures, header-only input, reordered
BOM headers, duplicates, totals exceeding Int64, spend boundaries, leading
zeros, Unicode, quotes, multiline fields, LF/CRLF, missing final newline,
byte boundaries down to one byte, invalid records after valid batches and
oversized unfinished records. The tests initially exposed the asynchronous
error issue and quote-parser compatibility issue; both are handled as above.
No new Docker, Linux or cold-cache benchmark was executed.

## Reproduce

Run from the repository root in the existing locked environment. Commands below
are the underlying commands; this session invoked shell commands through `rtk`.
Do not run tests or other heavy jobs concurrently with benchmarks.

```powershell
# Preserved baseline, full thread sweep:
.venv/Scripts/python.exe scripts/benchmark_polars.py --report benchmarks/polars-thread-tuning.json
# Expression-only scan; add --low-memory to reproduce its scan variant:
.venv/Scripts/python.exe scripts/benchmark_polars.py --module polars_experimental --threads 16 --report benchmarks/polars-expressions.json
# Repeat with sizes 1000, 10000 and 100000 for each control:
.venv/Scripts/python.exe scripts/benchmark_polars.py --threads 16 --chunk-size 1000 --report benchmarks/polars-chunk-1000.json
.venv/Scripts/python.exe scripts/benchmark_polars.py --threads 16 --morsel-size 1000 --report benchmarks/polars-morsel-1000.json
# Native synchronous row batches:
.venv/Scripts/python.exe scripts/benchmark_polars.py --module polars_experimental --threads 16 --batch-rows 100000 --report benchmarks/polars-row-batches.json
# Repeat with 8388608, 16777216, 33554432 and 67108864 byte sizes:
.venv/Scripts/python.exe scripts/benchmark_polars.py --module polars_experimental --threads 8 16 --batch-bytes 33554432 --report benchmarks/polars-byte-32m.json
# Retained implementation versus original, interleaved:
.venv/Scripts/python.exe scripts/benchmark.py --engines polars-baseline polars --repeats 3 --polars-threads 16 --report benchmarks/polars-memory-final.json
# Regenerate plans with pinned installed Polars:
.venv/Scripts/python.exe scripts/inspect_polars_plans.py
```

The experiment runner compares both aggregate and output identities against
`polars-thread-tuning.json` for non-baseline modules. The final runner compares
all six runs with each other and records both OS and sampled RSS separately.
