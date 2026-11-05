# Docker/Linux and campaign-cardinality validation

The optimized implementation retained its memory advantage through **100,000
campaigns** on approximately 1 GB inputs. At 100K campaigns it used **579.6 MiB
maximum peak RSS**, versus **3,268.4 MiB** for the preserved baseline, an **82.3%
reduction**. Its median runtime rose to **14.748 seconds**, so the earlier
under-10-second target does not hold at this cardinality.

No correctness issue was found. Production source, the production Dockerfile,
dependencies and earlier benchmark artifacts were left unchanged.

## Environment and measurement

- Built the existing `Dockerfile` as `ad-aggregator:scalability`. Production image
  digest: `sha256:3153db07dd2433e7eef4cab1ef3e3920a8bb9c1d3f78d158b02615c1337dcccc`.
- Python **3.12.16**, Polars **1.35.2**, Linux x86_64, kernel
  `6.6.87.2-microsoft-standard-WSL2`; Docker Engine **29.4.0** under Docker Desktop.
- Intel i7-11700F, 16 visible logical CPUs; Docker VM memory 16,691,412,992 bytes.
  The Windows host has 8 physical cores / 16 logical CPUs and 31.86 GiB RAM.
- `POLARS_MAX_THREADS=16`; 16-CPU quota; main comparison has a **4 GiB container
  memory limit with swap disabled**. Captured cgroup values are `memory.max =
  4294967296`, `memory.swap.max = 0`, `cpu.max = 1600000 100000`.
- Data and timed outputs reside in the Linux-native named volume
  `ad-aggregator-scalability-v1`. The original input was copied once, then
  verified against its existing SHA256. Source scripts are mounted read-only;
  reports are written to the host after timed worker completion.
- Three fresh subprocesses per engine per dataset: **24 full-input runs**.
  Engines alternate order. SHA256 reads warm the Linux page cache before each
  dataset; no cache flush or cold-cache claim. No tests/builds ran concurrently
  with the comparison. Fourteen unrelated containers and desktop activity were
  left running; background load and CPU frequencies were not controlled.
- Runtime includes subprocess startup/imports, validation, aggregation, exact
  ranking, CSV output, complete aggregate JSON export and hashing. Throughput is
  input MiB divided by that wall time. The existing Windows benchmark did not
  export aggregate JSON, so these timings have a small additional audit cost.
- Peak RSS is the Linux worker's OS high-water mark,
  `resource.getrusage(RUSAGE_SELF).ru_maxrss * 1024`. It includes native Polars
  allocations and resident file mappings. It excludes the controller, Docker/VM
  overhead and page-cache pages not resident in the worker. It is **not** cgroup
  memory consumption or a sampled `docker stats` estimate. The 4 GiB limit can
  influence reclamation; these results describe that resource envelope.

The [raw study](docker-linux-scalability.json) records every run, phase timings,
versions, kernel/CPU/memory information, source hashes, cgroup limits, input
identities and output identities. The [Docker/CLI record](docker-linux-verification.json)
records the production image, Docker environment and separate hard-limit runs.
All packaged production module bytes were checked against repository source.
The base image tag is mutable; this build used `python:3.12-slim` at digest
`sha256:4840d514c583a4d3d8cad3940e68dee6f0f6f3635c12fcd0a3d74c21a5b93a54`.
Future rebuilds should record fresh provenance rather than assume the same
Python patch version or image identity.

## Reproducible inputs

[`generate_scalability.py`](../scripts/generate_scalability.py) creates three
new CSVs, each **1,043,304,901 bytes**, only 31 bytes larger than the original
**1,043,304,870-byte** input. All have **17,683,133 records of 59 bytes** plus
the same header. IDs, numeric widths, six-place decimal spend and date format
are fixed across cardinalities. Counts/spend vary deterministically by campaign;
zero-impression and zero-conversion cases are included. No floating-point
arithmetic is used.

| Campaigns | Records per campaign | Input SHA256 |
| ---: | --- | --- |
| 1,000 | 17,683 or 17,684 | `ff2a4b70ed1f58bfa6a7ea59b66a04bc5be85499899f61f20095e1adc45d908d` |
| 10,000 | 1,768 or 1,769 | `63c1edc19061b4bcbcdfdbbe68531c1fdc3fd4c4b61f5cd8913737fb67fe8fe4` |
| 100,000 | 176 or 177 | `0ab9c2b255468fccb30e5018ab5ad1789bb432eb62b78f39157b2f501cb92600` |

Seed **20261106** shuffles one cycle containing every campaign exactly once.
The generator repeats that interleaved cycle and writes a final partial cycle.
This prevents campaign-sorted input from hiding the working set: a 32 MiB batch
sees all 100K campaign keys in the largest case. Each campaign's per-row metrics
are constant, making totals independently calculable as per-row values times
its analytically known repetition count. Duplicates are deliberately additive.
This workload stresses key cardinality, not high-entropy records or hot-key skew.

Each input has a manifest with seed, row counts, cycle/input hashes, analytical
aggregate hash and independently calculated Decimal CSV hashes, plus a complete
expected-aggregate JSON file. The study embeds the manifest fields. Generator
tests compare its analytical oracle to the independent Python CSV engine on
small fixtures, including partial cycles. Existing input/expected files are not
overwritten. Large generated inputs and aggregate JSONs remain in the Docker
volume, outside Git.

## Performance and memory scaling

Medians of three runs; peak memory is the **maximum** of the three OS high-water
marks. The original row is a cross-platform validation case; its record format
differs from the fixed-width synthetic inputs and is not a cardinality control.

| Input campaigns | Engine | Median seconds | Maximum RSS (MiB) | Median MiB/s |
| ---: | --- | ---: | ---: | ---: |
| 50 (original) | Baseline | 3.441 | 2,385.3 | 289.13 |
| 50 (original) | Optimized | 5.578 | 574.0 | 178.36 |
| 1,000 | Baseline | 2.430 | 2,046.4 | 409.53 |
| 1,000 | Optimized | 4.524 | 474.7 | 219.91 |
| 10,000 | Baseline | 2.926 | 2,794.4 | 340.07 |
| 10,000 | Optimized | 5.500 | 482.7 | 180.90 |
| 100,000 | Baseline | 5.536 | 3,268.4 | 179.73 |
| 100,000 | Optimized | 14.748 | 579.6 | 67.46 |

Peak-RSS reduction is **76.8%, 82.7%, and 82.3%** at 1K, 10K and 100K
campaigns, respectively. From 1K to 100K, the optimized peak increases about
**105 MiB / 22%**, while the baseline increases about **1,222 MiB / 60%**.
Both retain campaign state; 32 MiB input batches do not make memory independent
of campaign cardinality. Native allocator behavior and output-stage temporaries
also affect peak RSS, so these differences are not a per-campaign byte estimate.

The runtime cost becomes material: optimized median time grows **3.26x** from
1K to 100K. At 100K it is **2.66x** the baseline runtime. Phase medians help
separate the effects:

| Campaigns | Engine | Aggregation seconds | Ranking + CSV seconds | Aggregate export + hashes seconds |
| ---: | --- | ---: | ---: | ---: |
| 1,000 | Baseline | 2.107 | 0.020 | 0.002 |
| 1,000 | Optimized | 4.211 | 0.015 | 0.001 |
| 100,000 | Baseline | 2.612 | 2.407 | 0.152 |
| 100,000 | Optimized | 11.774 | 2.444 | 0.188 |

These phase medians need not add to the end-to-end median, which also includes
startup/imports. Exact Fraction-based ranking becomes significant for both
engines. The remaining optimized slowdown is in aggregation. This is consistent
with repeated per-batch grouping and Python dictionary merging when every batch
contains many keys; no profiler attribution to a particular operation is claimed.

## Hard-limit production CLI validation

Separate executions used the **unchanged image ENTRYPOINT**, `ad-aggregate`,
with `--memory 1000000000 --memory-swap 1000000000` and 16 threads/CPUs.
Equal memory and memory-plus-swap limits disable swap, as described in
[Docker's resource constraints documentation](https://docs.docker.com/engine/containers/resource_constraints/).

| Input | Start/attach wall time | Exit code | OOMKilled | CSVs |
| --- | ---: | ---: | --- | --- |
| Original, 50 campaigns | 5.605 s | 0 | false | Both hashes matched |
| Synthetic, 100K campaigns | 15.053 s | 0 | false | Both independent hashes matched |

These are single CLI smoke runs, not benchmark medians. Their wall times include
container startup and exclude `docker create`. No process RSS is inferred from
the cap. Successful completion validates a **1 GB whole-container memory limit**
for these two cases, including memory charged to that container beyond worker
RSS; it does not guarantee the same behavior for other workloads.

## Correctness and checks

- All 24 measured runs match the expected campaign count, complete aggregate
  SHA256 and both CSV SHA256 values. The six original-data runs also match the
  previously recorded Windows aggregate and CSV identities.
- Every synthetic run additionally compares its complete decoded aggregate
  list directly against the independently generated analytical oracle after
  timing. This comparison is in the controller, outside worker RSS and time.
- A [separate audit](docker-linux-output-audit.json) directly compares the last
  retained baseline and optimized aggregate lists for **all four datasets**.
  It reconstructs both top-ten CSVs with independent high-precision Decimal
  ranking/rounding and compares actual bytes for all eight output files.
- Linux test image built from the production image with existing locked dev
  dependencies: **340 tests passed in 10.75 s**. Windows: **340 tests passed in
  18.25 s**. New tests cover generator identities, seed reproducibility, uniform
  row widths, partial-cycle analytical totals and source-file preservation.
- Ruff check and format check passed in both environments. Initial Linux Ruff
  commands could not write their cache on the read-only source mount; rerunning
  with `--no-cache` passed. This was a tooling/mount issue, not a code failure.
- No new dependencies, production fixes or runtime changes were needed.

## Recommendations and limits

Keep the optimized default when memory headroom matters: its advantage persists
through the measured 100K campaigns, and the production CLI passes a decimal
1 GB hard limit. For the tested 1K/10K inputs it also stays below 10 seconds.
Budget roughly 15 seconds for this tested 100K workload rather than carrying
forward the original dataset's latency target.

If a 100K workload needs a sub-10-second SLA and several GiB of RAM are available,
the preserved baseline is the faster measured option. Further optimization should
profile batch grouping/merging and exact ranking before changing either. This
study does not promote an unmeasured production alternative.

The study stops at 100K balanced, interleaved keys. It does not cover millions of
keys, strongly skewed distributions, long/Unicode campaign IDs at scale, quoted
large records or malformed-input throughput. Existing small validation tests
cover those relevant syntax/failure boundaries, but do not establish large-file
resource bounds. The existing unusual bare-quote fallback still uses baseline
memory behavior. Linux here is WSL2 Docker Desktop, not bare-metal Linux; no
universal cross-OS speedup or cold-cache guarantee is claimed. The Linux volume
choice follows [Docker's WSL filesystem guidance](https://docs.docker.com/desktop/features/wsl/best-practices/).

## Reproduction

Run from the repository root in PowerShell. Use a **new volume name** for a fresh
study: the generator deliberately refuses to replace existing inputs. Commands
below omit this session's `rtk proxy` shell wrapper. Run benchmarks sequentially
without builds or tests in parallel. Existing reports can be preserved by giving
new `--report` paths. The volume retains about 4 GB of inputs and audit outputs.

```powershell
$repo = (Get-Location).Path
$volume = "ad-aggregator-scalability-v1"
docker build -t ad-aggregator:scalability .
docker volume create $volume
docker run --rm --mount "type=volume,src=$volume,dst=/study" --mount "type=bind,src=$repo/data,dst=/host-data,readonly" --entrypoint python ad-aggregator:scalability -c "from pathlib import Path; import shutil; p=Path('/study/data'); p.mkdir(exist_ok=True); shutil.copyfile('/host-data/ad_data.csv',p/'original.csv')"
docker run --rm --mount "type=volume,src=$volume,dst=/study" --mount "type=bind,src=$repo/scripts,dst=/tools,readonly" --entrypoint python ad-aggregator:scalability /tools/generate_scalability.py --output /study/data/synthetic-v1
docker run --rm --cpus 16 --memory 4294967296 --memory-swap 4294967296 --env POLARS_MAX_THREADS=16 --mount "type=volume,src=$volume,dst=/study" --mount "type=bind,src=$repo,dst=/repo,readonly" --mount "type=bind,src=$repo/benchmarks,dst=/reports" --entrypoint python ad-aggregator:scalability /repo/scripts/benchmark_linux.py --report /reports/docker-linux-scalability.json
docker run --rm --mount "type=volume,src=$volume,dst=/study,readonly" --mount "type=bind,src=$repo/scripts,dst=/tools,readonly" --mount "type=bind,src=$repo/benchmarks,dst=/reports" --entrypoint python ad-aggregator:scalability /tools/audit_linux_outputs.py --study /reports/docker-linux-scalability.json --report /reports/docker-linux-output-audit.json
.venv/Scripts/python.exe scripts/validate_docker_cli.py --volume $volume
docker build -f docker/validation.Dockerfile -t ad-aggregator:scalability-tests .
docker run --rm --mount "type=bind,src=$repo,dst=/repo,readonly" --workdir /repo ad-aggregator:scalability-tests -q -p no:cacheprovider
docker run --rm --mount "type=bind,src=$repo,dst=/repo,readonly" --workdir /repo --entrypoint python ad-aggregator:scalability-tests -m ruff check --no-cache src scripts tests aggregator.py
docker run --rm --mount "type=bind,src=$repo,dst=/repo,readonly" --workdir /repo --entrypoint python ad-aggregator:scalability-tests -m ruff format --no-cache --check src scripts tests aggregator.py
```

The two benchmark workers run installed production package code from the image,
not a host `PYTHONPATH` override. The test image adds only already-locked dev
tools. Its Dockerfile is separate from the production build.
