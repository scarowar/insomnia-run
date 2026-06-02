# Changelog

All notable changes to Insomnia Run are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.2.0] - 2026-06-02

### Added

- JUnit XML report generation for CI test reporting integrations.
- Explicit comment targeting for manual, scheduled, deployment, and push workflows.
- Inso CLI detection before setup, allowing self-hosted runners to provide `inso` directly.
- Security, SonarQube, CodeQL, Dependency Review, Scorecard, pre-commit, and E2E release gates.
- Migration guidance for upgrading from v0.1.x.

### Changed

- The action installs its Python package through a virtual environment instead of installing `uv` at runtime.
- Raw Inso output is hidden from Markdown reports unless explicitly enabled.
- Documentation now separates getting started, collections, test suites, secrets, examples, reference, migration, and troubleshooting.
- Workflow examples use reviewed release references and documented report outputs.

### Fixed

- GitHub API rate-limit failures caused by runtime `setup-uv` usage.
- Open dependency vulnerabilities in documentation and test dependencies.
- PR comments can now be posted from non-PR workflow triggers when an issue or pull request number is provided.

### Security

- Third-party GitHub Actions are pinned by full commit SHA.
- Workflow tokens use least privilege.
- Security scanning includes dependency audit, Bandit, Semgrep, Zizmor, Gitleaks, actionlint, CodeQL, SonarQube, and SBOM generation.
- Raw command output is not included in public reports by default.

## [0.1.0] - 2025-07-27

### Added

- Initial Insomnia Run action release.

[0.2.0]: https://github.com/scarowar/insomnia-run/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/scarowar/insomnia-run/releases/tag/v0.1.0
