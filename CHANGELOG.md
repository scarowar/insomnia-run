# Changelog

All notable changes to Insomnia Run are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.2.0] - Unreleased

### Changed

- Default to the verified Inso CLI `13.3.1` release.
- Install the action package with a pinned `uv` toolchain and frozen lockfile.
- Pass GitHub authentication to `setup-uv` and disable cache writes for untrusted comment-triggered runs.
- Refresh locked development dependencies to patched versions.
- Maintain the uv lockfile with Dependabot's native uv updater.
- Use Pydantic 2.14.1 for current Python support, with a test matrix covering Python 3.10 through 3.15.
- Hide raw Inso output from Markdown and JSON reports unless explicitly enabled.
- Separate getting started, collections, test suites, secrets, examples, reference, migration, and troubleshooting documentation.

### Added

- SHA-256 verification before extracting official Inso archives, including cache restores.
- Inso archive caching with version, operating system, and architecture isolation; cache writes are disabled for untrusted comment triggers.
- Optional report artifact uploads on GitHub.com, with configurable names and retention, including failing test runs.
- JUnit XML report generation for CI test reporting integrations.
- Explicit comment targeting for manual, scheduled, deployment, and push workflows.
- Exact-version detection of preinstalled Inso for self-hosted runners.
- Security, CodeQL, Dependency Review, Scorecard, pre-commit, and E2E release checks, with SonarQube Cloud GitHub App analysis.
- Migration guidance for upgrading from v0.1.x.

### Fixed

- Validate complete TAP plans and bailouts, protect option-like target identifiers, and label empty/skipped reports without claiming successful assertions.
- Stop the Inso process group on timeout and decode diagnostics as UTF-8 with replacement for invalid bytes.
- Keep execution diagnostics and exception locals out of default reports, including synthetic failures and report-write errors.
- Reject invalid iteration and timeout bounds before execution while preserving explicit zero request timeouts and delays.
- Prevent custom JUnit filenames from injecting workflow outputs or republishing stale reports.
- Preserve the current invocation's selected preinstalled Inso after an earlier installation.
- Require valid requested JSON output and scan committed content in CI rather than an empty staging area.
- Stop retrying failed Inso release-metadata requests immediately, including rate-limit and authorization errors.
- Keep CLI configuration errors fatal when test failures are allowed with `fail-on-error: "false"`.
- Render Markdown names as literal text, use collision-safe raw-output fences, and limit displayed results and raw diagnostics to fit GitHub comments without truncating JSON or JUnit results.
- Keep JUnit reports valid when test names contain XML-forbidden characters, and preserve legal attribute whitespace.
- Preserve nonzero Inso exits as report failures, including diagnostics emitted on stdout or after partial TAP output.
- Create Inso's package cache directory before invoking the CLI on clean runners.
- Omit raw logs from JSON unless explicitly requested, matching Markdown privacy defaults.
- Aggregate per-request TAP plans and assign unique result IDs across collection requests.
- Fail when action output or job summary publication fails while preserving expected test exit codes.
- Use the validated runner Python without inheriting the caller's project constraints or downloading another interpreter.
- Generate output delimiters portably and report macOS Rosetta requirements and unsupported Windows runners clearly.
- Preserve runner proxy environment variables when no proxy input overrides them.
- Use the existing token-free Sonar GitHub App integration without a conflicting CI scanner; CI enforces coverage independently.
- Correct secret-mapping examples and replace a legacy fixture script that silently executed zero assertions.
- Replace broad default workflow token permissions with explicit read permissions.

### Security

- Restrict release downloads and redirects to HTTPS, and confine integrity-helper paths to runner temporary storage.
- Install runtime dependencies from locked wheels without executing third-party source builds.
- Third-party GitHub Actions are pinned by full commit SHA.
- Workflow tokens use least privilege.
- Security scanning includes dependency audit, Bandit, Zizmor, Gitleaks, actionlint, CodeQL, SonarQube, and SBOM generation.
- Raw command output is not included in public reports by default.

## [0.1.2] - 2026-01-06

### Fixed

- Add the Python executable directory to the action PATH.

## [0.1.1] - 2026-01-06

### Fixed

- Remove the setup-python step and improve installation error handling.

## [0.1.0] - 2026-01-04

### Added

- Initial Insomnia Run action release.

[0.2.0]: https://github.com/scarowar/insomnia-run/compare/v0.1.2...release/v0.2.0-hardening
[0.1.2]: https://github.com/scarowar/insomnia-run/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/scarowar/insomnia-run/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/scarowar/insomnia-run/releases/tag/v0.1.0
