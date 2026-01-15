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
- **Automatic PR Comments**: Post test results directly to pull requests
- **Markdown & JSON Reports**: Human-readable and machine-readable outputs
- **Flexible Exit Codes**: Control workflow failure behavior
- **Environment Support**: Target different Insomnia environments per run
- **Secure Secrets**: Pass credentials safely via GitHub Secrets
- **Configurable Timeouts**: Handle slow APIs and large collections

## Quick Start

**Run a collection:**
```yaml
- uses: scarowar/insomnia-run@v0.1.0
  with:
    command: collection
    working-directory: .insomnia
```

**Run a test suite:**
```yaml
- uses: scarowar/insomnia-run@v0.1.0
  with:
    command: test
    working-directory: .insomnia
    identifier: "My Test Suite"
```

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `command` | Yes | | `collection` or `test` |
| `working-directory` | Yes | | Path to `.insomnia` or export file |
| `identifier` | No | | Collection/test suite name or ID |
| `environment` | No | | Insomnia environment to use |
| `pr-comment` | No | `true` | Post results as PR comment |
| `fail-on-error` | No | `true` | Fail workflow on test failures |
| `output-format` | No | | Use `json` to get JSON output in addition to Markdown |

[View all inputs](https://scarowar.github.io/insomnia-run/reference/inputs/)

## Outputs

| Output | Description |
|--------|-------------|
| `markdown` | Generated test report in Markdown format |
| `json-output` | Generated JSON report (machine-readable) |
| `exit-code` | `0` for pass, `1` for fail |

## Documentation

| Guide | Description |
|-------|-------------|
| [Getting Started](https://scarowar.github.io/insomnia-run/getting-started/) | First run in 5 minutes |
| [Collections](https://scarowar.github.io/insomnia-run/guides/collections/) | Run API collections |
| [Test Suites](https://scarowar.github.io/insomnia-run/guides/test-suites/) | Run unit tests |
| [Secrets](https://scarowar.github.io/insomnia-run/guides/secrets/) | Handle credentials |
| [Examples](https://scarowar.github.io/insomnia-run/examples/) | Workflow snippets |
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
