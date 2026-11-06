# Memory follow-up

Keep 32 MiB as the default. Retain the small buffer-lifetime change and offer
`--batch-mib 16` when memory matters more than high-cardinality throughput.
Further parser rewrites or a custom C engine are not justified by the current
under-1-GB memory target. The 100K workload's remaining concern is runtime.

## Reused evidence

The existing [batch/thread study](polars-memory-experiments.md) already establishes
the trade-off: 16 MiB / 16 threads used 308.5 MiB and 6.581 s, versus 541.4 MiB
and 5.608 s at 32 MiB. The 8 MiB path approached 9 s; 64 MiB exceeded decimal
1 GB, and reducing baseline threads did not solve its memory problem. Those
configurations were not swept again. These are historical Windows measurements
on an i7-11700F with Python 3.12.12, not direct comparisons with this follow-up.
The existing Linux measurements also remain separate and unchanged.

## Allocation profile

[Final phase profiles](memory-lifetimes-final-windows.json) use three batches of
the actual original and 100K inputs, in fresh processes. `tracemalloc` records
Python allocation sites, live bytes and peaks; phase RSS and the OS resident
high-water mark include native allocations. Frame `estimated_size()` supplies
logical column-buffer sizes, not an allocation or RSS census. Forced GC and
tracing make these diagnostic runs unsuitable for performance comparisons.

The old reader holds `block` and `pending` across its yield. The first batch
aliases those bytes, but later batches commonly retain two distinct buffers.
For the original input, batches 2/3 retained about 64 MiB in Python after merging.
Constructing `header + pending[:end+1]` also temporarily copies the record slice
and its header-prefixed payload: Python's measured peak reached about 128 MiB.

The retained change deletes `block` after concatenation, separates the incomplete
record before parsing, and deletes the parse payload before yielding the frame.
Original-input Python memory after merging then stays below 70 KiB and the
three-batch Python peak drops to about 96 MiB. CSV boundary detection, parsing,
validation and exact aggregation expressions are unchanged. The remaining
payload copies are intentionally retained to keep the synchronous parser and
existing quoting/error behavior straightforward.

On 100K campaigns the partial and accumulated dictionaries remain material:
Python live allocations after batch 3 fall from about 117 to 53 MiB. This change
does not eliminate state proportional to campaign count. Raw frame logical sizes
are about 26 MiB (original) and 29 MiB (100K); grouped frames are about 3.4 KiB
and 6.8 MiB respectively. RSS rises substantially during grouping despite those
small results, consistent with native intermediates and allocator retention.
After closing the generators and collecting Python objects, live traced memory
falls below 35 KiB, but RSS remains hundreds of MiB in both versions. This is not
evidence of a Python leak or a measured attribution to a particular Rust allocator
site. No native allocation-stack profiler was used; subtracting traced Python
bytes from RSS would not measure exact native live memory.

Avoid speculative zero-copy/mmap parsing, allocator tuning and narrower numeric
types: the first two add portability/lifetime complexity without an unmet memory
requirement; the last would break valid totals exceeding Int64. External grouping
or changes to exact ranking should await requirements beyond the measured 100K
campaigns and profiles demonstrating their benefit.

## Comparison and conditions

The final report is [memory-release-windows-final.json](memory-release-windows-final.json).
`current` is the frozen previous 32 MiB byte reader; `released` uses the retained
production reader at 32 MiB; `released16` uses that reader at 16 MiB. Only the
reader is substituted: validation, aggregation, merging, ranking and CSV writing
are shared. Three sequential fresh processes per configuration per dataset run
in order current/released/released16, reversed on the second repetition.

| Campaigns | Configuration | Median seconds | Max OS peak RSS (MiB) | Median MiB/s |
| ---: | --- | ---: | ---: | ---: |
| 50 | Previous 32 MiB | 4.492 | 534.3 | 221.51 |
| 50 | Revised 32 MiB | 4.438 | 505.8 | 224.20 |
| 50 | Revised 16 MiB | 4.570 | 302.3 | 217.70 |
| 1K | Previous 32 MiB | 3.627 | 459.8 | 274.32 |
| 1K | Revised 32 MiB | 3.660 | 420.3 | 271.88 |
| 1K | Revised 16 MiB | 3.729 | 241.2 | 266.83 |
| 10K | Previous 32 MiB | 4.320 | 467.2 | 230.32 |
| 10K | Revised 32 MiB | 4.301 | 447.9 | 231.32 |
| 10K | Revised 16 MiB | 4.485 | 262.7 | 221.84 |
| 100K | Previous 32 MiB | 10.941 | 582.1 | 90.94 |
| 100K | Revised 32 MiB | 10.950 | 554.8 | 90.87 |
| 100K | Revised 16 MiB | 16.796 | 366.8 | 59.24 |

The small lifetime change lowers maximum OS RSS by 4.1–8.6% across these inputs,
with median time within about 1.3% of the previous default. Individual run ranges
overlap; no speedup or statistically established absence of regression is claimed.
This is worth its eight-line production diff and introduces no new parser,
numeric representation or dependency.

Relative to revised 32 MiB, revised 16 MiB saves about 34–43% RSS, with roughly
2–4% longer median runtime through 10K campaigns. At 100K it takes 53% longer
(+5.85 s). That supports a documented option, rather than changing the default
or automatically choosing a size without workload knowledge. The new CLI only
converts positive integer MiB to the existing byte-size API and rejects use with
other engines. It is not an adaptive memory limit. More invasive memory work
would need a tighter measured deployment budget to justify its maintenance cost.

Windows 11, Intel i5-14600KF (14 physical / 20 logical CPUs), about 15.79 GiB RAM;
Python 3.12.13, Polars 1.35.2, psutil 7.1.3, 16 Polars threads, locked `.venv`.
The OS cache is warm from hashing each input; desktop/background load is
uncontrolled. No tests, builds or generators ran concurrently with the timings.
End-to-end time includes startup, imports, validation, aggregation, ranking,
writing and hashes. Synthetic workers also read/compare the analytical aggregate
oracle, equally for each configuration. Reported memory is the maximum worker OS
RSS high-water mark, including native memory. Separate sampled simultaneous
process-tree peaks include launchers/workers and can miss short peaks or count
shared pages twice. This engine spawns no worker processes. Controller memory
and system file cache outside process RSS are excluded.

The original input is 1,043,304,870 bytes; each synthetic input is 1,043,304,901
bytes. The former Linux volume/datasets are absent in this workspace; the existing
generator recreated the same 1K/10K/100K datasets in an ignored working directory.
All four input hashes, complete aggregate hashes, and CSV hashes are checked
against the retained Linux study's independent identities. Cross-platform
identities are used for correctness only, never for timing comparisons.

## Reproduction and verification

Run from the root in the existing locked dev environment. All shell invocations
in this session used `rtk proxy`. Reports refuse replacement; use new paths to
repeat them. The generator also refuses to replace existing datasets. No
dependencies were added.

```powershell
.venv/Scripts/python.exe scripts/generate_scalability.py --output benchmark-output/memory-study-data
.venv/Scripts/python.exe scripts/study_memory.py --input data/ad_data.csv benchmark-output/memory-study-data/campaigns-100000.csv --profile --report benchmarks/memory-lifetimes-final-windows.json
.venv/Scripts/python.exe scripts/study_memory.py --input data/ad_data.csv benchmark-output/memory-study-data/campaigns-1000.csv benchmark-output/memory-study-data/campaigns-10000.csv benchmark-output/memory-study-data/campaigns-100000.csv --config current released released16 --report benchmarks/memory-release-windows-final.json
.venv/Scripts/python.exe scripts/audit_memory_study.py --report benchmarks/memory-release-windows-final.json
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check src scripts tests aggregator.py
.venv/Scripts/python.exe -m ruff format --check src scripts tests aggregator.py
.venv/Scripts/python.exe scripts/verify_outputs.py --outputs benchmark-output/memory-study/ad_data/current benchmark-output/memory-study/ad_data/released benchmark-output/memory-study/ad_data/released16 results
git diff --check -- README.md src/ad_aggregator/cli.py src/ad_aggregator/polars_engine.py tests/test_polars_memory.py
```

All **36 timed runs** match the previous complete aggregate and both CSV hashes;
every synthetic worker also directly compared its full canonical aggregate bytes
with the independently generated analytical oracle. The audit additionally hashes
the retained CSV files. All input hashes are checked again after measurement.
**348 tests passed in 11.64 s**; Ruff check and format check passed for 27 files.
Tests exercise tiny batch/quote boundaries, malformed and late invalid rows,
Int64-exceeding totals, exact rounding, CSV parity and output preservation; new
CLI tests cover custom batch sizing and invalid option combinations.
The separate Decimal audit verified all eight original-input CSV files, including
the checked-in results. The scoped diff whitespace check passed. Protected files
and previous reports were not edited; the pre-existing `PROMPTS.md` changes remain.

The benchmark's production aggregation code is the retained code. The subsequent
CLI-only help-text shortening changes its recorded CLI source hash, with no
effect on measured workers (which call the engine API). Initial lint failures
were corrected before final checks. An initial profiling controller blocked on
its stdout pipe; those specific processes were stopped and capture changed to a
temporary file before any retained profile completed. There are no partial runs
in the completed reports.

The earlier [initial profile](memory-lifetimes-windows.json) and
[original-only comparison](memory-release-windows-original.json) are retained.
The final profile more faithfully retains partial dictionaries across iterations;
the final comparison exercises the promoted production reader and smaller batches.
Their source identities reflect those diagnostic-script revisions.

No new Linux, cold-cache, millions-of-keys or bare-quote large-file measurement
was performed. The existing bare-quote compatibility fallback can still use
whole-file baseline memory. Batch size is not an RSS cap.
