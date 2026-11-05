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