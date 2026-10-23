<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/images/cover-dark.png">
  <source media="(prefers-color-scheme: light)" srcset="docs/assets/images/cover-light.png">
  <img alt="Insomnia Run" src="docs/assets/images/cover-light.png">
</picture>

<p align="center">
  <a href="https://github.com/scarowar/insomnia-run/actions/workflows/ci.yml"><img src="https://github.com/scarowar/insomnia-run/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/scarowar/insomnia-run/actions/workflows/codeql.yml"><img src="https://github.com/scarowar/insomnia-run/actions/workflows/codeql.yml/badge.svg" alt="CodeQL"></a>
  <a href="https://scorecard.dev/viewer/?uri=github.com/scarowar/insomnia-run"><img src="https://api.scorecard.dev/projects/github.com/scarowar/insomnia-run/badge" alt="OpenSSF Scorecard"></a>
  <a href="https://github.com/scarowar/insomnia-run/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="MIT License"></a>
  <!-- ALL-CONTRIBUTORS-BADGE:START - Do not remove or modify this section -->
<a href="#contributors"><img src="https://img.shields.io/badge/all_contributors-3-orange.svg?style=flat-square" alt="All Contributors"></a>
<!-- ALL-CONTRIBUTORS-BADGE:END -->
</p>

<p align="center">
  <a href="https://scarowar.github.io/insomnia-run/">Documentation</a> •
  <a href="https://scarowar.github.io/insomnia-run/getting-started/">Getting Started</a> •
  <a href="https://scarowar.github.io/insomnia-run/examples/">Examples</a>
</p>

---

Insomnia Run is an unofficial GitHub Action that wraps the Inso CLI to run Insomnia API collections and test suites with PR comments and CI-native reports.

https://github.com/user-attachments/assets/695ab30b-7775-4452-a107-4ca1caf49744

## Reports and Installation

- Request-grouped Markdown, normalized JSON files, and JUnit reports, with redacted failure reasons and available timings.
- Per-job/matrix PR comment replacement, bounded annotations, optional artifacts, and separate assertion/run-error outcomes.
- Verified Inso archive caching, explicit custom archive digests, frozen source installation, and optional verified runtime bundles.

Native collections retain completed request records; legacy suites use TAP. Partial runs are marked, and unknown request counts are not guessed. Redaction is best effort, not a guarantee that arbitrary collection output is secret-free.

## Quick Start

Use Linux or macOS with Python 3.10+, or select the managed Python option. Automatic Inso installation supports Linux x64 and macOS; Apple Silicon requires Rosetta. Linux ARM needs compatible preinstalled tools. Windows is unsupported.

This documentation describes v0.2.0, which is unreleased. Until the tag is available, use a full commit SHA instead of `@v0.2.0` in the examples.

Examples use `insomnia-export.yaml`. For legacy Git Sync data under `.insomnia/Workspace/`, use the parent repository root (`working-directory: .`), not `.insomnia`. See [input paths](docs/reference/inputs.md#input-paths).

**Run a collection:**
```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: collection
    working-directory: insomnia-export.yaml
```

**Run a test suite:**
```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: test
    working-directory: insomnia-export.yaml
    identifier: "My Test Suite"
```

## Common Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `command` | No | `collection` | `collection` or `test` |
| `working-directory` | Yes | | Explicit YAML export path, or repository root for legacy Git Sync |
| `identifier` | No | | Collection/test suite name or ID |
| `environment` | No | | Insomnia environment to use |
| `pr-comment` | No | `true` | Post results as PR comment |
| `comment-issue-number` | No | | Issue or PR number for non-PR workflow comments |
| `fail-on-error` | No | `true` | Set false to permit assertion failures only; execution/report errors remain fatal |
| `output-format` | No | | Request bounded convenience `json-output`; JSON files do not need this opt-in |
| `junit-report` | No | `true` | Generate a JUnit XML report file |

Verified Inso archive caching (`cache-inso`) is enabled by default. Report uploads (`upload-artifact`) are disabled by default. See the [migration guide](docs/migration.md) for upgrade details and runner requirements.

[View all inputs](https://scarowar.github.io/insomnia-run/reference/inputs/)

## Outputs

| Output | Description |
|--------|-------------|
| `markdown` | Generated test report in Markdown format |
| `json-file` | Complete normalized JSON report path |
| `report-directory` | Current report directory for uploads/downstream tools |
| `json-output` | Requested JSON within 64 KiB measured as UTF-16; otherwise empty |
| `json-output-omitted` | Whether requested convenience JSON exceeded that limit |
| `junit-file` | Generated JUnit XML path, if enabled |
| `raw-file` | Redacted raw diagnostics path, only when explicitly enabled |
| `total`, `passed`, `failed`, `skipped` | Assertion/test counts, empty if no report exists |
| `requests` | Completed native request occurrences; empty when unknown |
| `complete` | Whether the selected run completed; false for partial evidence, empty when no report exists |
| `run-error` | Whether a report contains a structured execution/timeout/protocol error |
| `comment-status`, `comment-id` | Comment publication outcome and known comment ID |
| `exit-code` | `0` success, `1` assertion failures, `2` wrapper/config/report error, `3` Inso execution/timeout/protocol error |

Use `json-file` for automation; JSON step output is optional and never truncated into invalid JSON. See the [full reference](docs/reference/inputs.md) for the schema, privacy limits, comment concurrency, and enterprise installation.

A report saying **No assertions executed** is not successful test validation. Collections need explicit script assertions; check test filters when an expected suite executes no assertions.

## CI Reports

Use `junit-file` with GitHub test report integrations or artifact upload:

Grant `checks: write` when publishing a GitHub test report.

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  id: tests
  with:
    command: collection
    working-directory: insomnia-export.yaml
    fail-on-error: "false"

- uses: dorny/test-reporter@a6ddd83ac95ff4586f5d3aceeb314d9a1841db95 # v3.0.0
  if: always() && steps.tests.outputs.junit-file != ''
  with:
    name: Insomnia API Tests
    path: ${{ steps.tests.outputs.junit-file }}
    reporter: java-junit

- if: steps.tests.outputs.exit-code != '0'
  run: exit 1
```

## Documentation

| Guide | Description |
|-------|-------------|
| [Getting Started](https://scarowar.github.io/insomnia-run/getting-started/) | Set up a test workflow |
| [Collections](https://scarowar.github.io/insomnia-run/guides/collections/) | Run API collections |
| [Test Suites](https://scarowar.github.io/insomnia-run/guides/test-suites/) | Run unit tests |
| [Secrets](https://scarowar.github.io/insomnia-run/guides/secrets/) | Handle credentials |
| [Examples](https://scarowar.github.io/insomnia-run/examples/) | Workflow snippets |
| [Migration](https://scarowar.github.io/insomnia-run/migration/) | Upgrade from previous releases |
| [Troubleshooting](https://scarowar.github.io/insomnia-run/troubleshooting/) | Common issues |

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Contributors

Thanks to the contributors ([emoji key](https://allcontributors.org/docs/en/emoji-key)):

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
