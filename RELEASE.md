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
- Confirm required checks include CI, Security, CodeQL, SonarQube, Dependency Review, docs build, and E2E.

Scanner policy must not be relaxed for a release.

## Release Validation

- Use the exact candidate commit or release tag for validation.
- Do not validate production examples from a floating `main` reference.
- Confirm hosted runner and self-hosted runner behavior:
  - preinstalled `inso` is used when available
  - fallback Inso installation works
  - runtime action installation does not use `uv`
  - Markdown, JSON, and JUnit outputs are produced as documented

## Release Discipline

- Add a regression test for every important bug fix.
- Keep release changes small and directly tested.
- Keep docs and maintainer instructions short, canonical, and non-duplicative.
- Draft release notes from `CHANGELOG.md` and the tag diff.
- Keep release notes factual and user-facing.
