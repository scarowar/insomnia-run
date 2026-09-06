<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/images/cover-dark.png">
  <source media="(prefers-color-scheme: light)" srcset="docs/assets/images/cover-light.png">
  <img alt="Insomnia Run" src="docs/assets/images/cover-light.png">
</picture>

<p align="center">
  <a href="https://github.com/scarowar/insomnia-run/actions/workflows/ci.yml"><img src="https://github.com/scarowar/insomnia-run/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/scarowar/insomnia-run/actions/workflows/codeql.yml"><img src="https://github.com/scarowar/insomnia-run/actions/workflows/codeql.yml/badge.svg" alt="CodeQL"></a>
  <a href="https://github.com/scarowar/insomnia-run/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="MIT License"></a>
  <!-- ALL-CONTRIBUTORS-BADGE:START - Do not remove or modify this section -->
<a href="#contributors-"><img src="https://img.shields.io/badge/all_contributors-3-orange.svg?style=flat-square" alt="All Contributors"></a>
<!-- ALL-CONTRIBUTORS-BADGE:END -->
</p>

<p align="center">
  <a href="https://scarowar.github.io/insomnia-run/">Documentation</a> •
  <a href="https://scarowar.github.io/insomnia-run/getting-started/">Getting Started</a> •
  <a href="https://scarowar.github.io/insomnia-run/examples/">Examples</a>
</p>

---

Run your Insomnia API collections and test suites in GitHub Actions with automatic PR comment reporting.

**Why Insomnia Run?** Insomnia is great for designing and testing APIs locally. This action brings those same collections into your CI/CD pipeline—no separate test framework needed.

https://github.com/user-attachments/assets/695ab30b-7775-4452-a107-4ca1caf49744

## Features

- **GitHub Actions Native**: Drop-in action with simple YAML configuration
- **Automatic PR Comments**: One idempotent comment per pull request, updated on every run
- **JUnit Reports & Artifacts**: Machine-readable JUnit XML plus a workflow artifact with the full report
- **Failure Annotations**: One `::error::` annotation per failing test (first 10) on the workflow run
- **Markdown & JSON Reports**: Human-readable and machine-readable outputs
- **Secure Secrets**: Redaction of `env-var` values, Authorization headers, and tokenized URLs in every report
- **Rate-Limit Friendly Runtime**: Release assets download straight from the CDN, not the REST API — private/enterprise mirrors make only the authenticated calls they need
- **Flexible Exit Codes**: Control workflow failure behavior
- **Environment Support**: Target different Insomnia environments per run
- **Linux x64**: Runs on GitHub-hosted and self-hosted Linux x86_64 runners (Inso CLI publishes Linux x64 binaries only)

## Quick Start

**Run a collection:**

```yaml
name: API Tests

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read
  pull-requests: write   # needed for pr-comment: true (the default)

jobs:
  api-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2

      - uses: scarowar/insomnia-run@v0.2.0
        with:
          command: collection
          working-directory: .insomnia
```

**Run a test suite:**

```yaml
name: Unit Tests

on:
  pull_request:

permissions:
  contents: read
  pull-requests: write   # needed for pr-comment: true (the default)

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2

      - uses: scarowar/insomnia-run@v0.2.0
        with:
          command: test
          working-directory: .insomnia
          identifier: "My Test Suite"
```

Pin the exact release tag as shown. The alias `@v0.2` also works. Only exact
tags `vX.Y.Z` install the verified wheel. Other references install from
source and show a warning.

## Permissions

The action defaults to `pr-comment: true`, so pull-request workflows need:

```yaml
permissions:
  contents: read
  pull-requests: write
```

| Feature | Permissions required |
|---------|----------------------|
| Running tests (`pr-comment: false`) | `contents: read` only |
| PR comments (`pr-comment: true`, default) | `contents: read` + `pull-requests: write` |
| Artifact upload (`upload-report: true`) | Nothing beyond the default — uploads use the runner's runtime token |

PR comments are only posted on `pull_request` events; other events skip the comment step.

## Egress requirements

The action needs outbound HTTPS from the runner to exactly these destinations:

| Destination | Purpose |
|-------------|---------|
| `github.com` (release CDN) | Download the Inso CLI tarball. The `13.2.0` tarball is verified against a SHA256 digest pinned in this action; other versions proceed with a warning because Kong publishes no checksum manifest upstream |
| This action's release assets (your `github.server_url` host) | The `insomnia_run` wheel, `constraints.txt`, and `SHA256SUMS` for exact `vX.Y.Z` pins — all checksum-verified (`sha256sum --check --strict`) before install |
| `pypi.org` + `files.pythonhosted.org` | Wheel runtime dependencies (`pydantic`, `typer`, and transitive) fetched by pip at install time. Constraints pin the versions but do not vendor them; an ambient `PIP_INDEX_URL` is respected for private mirrors |
| Your API host | Whatever host(s) the collection's requests target |

Notes:

- On GitHub Enterprise Server / Enterprise Cloud data-residency hosts, the release assets come from your enterprise host instead of `github.com`; private mirrors additionally use authenticated API calls for the assets
- Refs other than exact `vX.Y.Z` tags install from source and additionally fetch the Python build backend from PyPI
- PR comments (enabled by default on `pull_request` events) additionally use the GitHub REST API

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `command` | Yes | | `collection` or `test` |
| `working-directory` | Yes | | Path to `.insomnia` or export file |
| `identifier` | No | | Collection/test suite name or ID |
| `environment` | No | | Insomnia environment to use |
| `pr-comment` | No | `true` | Post results as a single tagged PR comment (updated per run, never duplicated) |
| `comment-tag` | No | `insomnia-run-report` | Tag identifying the PR comment to update |
| `fail-on-error` | No | `true` | Fail workflow on test failures |
| `output-format` | No | | Use `json` to get JSON output in addition to Markdown |
| `junit-output` | No | | Path to write a JUnit XML report (enabled when set) |
| `upload-report` | No | `false` | Upload the JUnit report, markdown report, and full raw output as a workflow artifact |
| `inso-version` | No | `13.2.0` | Exact Inso CLI version (semver) |

[View all inputs](https://scarowar.github.io/insomnia-run/reference/inputs/)

## Outputs

| Output | Description |
|--------|-------------|
| `markdown` | Generated test report in Markdown format |
| `json-output` | Generated JSON report (machine-readable, when `output-format: json`) |
| `exit-code` | `0` pass, `1` test failures, `2` configuration/usage error |
| `junit-path` | Path of the written JUnit XML report (when a report was written) |

## Documentation

| Guide | Description |
|-------|-------------|
| [Getting Started](https://scarowar.github.io/insomnia-run/getting-started/) | First run in 5 minutes |
| [Collections](https://scarowar.github.io/insomnia-run/guides/collections/) | Run API collections |
| [Test Suites](https://scarowar.github.io/insomnia-run/guides/test-suites/) | Run unit tests |
| [Secrets](https://scarowar.github.io/insomnia-run/guides/secrets/) | Handle credentials and redaction |
| [Examples](https://scarowar.github.io/insomnia-run/examples/) | Workflow snippets incl. JUnit + artifacts |
| [Migration](https://scarowar.github.io/insomnia-run/migration/) | Upgrading from v0.1.x to v0.2.0 |
| [Troubleshooting](https://scarowar.github.io/insomnia-run/troubleshooting/) | Common issues |

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Contributors ✨

Thanks goes to these wonderful people ([emoji key](https://allcontributors.org/docs/en/emoji-key)):

<!-- ALL-CONTRIBUTORS-LIST:START - Do not remove or modify this section -->
<!-- prettier-ignore-start -->
<!-- markdownlint-disable -->
<table>
  <tbody>
    <tr>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/sagar-shaw-bits"><img src="https://avatars.githubusercontent.com/u/84916495?v=4?s=100" width="100px;" alt="Sagar Shaw BITS"/><br /><sub><b>Sagar Shaw BITS</b></sub></a><br /><a href="https://github.com/scarowar/insomnia-run/commits?author=sagar-shaw-bits" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/cnaples79"><img src="https://avatars.githubusercontent.com/u/28323262?v=4?s=100" width="100px;" alt="Chase Naples"/><br /><sub><b>Chase Naples</b></sub></a><br /><a href="https://github.com/scarowar/insomnia-run/commits?author=cnaples79" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/rivhar"><img src="https://avatars.githubusercontent.com/u/107469626?v=4?s=100" width="100px;" alt="Radha Patel"/><br /><sub><b>Radha Patel</b></sub></a><br /><a href="https://github.com/scarowar/insomnia-run/commits?author=rivhar" title="Code">💻</a> <a href="https://github.com/scarowar/insomnia-run/commits?author=rivhar" title="Documentation">📖</a></td>
    </tr>
  </tbody>
</table>

<!-- markdownlint-restore -->
<!-- prettier-ignore-end -->

<!-- ALL-CONTRIBUTORS-LIST:END -->

This project follows the [all-contributors](https://github.com/all-contributors/all-contributors) specification. Contributions of any kind welcome!
