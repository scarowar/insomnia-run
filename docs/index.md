# Insomnia Run

![Insomnia Run Cover](assets/images/cover-dark.png#only-dark)
![Insomnia Run Cover](assets/images/cover-light.png#only-light)

Run Insomnia collections and test suites in GitHub Actions with PR comments and CI-native reports.

## Usage

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: collection
    working-directory: insomnia-export.yaml
```

## Features

| Feature | Description |
|---------|-------------|
| Collections | Run API request collections |
| Test Suites | Execute JavaScript unit tests |
| PR Comments | Auto-post results to pull requests |
| JSON Output | Machine-readable reports for automation |
| JUnit Reports | CI test report files for downstream tools |
| [Secrets](guides/secrets.md) | Set collection environment overrides |
| Multi-Environment | Target dev, staging, production |
| Configurable Timeouts | Handle slow APIs and large collections |

## Inputs

| Input | Required | Description |
|-------|----------|-------------|
| `command` | Yes | `collection` or `test` |
| `working-directory` | Yes | Explicit YAML export path, or repository root for legacy Git Sync |
| `identifier` | No | Collection or test suite name |
| `environment` | No | Insomnia environment to use |
| `output-format` | No | Use `json` for machine-readable output |
| `junit-report` | No | Generate a JUnit XML report file |

[View all inputs →](reference/inputs.md)

## Outputs

| Output | Description |
|--------|-------------|
| `markdown` | Generated test report |
| `json-output` | JSON report (when `output-format: json`) |
| `junit-file` | Path to the generated JUnit XML report |
| `exit-code` | `0` = command success; nonzero = test, execution, or CLI error |

**No assertions executed** is not successful test validation. See [collection assertions](guides/collections.md#assertions) and [input paths](reference/inputs.md#input-paths).

## Documentation

| Page | Description |
|------|-------------|
| [Getting Started](getting-started/index.md) | Set up a test workflow |
| [Collections](guides/collections.md) | Run API collections |
| [Test Suites](guides/test-suites.md) | Run unit tests |
| [Secrets](guides/secrets.md) | Handle credentials |
| [Reference](reference/inputs.md) | All inputs & outputs |
| [Examples](examples/index.md) | Workflow snippets |
| [Migration](migration.md) | Upgrade between releases |
| [Troubleshooting](troubleshooting.md) | Common issues |
