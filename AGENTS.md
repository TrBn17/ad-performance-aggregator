# Repository engineering guidelines

## Scope and task instructions
- This file contains persistent engineering rules. Task-specific requirements belong in the current user request; `PROMPTS.md` is user-maintained history, not an execution queue. Do not edit it unless explicitly requested.
- Inspect relevant files and the working tree before changes. Preserve unrelated work and keep changes limited to the requested task; do not implement future prompts or speculative features.
- Current repository: `data/ad_data.csv` contains advertising metrics and is approximately 1 GB. No Python package, dependency manifest, or test configuration exists yet. Do not assume tools or commands are configured.

## Python quality and architecture
- Follow PEP 8, use descriptive names, and add type hints to public interfaces. Keep functions focused and avoid hidden mutable state, import-time I/O, and unexplained constants.
- Prefer straightforward functions and standard-library facilities. Introduce classes, frameworks, or abstraction layers only when concrete requirements justify them.
- Separate parsing and filesystem I/O from validation, calculations, and presentation so core logic can be tested independently.
- Declare required Python versions and dependencies in project metadata when introduced. Use an isolated environment, justify new dependencies, and keep dependency resolution reproducible; never rely on undocumented local installations.
- Use `pathlib` for paths and context managers for resources. Avoid machine-specific paths in application code.

## Data correctness and failures
- Preserve source data. Use small synthetic fixtures for tests; avoid copying or rewriting the large CSV during routine work.
- Validate schema and values at input boundaries. Define behavior for empty input, missing or malformed fields, invalid dates, duplicate records, non-finite numbers, and zero denominators; never silently drop or coerce records without an explicit policy.
- Make numeric precision, rounding, aggregation semantics, and output ordering explicit. Validate derived metrics against independently calculated examples.
- Catch specific exceptions where recovery or useful context is possible. Preserve exception causes and report actionable errors; never hide failures behind success-shaped defaults.

## Verification and performance
- Test observable behavior with deterministic, small fixtures, including relevant boundary and failure cases. Add regression coverage for bug fixes and compare aggregation results with a simple independent reference calculation.
- Run checks appropriate to the change using the project's actual tooling. Record exact commands and outcomes; distinguish executed, failed, and unexecuted checks. Never invent test passes, coverage, or benchmark results.
- Inspect file sizes before loading data. Prefer bounded-memory processing when practical for large inputs, but measure before adding complexity, concurrency, or alternative engines.
- Optimize demonstrated bottlenecks. Record baseline and revised timings and peak memory with the same command, input identity/size, Python/dependency versions, hardware, and run conditions. Repeat measurements and verify unchanged results before claiming improvement.

## Documentation and agent reporting
- Keep documentation concise: explain setup, runnable commands, public interfaces, assumptions, and non-obvious decisions. Comments should explain intent rather than restate code.
- Resolve routine implementation choices within scope; ask for clarification when ambiguity materially changes correctness or scope.
- Before finishing, inspect the final changes for accidental edits. Report what changed, verification actually performed, and remaining limitations. Do not claim completion of work that was not performed.
