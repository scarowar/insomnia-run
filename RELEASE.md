# Release Checklist

## Validate the Commit

- Run the [local checks](CONTRIBUTING.md#development) and confirm all required GitHub checks pass on the release commit.
- Confirm the Python 3.10-3.15 matrix and Linux, macOS Intel, and Apple Silicon E2E jobs pass.
- Verify the real-Inso compatibility suite runs against the installed wheel, not an editable checkout or another binary on PATH.
- Check that action inputs, CLI options, examples, and the [compatibility reference](docs/reference/compatibility.md) agree.
- Review migration guidance for changed defaults, output schemas, and runner requirements.

## Extended Release Validation

- Require the `Release validation` check on the exact candidate tree. Publication refuses missing, skipped, or failed validation even if the aggregate coverage gate passes.
- The validation workflow runs for version/lockfile PRs and can also be dispatched on a candidate branch. It installs the candidate wheel, verified Inso, locked release tools, and the pinned secret scanner before running the complete suite. Unexpected skips fail validation.
- Inspect the retained `release-validation` artifact: pytest results, JSON/JUnit evidence, Markdown and GitHub-rendered HTML for mixed, large, assertion-free, and hostile raw-output cases, plus machine-readable acceptance results.

## Check Installation and Reports

- Test a cold install, verified cache hit, corrupt-cache recovery, and an exact-version preinstalled Inso.
- Test offline installation with the required tools and locked packages already cached.
- Confirm `fail-on-error: false` permits assertion failures only; execution and report errors must still fail the action.
- Confirm empty and all-skipped runs have neutral summaries, and incomplete TAP fails.
- Inspect Markdown, JSON, and JUnit reports from passing and failing runs. Verify opt-in artifacts arrive before the final failure step.
- Check hostile names and raw diagnostics with GitHub's GFM renderer, including long backtick runs, mentions, and HTML. CommonMark-only rendering is not sufficient.
- Confirm raw diagnostics are omitted by default. Check explicit opt-in without using real credentials.

## Review Security

- Review advisories, dependency alerts, code-scanning findings, secret-scanning findings, and Sonar issues, including issues that do not fail the quality gate.
- Resolve confirmed defects or document a specific exception with its risk and rationale.
- Check the base branch's required checks, CODEOWNERS, review policy, and signature requirements. Do not weaken them to publish a release.
- Verify dependency-action references are pinned and runtime dependencies still install from locked wheels without source builds.

SonarQube Cloud uses automatic GitHub App analysis. CI enforces at least 95% coverage separately.

The Python 3.15 test environment permits hash-locked PyYAML 6.0.3 source builds because no compatible wheel is available. This exception does not apply to runtime installation; remove it when a wheel becomes available.

## Update Inso

- Check the latest stable Kong release, release notes, exact binary help, and versioned source before changing the default.
- Update the option inventory and compatibility tests for changed flags, defaults, units, or output formats.
- Match asset names and SHA-256 digests against the official release metadata.
- Verify `inso-provenance.intoto.jsonl` with `slsa-verifier` against `github.com/Kong/insomnia` and the requested version before adding bundled digests.
- Run the updated binary on every supported automatic-install platform, including Rosetta on Apple Silicon.

## Validate Release Bundles

- Build bundles with the reviewed interpreter from `python-downloads.json`, matching the consumer's Python and platform identities on Linux x64, macOS Intel, and macOS ARM64.
- Confirm build, assembly, and publication jobs install checksum-pinned `uv 0.13.1` with caching disabled; bundle validation also invokes uv.
- Dispatch the Release workflow from `main` with `publish: false` for the signed release tag and exact tested commit. Confirm all three native bundles and the assembled candidate validate before publishing.
- Consume each candidate bundle with the action on its matching platform and an empty dependency cache. A passing PR E2E run alone does not validate the assembled release candidate.

## Publish

- Confirm **Settings → General → Releases → Enable release immutability** is enabled before dispatching the release workflow. This is a maintainer check; the workflow uses `GITHUB_TOKEN` and does not read the administration-only setting.
- Update `CHANGELOG.md` with user-facing changes and the release date. Confirm documentation examples and changelog comparison links reference the release tag.
- Use the tested commit for the version tag and release notes.
- Describe supported platforms and migration requirements without claiming unverified compatibility or security certification.
