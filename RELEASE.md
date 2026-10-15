# Maintainer Release Checklist

Insomnia Run wraps the Inso CLI for GitHub Actions. A release must preserve the action inputs, outputs, CLI commands, generated reports, and failure behavior.

## Local Gates

Run from this repository:

```bash
uv run pytest --cov=src/insomnia_run --cov-report=term-missing
uv run pre-commit run --all-files
uv run zensical build
```

Do not release if action inputs, outputs, CLI options, or docs are out of sync.

## Security Gates

Before tagging:

- Review open security advisories.
- Review Dependabot alerts.
- Review code scanning alerts.
- Review secret scanning alerts.
- Review SonarQube Cloud findings.
- Resolve every open finding, regardless of severity, or record a narrow false-positive decision.
- Confirm the stable branch is protected by branch protection or a repository ruleset.
- Confirm CODEOWNERS is active for workflow and action changes.
- Confirm required checks include CI, Security, CodeQL, `SonarCloud Code Analysis`, Dependency Review, docs build, and E2E.

SonarQube Cloud uses the installed GitHub App with automatic analysis for this repository; no `SONAR_TOKEN` is needed. Do not add a concurrent CI SonarScanner, which conflicts with automatic analysis. Coverage is enforced separately by the CI test matrix at a minimum of 95%. The required `SonarCloud Code Analysis` check remains the Sonar quality gate.

Scanner policy must not be relaxed for a release.

Runtime and developer dependencies install from locked wheels with `--no-build`; the first-party wheel is built separately using the pinned native uv backend. Tool invocations use `--frozen --no-sync --no-build`. The Python 3.15 unit-test job has one reviewed `githubactions:S8541` exception: PyYAML 6.0.3 has no 3.15 wheel, so that test-only environment permits hash-locked source builds. Remove this exception when a compatible wheel is available. It does not apply to production installation.

## Release Validation

- Use the exact candidate commit or release tag for validation.
- Do not validate production examples from a floating `main` reference.
- Confirm hosted runner and self-hosted runner behavior:
  - preinstalled `inso` is used when available
  - fallback Inso installation works
  - the pinned `uv` version uses the validated runner Python and frozen runtime dependencies
  - Linux x64, macOS Intel, and macOS Apple Silicon with Rosetta run the exact candidate
  - a cold Inso install verifies its SHA-256 digest before extraction; a cache hit verifies it again
  - a corrupted cache is replaced and an unverifiable download fails closed
  - Markdown, JSON, and JUnit outputs are produced as documented
  - raw Inso logs are absent from JSON and Markdown unless explicitly enabled
  - opt-in report artifacts are uploaded for passing and failing tests before the final failure decision

For versions in `inso-checksums.json`, compare the pinned digests with the official `Kong/insomnia` release metadata. When updating a default, verify Kong's `inso-provenance.intoto.jsonl` with `slsa-verifier` before adding its digest. Other user-selected versions resolve their digest from the official release API and fail if no SHA-256 digest is available.

The `13.3.1` Linux x64 archive was verified with `slsa-verifier v2.7.1` against source `github.com/Kong/insomnia` and workflow input `version=13.3.1`. The signed subject digest matches `inso-checksums.json`. Verification identified Kong commit `abbf55892e16adafea6eb1d6c12af2fa85d32dc9` and the SLSA GitHub generator `v2.1.0`.

## Release Discipline

- Add a regression test for every important bug fix.
- Keep release changes small and directly tested.
- Keep docs and maintainer instructions short, canonical, and non-duplicative.
- Draft release notes from `CHANGELOG.md` and the tag diff.
- Keep release notes factual and user-facing.
