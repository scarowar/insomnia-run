# Maintainer Release Checklist

Insomnia Run wraps the Inso CLI for GitHub Actions. A release must preserve the action inputs, outputs, CLI commands, generated reports, and failure behavior.

## Owner Decisions

This is a solo-maintainer project. Recruiting another maintainer is not a prerequisite for technical work. Existing GitHub review rules remain unchanged: required reviews, CODEOWNERS, and branch protections must still be honored. Automated reviews are not independent human approval and do not authorize a bypass.

ClusterFuzzLite is explicitly deferred by the owner. This is an accepted remaining limitation, not a false positive or a claim that recognized fuzzing is implemented. Keep the deferral separate from confirmed code defects and scanner false-positive decisions.

Historical Scorecard results are not proof of a present code defect. Evaluate their evidence against the current candidate and record the disposition without rewriting history or dismissing alerts to improve a score.

No merge, tag, or release is authorized by this checklist or the candidate review. Keep the candidate unreleased; the owner's final release decision is separate from technical verification.

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
- Triage every open finding. Fix confirmed defects or record an explicit unresolved disposition; document false positives and owner-approved deferrals separately.
- Confirm the stable branch is protected by branch protection or a repository ruleset.
- Confirm CODEOWNERS is active for workflow and action changes.
- Confirm required checks include CI, Security, CodeQL, `SonarCloud Code Analysis`, Dependency Review, docs build, and E2E.

SonarQube Cloud uses the installed GitHub App with automatic analysis for this repository; no `SONAR_TOKEN` is needed. Do not add a concurrent CI SonarScanner, which conflicts with automatic analysis. Coverage is enforced separately by the CI test matrix at a minimum of 95%. The required `SonarCloud Code Analysis` check remains the Sonar quality gate.

Scanner policy must not be relaxed for a release.

Runtime and developer dependencies install from locked wheels with `--no-build`; the first-party wheel is built separately using the pinned native uv backend. Tool invocations use `--frozen --no-sync --no-build`. The Python 3.15 unit-test job has one reviewed `githubactions:S8541` exception: PyYAML 6.0.3 has no 3.15 wheel, so that test-only environment permits hash-locked source builds. Remove this exception when a compatible wheel is available. It does not apply to production installation.

### Scorecard Follow-Ups

The six open Scorecard alerts inspected on 2026-10-15 reference default-branch commit `31f82a6`, not this candidate. They have not been dismissed. Recheck their latest analyses before release:

- [Token permissions (#2)](https://github.com/scarowar/insomnia-run/security/code-scanning/2): explicit read-only workflow defaults are present in the candidate; a default-branch analysis must confirm the result after an approved merge.
- [CI tests (#3)](https://github.com/scarowar/insomnia-run/security/code-scanning/3): historical analysis found CI on 25 of 27 merged PRs. The ruleset now requires the unit matrix, lint/docs, Security, Dependency Review, and E2E alongside the existing checks. Do not alter past reviews or results to improve this score.
- [Branch protection (#1)](https://github.com/scarowar/insomnia-run/security/code-scanning/1): the candidate adds CODEOWNERS, but the existing one-review policy and administrator PR bypass remain unchanged. Those intentional policy choices need maintainer risk review, not a scanner suppression.
- [Code review (#5)](https://github.com/scarowar/insomnia-run/security/code-scanning/5): preserve the existing review requirements; the PR author cannot self-approve. Automated reviews do not replace required human approval or change historical review coverage. The solo-maintainer model does not require recruiting another maintainer for technical work or permit bypassing GitHub rules.
- [Best practices badge (#4)](https://github.com/scarowar/insomnia-run/security/code-scanning/4): OpenSSF enrollment and its attestations require maintainer participation. Do not display an unearned badge.
- [Fuzzing (#6)](https://github.com/scarowar/insomnia-run/security/code-scanning/6): generated-input tests cover Unicode report validity and repeated TAP plans, but this is not a Scorecard-recognized fuzzing integration. The owner's explicit ClusterFuzzLite deferral above records the accepted limitation; it is not a false-positive dismissal or an additional technical prerequisite.

## Release Validation

- Use the exact candidate commit or release tag for validation.
- Do not validate production examples from a floating `main` reference.
- Recheck the latest stable upstream release, exact binary help, versioned source, release notes, asset digests, and [compatibility matrix](docs/reference/compatibility.md). Resolve every supported-contract discrepancy or disclose a deliberate restriction; do not claim unverified universal conformance.
- Confirm the E2E test-command job passes the real-binary compatibility suite and audited option inventory against the installed candidate wheel.
- Confirm hosted runner and self-hosted runner behavior:
  - preinstalled `inso` is used only when its version exactly matches `inso-version`
  - fallback Inso installation works
  - the pinned `uv` version uses the validated runner Python and frozen runtime dependencies
  - Linux x64, macOS Intel, and macOS Apple Silicon with Rosetta run the exact candidate
  - a cold Inso install verifies its SHA-256 digest before extraction; a cache hit verifies it again
  - a corrupted cache is replaced and an unverifiable download fails closed
  - Markdown, JSON, and JUnit outputs are produced as documented
  - empty runs retain exit code `0` and show `No Assertions Executed` / `No assertions executed`, never successful test validation; all-skipped runs show `Skipped`
  - counts describe test results, including assertions, skips, and synthetic execution failures, not HTTP requests
  - raw Inso logs are absent from JSON and Markdown unless explicitly enabled
  - `verbose` diagnostics require explicit `include-raw-output` opt-in, with disclosure limits documented
  - opt-in report artifacts are uploaded for passing and failing tests before the final failure decision

For versions in `inso-checksums.json`, compare the pinned digests with the official `Kong/insomnia` release metadata. When updating a default, verify Kong's `inso-provenance.intoto.jsonl` with `slsa-verifier` before adding its digest. Other user-selected versions resolve their digest from the official release API and fail if no SHA-256 digest is available.

The `13.3.1` Linux x64 archive was verified with `slsa-verifier v2.7.1` against source `github.com/Kong/insomnia` and workflow input `version=13.3.1`. The signed subject digest matches `inso-checksums.json`. Verification identified Kong commit `abbf55892e16adafea6eb1d6c12af2fa85d32dc9` and the SLSA GitHub generator `v2.1.0`.

## Release Discipline

- Add a regression test for every important bug fix.
- Keep release changes small and directly tested.
- Keep docs and maintainer instructions short, canonical, and non-duplicative.
- Draft release notes from `CHANGELOG.md` and the tag diff.
- Keep release notes factual and user-facing.
