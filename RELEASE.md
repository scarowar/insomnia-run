# Release Checklist

## Validate the Commit

- Run the [local checks](CONTRIBUTING.md#development) and confirm all required GitHub checks pass on the release commit.
- Confirm the Python 3.10-3.15 matrix and Linux, macOS Intel, and Apple Silicon E2E jobs pass.
- Verify the real-Inso compatibility suite runs against the installed wheel, not an editable checkout or another binary on PATH.
- Check that action inputs, CLI options, examples, and the [compatibility reference](docs/reference/compatibility.md) agree.
- Review migration guidance for changed defaults, output schemas, and runner requirements.

## Check Installation and Reports

- Test a cold install, verified cache hit, corrupt-cache recovery, and an exact-version preinstalled Inso.
- Test offline installation with the required tools and locked packages already cached.
- Confirm failing Inso runs fail the action unless `fail-on-error` is disabled.
- Confirm empty and all-skipped runs have neutral summaries, and incomplete TAP fails.
- Inspect Markdown, JSON, and JUnit reports from passing and failing runs. Verify opt-in artifacts arrive before the final failure step.
- Check hostile names and raw diagnostics with GitHub's GFM renderer, including long backtick runs, mentions, and HTML. CommonMark-only rendering is not sufficient.
- Confirm raw diagnostics are omitted by default. Check explicit opt-in without using real credentials.

## Review Security

- Review advisories, dependency alerts, code-scanning findings, secret-scanning findings, and Sonar issues, including issues that do not fail the quality gate.
- Resolve confirmed defects or document a specific exception with its risk and rationale.
- Check the base branch's required checks, CODEOWNERS, review policy, and signature requirements. Do not weaken them to publish a release.
- Verify dependency-action references are pinned and runtime dependencies still install from locked wheels without source builds.

SonarQube Cloud uses the GitHub App's automatic analysis. Do not add a concurrent CI SonarScanner; it conflicts with automatic analysis. No `SONAR_TOKEN` is needed. CI enforces at least 95% coverage independently.

The Python 3.15 test environment permits hash-locked PyYAML 6.0.3 source builds because no compatible wheel is available. This exception does not apply to runtime installation; remove it when a wheel becomes available.

## Update Inso

- Check the latest stable Kong release, release notes, exact binary help, and versioned source before changing the default.
- Update the option inventory and compatibility tests for changed flags, defaults, units, or output formats.
- Match asset names and SHA-256 digests against the official release metadata.
- Verify `inso-provenance.intoto.jsonl` with `slsa-verifier` against `github.com/Kong/insomnia` and the requested version before adding bundled digests.
- Run the updated binary on every supported automatic-install platform, including Rosetta on Apple Silicon.

## Publish

- Update `CHANGELOG.md` with user-facing changes and the release date. Update version references and remove unreleased notices.
- Use the tested commit for the version tag and release notes.
- Describe supported platforms and migration requirements without claiming unverified compatibility or security certification.
