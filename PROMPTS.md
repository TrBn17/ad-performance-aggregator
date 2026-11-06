# PROMPTS.md

## Prompt 1 — Initialize Agent Guidelines

Create an `AGENTS.md` file at the repository root following OpenAI Codex best practices.

The file should define persistent engineering guidelines for this repository, including:

- Code quality, readability, maintainability, and Python conventions.
- Software architecture and dependency management.
- Error handling and edge-case awareness.
- Testing, correctness verification, and performance profiling.
- Concise technical documentation.
- Agent workflow, scope control, and reporting standards.

Keep `AGENTS.md` concise, actionable, and technology-aware without duplicating the challenge specification or implementation tasks.

Clearly separate persistent repository instructions from task-specific prompts.

Additional constraints:
- Inspect the existing repository before writing.
- Prefer simple solutions over unnecessary abstractions.
- Require evidence-based optimization and reproducible verification.
- Never fabricate benchmark results or claim unexecuted tests.
- Do not modify `PROMPTS.md`; I will maintain the raw prompt history manually.
- Do not implement application features yet.

Create only `AGENTS.md` and briefly summarize its contents.

## Prompt 2
I have unzip data for you in folder /data.

Implement the FLINTERS challenge in `REQUIREMENTS.md`, following `AGENTS.md`.

Use Python 3.12+ and implement two independent approaches:

1. **Baseline:** Standard-library CSV streaming with dictionary aggregation.
2. **Optimized:** Polars LazyFrame with streaming execution where supported.

Both must satisfy the same requirements and produce equivalent, deterministic CSV outputs.

Use pytest to validate correctness and edge cases. Benchmark both approaches on `data/ad_data.csv` (~1 GB), comparing wall-clock time, peak RSS memory, and throughput.

Provide a CLI with `--engine python|polars`, defaulting to the best verified approach.

Include Docker support and a concise README documenting architecture, usage, actual benchmark results, and trade-offs.

Do not modify `AGENTS.md`, `REQUIREMENTS.md`, or `PROMPTS.md`. Never fabricate measurements.

## Prompt 3

Review both implementations against `REQUIREMENTS.md` and `AGENTS.md`.

- Verify correctness, edge cases, deterministic ranking, and output equivalence.
- Run all tests and benchmark both approaches on the full dataset.
- Identify performance bottlenecks and optimize only where measurements justify changes.
- Compare execution time, peak RSS memory, and throughput.
- Verify CLI behavior, Docker execution, and generated CSV files.
- Review code quality, dependencies, error handling, and maintainability.
- Update README with verified results and a concise comparison of both approaches.

Fix any issues found, rerun relevant checks, and recommend the best default engine based on evidence.

Do not modify `AGENTS.md`, `REQUIREMENTS.md`, or `PROMPTS.md`. Never fabricate results.

## Prompt 4 — Final Cleanup & GitHub Push

Prepare the repository for final submission.

- Simplify `README.md`: concise, clear, easy to read, with essential setup, usage, benchmark results, and AI disclosure.
- Review `.gitignore` to exclude datasets, caches, temporary files, virtual environments, and secrets.
- Ensure all required source files, tests, output CSVs, and documentation are included.
- Run final tests and verify the generated outputs.
- Review `git status` and staged changes to ensure no large or sensitive files are committed.
- Commit changes with a clear message and push to the `main` branch.

Preserve `AGENTS.md`, `REQUIREMENTS.md`, and `PROMPTS.md` without modification.

Do not force-push or overwrite remote changes. Report the commit hash, repository URL, and push status.

## Prompt 5 (Additional)
Add link data to readme: https://github.com/flinters-vietnam/recruitment/blob/main/fv-sec-001-software-engineer-challenge/ad_data.csv.zip, commit and push to main branch

## Prompt 6 - Optimization (Python)

As we observed in previous benchmarks, the Python implementation is significantly slower than Polars but consumes very little memory.

Let's experiment with two optimization approaches:

1. **Optimized Streaming:** Reduce unnecessary object creation, generator overhead, and redundant validation.
2. **Chunked Multiprocessing:** Process CSV chunks in parallel using safe record boundaries, then merge campaign aggregates.

Keep the current Python implementation as the baseline. Benchmark all three approaches on the full dataset, comparing execution time, peak RAM, and throughput.

Ensure identical outputs, preserve correctness and validation, and analyze the performance–memory trade-offs.

Document the experimental results and recommend the best approach based on measured evidence.

Do not modify `AGENTS.md`, `REQUIREMENTS.md`, or `PROMPTS.md`.

## Prompt 7 - Optimization (Polars)

Our current Polars implementation processes ~1 GB in about 5 seconds but consumes nearly 2 GB of RAM.

Let's explore ways to reduce peak memory usage while maintaining strong performance:

1. **Thread tuning:** Benchmark different `POLARS_MAX_THREADS` settings (2, 4, 8, 16).
2. **Expression optimization:** Reduce unnecessary allocations, intermediate columns, and expensive type conversions.
3. **Streaming optimization:** Investigate execution plans, chunk sizes, and bounded batch processing.

Keep the current implementation as the baseline. Benchmark each approach on the full dataset, measuring execution time, peak RSS, and throughput.

Preserve strict validation and exact output equivalence. Aim for **under 1 GB RAM and under 10 seconds**, if achievable.

Document all experiments, compare trade-offs, and retain the best-performing practical solution based on measured evidence.

Do not modify `AGENTS.md`, `REQUIREMENTS.md`, or `PROMPTS.md`.

## Prompt 8 — Docker/Linux & Scalability Validation

The latest Polars optimization reduced peak RAM by ~72% while maintaining good performance. Let's validate its reliability and scalability further.

1. **Docker/Linux validation:** Build and run the updated implementation in Docker. Verify correctness, execution time, and peak memory usage.
2. **High-cardinality testing:** Generate reproducible synthetic datasets with significantly more campaigns (e.g., 1K, 10K, 100K), while keeping the total dataset size comparable to the original (~1 GB).
3. **Performance comparison:** Benchmark the original Polars baseline against the optimized implementation, measuring runtime, peak RSS, throughput, and memory scaling.
4. **Correctness:** Verify identical campaign aggregates and output CSVs across implementations.

Analyze whether the optimized implementation maintains its memory advantage as campaign cardinality increases.

Document the results, limitations, and recommendations. Preserve existing benchmarks and avoid changing the production implementation unless a correctness issue is discovered.

Do not modify `AGENTS.md`, `REQUIREMENTS.md`, or `PROMPTS.md`.