# Insomnia Run

[![MIT License](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/scarowar/insomnia-run/blob/main/LICENSE)
[![CI](https://github.com/scarowar/insomnia-run/actions/workflows/ci.yml/badge.svg)](https://github.com/scarowar/insomnia-run/actions/workflows/ci.yml)
[![CodeQL](https://github.com/scarowar/insomnia-run/actions/workflows/codeql.yml/badge.svg)](https://github.com/scarowar/insomnia-run/actions/workflows/codeql.yml)

GitHub Action for running Insomnia collections and test suites in CI/CD pipelines.

## Quick Start

```yaml
- uses: scarowar/insomnia-run@v0.1.0
  with:
    command: collection
    working-directory: .insomnia
```

## Documentation

**[📖 Full Documentation](https://scarowar.github.io/insomnia-run/)**

- [Getting Started](https://scarowar.github.io/insomnia-run/getting-started/)
- [Running Collections](https://scarowar.github.io/insomnia-run/guides/collections/)
- [Running Test Suites](https://scarowar.github.io/insomnia-run/guides/test-suites/)
- [Handling Secrets](https://scarowar.github.io/insomnia-run/guides/secrets/)
- [Reference](https://scarowar.github.io/insomnia-run/reference/inputs/)
- [Examples](https://scarowar.github.io/insomnia-run/examples/)

## License

MIT License - see [LICENSE](LICENSE).
