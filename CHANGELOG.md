# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.2.1]

### Fixed

- Preserve request summaries and failure descriptions under Markdown budgets, remove the 50-assertion cutoff, and account for omissions within each request.
- Render job summaries independently from bounded PR-comment Markdown; show compact totals, per-request counts, and failed-assertion tables with separate expandable diagnostics.
- Redact literal and decoded override values, credential-bearing dictionary entries, and secrets in dynamic keys without losing colliding entries.
- Filter recognized cloud/package credentials and GitHub/Actions/state tokens from the Inso child while preserving proxy and certificate settings.
- Reject incomplete passing evidence consistently, retain interrupted TAP diagnostics, and bound annotations after escaping.
- Preserve full JUnit evidence while bounding summary attributes, omit unknown empty-suite timing, and validate runtime options before report allocation.

### Changed

- Identify incompatible inputs and explain numeric input types, ranges, and units without echoing supplied values.
- Require installed-wheel release validation with real integrations, no skipped tests, and rendered-report acceptance evidence before publication.
- Update development-tool locks to patched filelock 4.2.1 and virtualenv 21.14.13. Pre-commit and dependency auditing require Python 3.11+; Python 3.10 runtime/test support is retained.

## [0.2.0] - 2026-10-23

### Added

- Normalized version 1 JSON reports with request execution occurrences, assertion messages, nullable seconds timings, source/completeness metadata, and structured run errors.
- JSON/Markdown file outputs, explicit raw-file opt-in, report-directory and count outputs, and a bounded JSON convenience output with an omission flag.
- Request-grouped Markdown, redacted failure reasons, trusted execution heartbeats, and at most ten failure annotations.
- Owned comment replacement scoped to workflow, job, matrix, and comment tag, with stale-run detection under caller serialization. Comment API errors warn; fork/Dependabot PR comments are skipped.
- Optional report uploads for GitHub.com and GitHub Enterprise Cloud. GHES callers can use report files with a compatible uploader.
- Explicit local/HTTPS Inso archives, caller-supplied digests, origin-scoped download credentials, optional verified runtime bundles, and offline installation.
- Maintainer-triggered release preparation and signed-tag candidate/publishing workflows with checksums, SBOMs, draft recovery, and OIDC attestations.

### Changed

- Default to Inso CLI `13.3.1` and pin `uv`/`uv_build` to `0.13.1`.
- Use private native collection JSON when supported; retain TAP for legacy suites, older collection CLIs, and trustworthy partial recovery.
- Distinguish assertion-only exit `1`, wrapper/configuration/report exit `2`, and Inso execution/timeout/protocol exit `3`. `fail-on-error: "false"` permits only `1`.
- Reject verbose legacy suites before execution. Verbose collections require native reporting and do not trust stdout TAP when a native report is absent.
- Keep source installation with frozen runtime dependency wheels as the default; bundles require an explicit trusted digest and matching source/lock/Python/platform identity.
- Separate instance comment credentials, public GitHub download credentials, and runner artifact credentials.
- Make unbundled Inso archive digests explicit instead of fetching release checksum metadata. Cache identities include trusted digest and custom archive source.
- Refresh patched dependency floors/locks and retain CI coverage checks across Python 3.10 through 3.15.

### Fixed

- Build release bundles with the consumer's reviewed Python distribution and install pinned uv in assembly and publication jobs.
- Preserve completed evidence and report later script/process errors separately from failed assertions.
- Mark incomplete runs without inventing request records or timings, and preserve native skip status.
- Stop Inso descendant processes on timeout and retain trustworthy partial output.
- Keep JSON stderr valid after a report exists, even when another report write fails; use files rather than process-stream parsing in the action.
- Validate report destinations before execution and writing; reject control-file overwrites, collisions, and escaping symlinks.
- Keep the current invocation's JUnit report in the upload directory even with a custom destination.
- Preserve quotes, backslashes, and interior spaces while trimming comma-separated item/folder inputs.
- Bound Markdown by complete blocks without truncating normalized JSON/JUnit result lists.

### Security

- Apply shared best-effort redaction to published reports and explicitly supplied sensitive values; keep raw diagnostics disabled by default.
- Permit only explicitly named non-credential response headers. Native/full-data captures remain private and are not uploaded.
- Verify archives before extraction, reverify cache restores, and reject digest/identity conflicts rather than weakening checks.
- Disable Inso telemetry for child processes and keep runtime dependency source builds disabled.
- Retain SHA-pinned dependency actions and scoped workflow permissions.

## [0.1.2] - 2026-01-06

### Fixed

- Add the Python executable directory to the action PATH.

## [0.1.1] - 2026-01-06

### Fixed

- Remove the setup-python step and improve installation error handling.

## [0.1.0] - 2026-01-04

### Added

- Initial Insomnia Run action release.

[0.2.1]: https://github.com/scarowar/insomnia-run/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/scarowar/insomnia-run/compare/v0.1.2...v0.2.0
[0.1.2]: https://github.com/scarowar/insomnia-run/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/scarowar/insomnia-run/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/scarowar/insomnia-run/releases/tag/v0.1.0
