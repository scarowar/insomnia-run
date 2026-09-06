# Insomnia Run

![Insomnia Run Cover](assets/images/cover-dark.png#only-dark)
![Insomnia Run Cover](assets/images/cover-light.png#only-light)

Run Insomnia collections and test suites in GitHub Actions with PR comment reporting.

## Usage

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: collection
    working-directory: .insomnia
```

## Features

| Feature | Description |
|---------|-------------|
| **Collections** | Run API request collections |
| **Test Suites** | Execute JavaScript unit tests |
| **PR Comments** | One idempotent comment per pull request, updated on every run |
| **JUnit & Artifacts** | JUnit XML reports, uploadable as workflow artifacts |
| **Annotations** | One `::error::` annotation per failing test (first 10) |
| **JSON Output** | Machine-readable reports for automation |
| **Secrets** | Secure credential passthrough with automatic redaction in reports |
| **Multi-Environment** | Target dev, staging, production |
| **Configurable Timeouts** | Handle slow APIs and large collections |

## PR Comment Examples

=== "Passing Tests"

    ![Collection passing](assets/images/collection-pass.png)

=== "Failing Tests"

    ![Test failing](assets/images/test-fail.png)

## Inputs

| Input | Required | Description |
|-------|----------|-------------|
| `command` | Yes | `collection` or `test` |
| `working-directory` | Yes | Path to `.insomnia` or export file |
| `identifier` | No | Collection or test suite name |
| `environment` | No | Insomnia environment to use |
| `output-format` | No | Use `json` for machine-readable output |

[View all inputs →](reference/inputs.md)

## Outputs

| Output | Description |
|--------|-------------|
| `markdown` | Generated test report |
| `json-output` | JSON report (when `output-format: json`) |
| `exit-code` | `0` = pass, `1` = test failures, `2` = configuration/usage error |
| `junit-path` | Path of the written JUnit XML report |

## Documentation

| Page | Description |
|------|-------------|
| [Getting Started](getting-started/index.md) | First run in 5 minutes |
| [Collections](guides/collections.md) | Run API collections |
| [Test Suites](guides/test-suites.md) | Run unit tests |
| [Secrets](guides/secrets.md) | Handle credentials and redaction |
| [Reference](reference/inputs.md) | All inputs & outputs |
| [Examples](examples/index.md) | Workflow snippets incl. JUnit + artifacts |
| [Migration](migration.md) | Upgrading from v0.1.x to v0.2.0 |
| [Troubleshooting](troubleshooting.md) | Common issues |
