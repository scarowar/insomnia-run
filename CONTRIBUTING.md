# Contributing to insomnia-run

Thank you for your interest in contributing to insomnia-run! Your ideas, bug reports, and improvements are welcome. Please read this guide to help you get started.

## Local Development

This project uses `uv` and Python 3.10+. Install `uv` from https://docs.astral.sh/uv/getting-started/installation/.

```sh
git clone https://github.com/scarowar/insomnia-run.git
cd insomnia-run
uv sync --dev --frozen
uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src/insomnia_run
uv lock --check
```

Pre-commit hooks run the same checks:

```sh
uv run pre-commit run --all-files
```

Or install the hooks:

```sh
uv run pre-commit install
```

Python 3.10 is the minimum version. Python 3.12 is the version that CI uses.

## How to Contribute

- **Bug Reports & Feature Requests:**
  - Open an issue on [GitHub Issues](https://github.com/scarowar/insomnia-run/issues).
  - Provide as much detail as possible, including steps to reproduce bugs or a clear description of your feature request.

- **Pull Requests:**
  1. Fork the repository and create your branch from `develop`.
  2. Make clear, focused changes. Each pull request should address a single concern.
  3. If your change affects the action's behavior, update the documentation (e.g., `README.md`).
  4. Run all pre-commit checks before submitting:
      ```sh
      uv run pre-commit run --all-files
      ```
  5. Open a pull request and describe your changes clearly.

## Code Style & Linting

- Python code is formatted with `ruff format` and checked with `ruff check` and `mypy`.
- Pre-commit hooks are configured. Run `uv run pre-commit install` after cloning to enable automatic checks.
- Run all checks manually:

  ```sh
  uv run pre-commit run --all-files
  ```

- YAML, JSON, and GitHub Actions workflows are also linted via pre-commit.

See `pyproject.toml` for tool configuration.

For self-hosted or GHE runners, see the egress and proxy notes in `README.md` and
`docs/troubleshooting.md`.

## Security

- Please do not report security vulnerabilities in public issues. See [SECURITY.md](./SECURITY.md) for how to report vulnerabilities.

## Code of Conduct

- By participating, you agree to follow our [Code of Conduct](./CODE_OF_CONDUCT.md).

## Questions & Discussions

- For general questions, ideas, or discussions, please use [GitHub Discussions](https://github.com/scarowar/insomnia-run/discussions).

---

Thank you for helping make insomnia-run better!
