# Insomnia Run

[![MIT License](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/scarowar/insomnia-run/blob/main/LICENSE)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=scarowar_insomnia-run&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=scarowar_insomnia-run)
[![CodeQL](https://github.com/scarowar/insomnia-run/actions/workflows/codeql.yml/badge.svg)](https://github.com/scarowar/insomnia-run/actions/workflows/codeql.yml)
[![Dependabot](https://img.shields.io/badge/dependabot-enabled-brightgreen?logo=dependabot)](https://github.com/scarowar/insomnia-run/network/updates)
[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/scarowar/insomnia-run/main.svg)](https://results.pre-commit.ci/latest/github/scarowar/insomnia-run/main)

<p align="center">
  <a href="https://scarowar.github.io/insomnia-run/">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/assets/images/cover-dark.png">
      <source media="(prefers-color-scheme: light)" srcset="docs/assets/images/cover-light.png">
      <img alt="Insomnia Run - GitHub Action for running Insomnia API tests with automated PR reporting" src="docs/assets/images/cover-light.png" width="600">
    </picture>
  </a>
</p>

<p align="center">
  <b><a href="https://scarowar.github.io/insomnia-run/">📖 Documentation (GitHub Pages)</a></b>
</p>

## 📝 Overview

GitHub Action for running Insomnia API tests and collections using the Inso CLI with automated PR comment reporting.

## 🚀 Quick Start

```yaml
- name: Run Insomnia Tests
  uses: scarowar/insomnia-run@v0.1.0
  with:
    command: 'test'                      # test or collection
    identifier: 'test-suite'             # name of your test suite
    working-directory: 'insomnia-export.yaml'  # or path to .insomnia/ directory
```

👉 **[View complete configuration options →](https://scarowar.github.io/insomnia-run/quickstart/)**

## ⭐ Key Features

- **Automated API testing**: Execute Insomnia test suites and collections in CI/CD pipelines
- **PR-driven feedback**: Post detailed test results as pull request comments
- **Environment targeting**: Run tests against different environments with variable injection
- **Secure integration**: Native GitHub Actions secrets support

## 📃 License

MIT License - see [LICENSE](https://github.com/scarowar/insomnia-run/blob/main/LICENSE) for details.

---

## 🔗 Quick Links

- [Documentation site](https://scarowar.github.io/insomnia-run/)
- [GitHub Discussions](https://github.com/scarowar/insomnia-run/discussions)
- [Report a bug](https://github.com/scarowar/insomnia-run/issues)
- [Security policy](https://github.com/scarowar/insomnia-run/blob/main/SECURITY.md)
- [Contributing guide](https://github.com/scarowar/insomnia-run/blob/main/CONTRIBUTING.md)
- [License](https://github.com/scarowar/insomnia-run/blob/main/LICENSE)
