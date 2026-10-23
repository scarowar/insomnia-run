# Contributing

Open bugs and feature requests in [GitHub Issues](https://github.com/scarowar/insomnia-run/issues). Include reproduction steps for bugs. Report vulnerabilities through [SECURITY.md](SECURITY.md), not public issues.

## Development

Use Python 3.12 and uv 0.13.1 for local development. CI tests Python 3.10 through 3.15.

```sh
uv sync --frozen --dev --no-build --no-install-project
uv pip install --no-deps --editable .
uv run --frozen --no-sync --no-build pre-commit install --hook-type pre-commit --hook-type commit-msg
```

The first command installs locked dependency wheels. The second builds only this repository's editable package using its pinned build backend, so source edits take effect without reinstalling dependencies.

Run checks before submitting a pull request:

```sh
uv run --frozen --no-sync --no-build pytest --cov=insomnia_run --cov=scripts --cov-fail-under=95
uv run --frozen --no-sync --no-build pre-commit run --all-files
uv run --frozen --no-sync --no-build pre-commit run gitleaks-ci --hook-stage manual --all-files
uv run --frozen --no-sync --no-build mypy src/insomnia_run scripts --ignore-missing-imports
uv run --frozen --no-sync --no-build zensical build --strict
```

Ruff checks and formats Python. Its rule selectors are explicit in `pyproject.toml` so tool upgrades do not silently change the lint policy. Pre-commit also checks YAML, JSON, workflows, dependencies, and security rules. Gitlint runs at the `commit-msg` stage; `--all-files` does not run it.

The local secret hook scans staged changes; the manual `gitleaks-ci` hook scans fetched Git history. Keep a full clone for that check. `.gitleaksignore` contains only commit-specific fingerprints for confirmed non-issued historical test fixtures, not file exclusions.

To test against an official Inso release, verify its archive digest and set its executable path:

```sh
INSOMNIA_RUN_INSO_BINARY=/path/to/inso uv run --frozen --no-sync --no-build pytest tests/test_inso_compatibility.py tests/test_native_compatibility.py
```

These tests start a local HTTP fixture on port 8765. No external test API is required. Run them serially to avoid port conflicts. Include real-binary coverage when changing native/TAP parsing, error classification, or Inso flag mapping.

## Pull Requests

- Branch from `main` and keep changes focused. Separate independent fixes and refactors where practical.
- Add behavioral regression tests for bug fixes. Keep fixtures local and deterministic.
- Update user documentation when inputs, outputs, defaults, or supported runners change.
- Explain the problem, the approach, migration impact, and verification in the PR description. Link issues and relevant documentation.

Follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Commit Messages

Use a short, imperative subject, no longer than 72 characters, with a prefix such as `fix:`, `feat:`, `docs:`, `test:`, `ci:`, or `refactor:`. Leave a blank line before a body explaining why the change is needed. Gitlint requires a body; wrap body lines at 80 characters.

```text
fix: stop Inso descendants when execution times out

Terminate the process group before writing the failure report so child
processes cannot continue issuing requests after the execution timeout.
```

## Release Preparation

Release tooling is development-only. Install the locked release group before using it:

```sh
uv sync --frozen --dev --group release --no-build --no-install-project
uv pip install --no-deps --editable .
python scripts/prepare_release.py --dry-run
```

The helper uses pinned `python-semantic-release 10.7.0`. Without `--dry-run`, it prepares local version/changelog files and refreshes the lockfile; it does not commit, tag, push, build, or publish. It requires a clean worktree. Review the generated diff and release notes, then open a normal PR with the required checks.

A maintainer creates a signed annotated `vMAJOR.MINOR.PATCH` tag on the exact approved, tested commit. The manually dispatched Release workflow verifies the trusted signing identity, tag/commit/version agreement, and protected-branch checks. `publish: false` builds and validates candidates without creating a public release.

The workflow builds wheel/sdist distributions, three native runtime wheelhouses for its selected Python/platforms, hash requirements, identity manifests, checksums, and CycloneDX SBOMs. Bundle builds use the same reviewed CPython 3.14.8 distribution from `python-downloads.json` as bundle consumers; matching only the Python version is insufficient because platform identities must also match. Build, assembly, and publication jobs install checksum-pinned `uv 0.13.1` without restored uv caches. OIDC provides build-provenance attestations. Run the platform and artifact checks in [RELEASE.md](RELEASE.md) before publication.

Publication uses the workflow's built-in `GITHUB_TOKEN` with Contents: write and read access to checks, pull requests, and commit statuses. No personal token or protected environment setup is required. Before every publishing dispatch, a maintainer must confirm that **Settings → General → Releases → Enable release immutability** is enabled. The publisher does not query that administration-only setting, so it cannot detect if someone disables it. Use `publish: false` to build and validate candidates without publishing. See [enabling immutable releases](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/establish-provenance-and-integrity/prevent-release-changes).

The publisher assembles and verifies the complete draft before publishing. Recovery accepts identical existing draft assets and uploads missing assets; conflicting assets, conflicting targets, and already published releases are refused. Treat semantic-version tags and assets as immutable. GitHub-enforced tag/asset locking additionally requires the repository's [immutable releases setting](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases); publisher refusal alone does not enable it. Moving-major tags are a separate policy and are not moved by this workflow.
