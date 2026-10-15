# Contributing

Open bugs and feature requests in [GitHub Issues](https://github.com/scarowar/insomnia-run/issues). Include reproduction steps for bugs. Report vulnerabilities through [SECURITY.md](SECURITY.md), not public issues.

## Development

Use Python 3.12 and uv 0.11.11 for local development. CI tests Python 3.10 through 3.15.

```sh
uv sync --frozen --dev --no-build --no-install-project
uv pip install --no-deps --editable .
uv run --frozen --no-sync --no-build pre-commit install --hook-type pre-commit --hook-type commit-msg
```

The first command installs locked dependency wheels. The second builds only this repository's editable package using its pinned build backend, so source edits take effect without reinstalling dependencies.

Run checks before submitting a pull request:

```sh
uv run --frozen --no-sync --no-build pytest --cov=insomnia_run --cov-fail-under=95
uv run --frozen --no-sync --no-build pre-commit run --all-files
uv run --frozen --no-sync --no-build mypy src/insomnia_run --ignore-missing-imports
uv run --frozen --no-sync --no-build zensical build --strict
```

Ruff checks and formats Python. Its rule selectors are explicit in `pyproject.toml` so tool upgrades do not silently change the lint policy. Pre-commit also checks YAML, JSON, workflows, dependencies, and security rules. Gitlint runs at the `commit-msg` stage; `--all-files` does not run it.

To test against an official Inso release, verify its archive digest and set its executable path:

```sh
INSOMNIA_RUN_INSO_BINARY=/path/to/inso uv run --frozen --no-sync --no-build pytest tests/test_inso_compatibility.py
```

These tests start a local HTTP fixture on port 8765. No external test API is required.

## Pull Requests

- Branch from `main` and keep changes focused. Separate independent fixes and refactors where practical.
- Add behavioral regression tests for bug fixes. Keep fixtures local and deterministic.
- Update user documentation when inputs, outputs, defaults, or supported runners change.
- Explain the problem, the approach, migration impact, and verification in the PR description. Link issues and relevant documentation.
- Keep temporary investigation notes and editing instructions out of product documentation and source comments.

Follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Commit Messages

Use a short, imperative subject, no longer than 72 characters, with a prefix such as `fix:`, `feat:`, `docs:`, `test:`, `ci:`, or `refactor:`. Leave a blank line before a body explaining why the change is needed. Gitlint requires a body; wrap body lines at 80 characters.

```text
fix: stop Inso descendants when execution times out

Terminate the process group before writing the failure report so child
processes cannot continue issuing requests after the execution timeout.
```
