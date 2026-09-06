# Action Reference

Every input and output below matches `action.yml` exactly. Defaults shown are the
action's built-in defaults.

## Required

| Input | Description |
|-------|-------------|
| `command` | `collection` or `test` |
| `working-directory` | Path to `.insomnia` directory or export file |

## Common

| Input | Default | Description |
|-------|---------|-------------|
| `identifier` | — | Collection name, test suite name, or workspace ID |
| `environment` | — | Insomnia environment name |
| `bail` | `false` | Stop execution on first failure |
| `verbose` | `false` | Enable verbose logging |
| `execution-timeout` | `300` | Timeout for the entire execution in seconds |
| `inso-version` | `13.2.0` | Exact Inso CLI version (semver, e.g. `13.2.0`) |
| `output-format` | — | `json` is currently the only supported machine-readable format; validated before any tests run |
| `fail-on-error` | `true` | Fail the workflow if tests fail |
| `github-token` | falls back to the workflow `GITHUB_TOKEN` | Token for PR comments and for release-asset downloads on private/enterprise hosts |

## Reporting

| Input | Default | Description |
|-------|---------|-------------|
| `include-raw-output` | `true` | Embed the (redacted) raw Inso output in the markdown report |
| `raw-output-max-bytes` | `8192` | Maximum raw output size embedded in the markdown report |
| `junit-output` | — (disabled) | Path to write a JUnit XML report (enabled when set) |
| `upload-report` | `false` | Upload the JUnit report, markdown report, and full raw output as a workflow artifact |
| `report-artifact-name` | `insomnia-run-report` | Artifact name used when `upload-report` is `true` |
| `pr-comment` | `true` | Post test results as a PR comment (only on `pull_request` events) |
| `comment-tag` | `insomnia-run-report` | Tag used to find and update the existing PR comment instead of posting duplicates |

## Collection Only

| Input | Description |
|-------|-------------|
| `request-name-pattern` | Regex to filter requests |
| `item` | Request/folder IDs, comma-separated |
| `globals` | Global environment file |
| `delay-request` | Delay between requests (ms) |
| `iteration-count` | Number of iterations |
| `iteration-data` | Path to iteration data file |
| `env-var` | Environment variables, `KEY=VALUE` per line; passed to Inso as `--env-var` overrides so `{{ _.KEY }}` templates resolve. Values of 4+ characters are redacted from reports. See [Handling Secrets](../guides/secrets.md) |
| `data-folders` | Folders Insomnia can access for file references |

## Test Only

| Input | Default | Description |
|-------|---------|-------------|
| `test-name-pattern` | — | Regex to filter tests |
| `keep-file` | `false` | Keep generated test file |

## Network

| Input | Default | Description |
|-------|---------|-------------|
| `request-timeout` | — | Timeout per request (ms) |
| `disable-cert-validation` | `false` | Skip SSL verification |
| `https-proxy` | — | HTTPS proxy URL |
| `http-proxy` | — | HTTP proxy URL |
| `no-proxy` | — | Hosts to bypass proxy |

# Action Outputs

| Output | Description |
|--------|-------------|
| `markdown` | Generated Markdown report |
| `json-output` | Generated JSON report (only set when `output-format: json`) |
| `exit-code` | `0` = success, `1` = test failures (timeouts exit `1`), `2` = configuration/usage error (invalid input or unwritable report path) |
| `junit-path` | Path of the written JUnit XML report (only set when a report was written) |

## Using Outputs

Access the exit code and markdown report from subsequent steps:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  id: tests
  with:
    command: collection
    working-directory: .insomnia

- run: echo "Exit code: ${{ steps.tests.outputs.exit-code }}"
```

Access json report from subsequent steps:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  id: tests
  with:
    command: collection
    working-directory: .insomnia
    output-format: json

- name: Save JSON report
  env:
    JSON_OUTPUT: ${{ steps.tests.outputs.json-output }}
  run: |
    printf '%s' "$JSON_OUTPUT" > test-results.json
```

Access the JUnit report from subsequent steps — enable it either with `junit-output`
(a path you choose) or with `upload-report` (a default path inside the artifact staging
directory):

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  id: tests
  with:
    command: test
    working-directory: .insomnia
    identifier: "My Test Suite"
    junit-output: reports/junit.xml

- run: echo "JUnit report at ${{ steps.tests.outputs.junit-path }}"
```

## Conditional Steps

Run steps based on test results:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  id: tests
  with:
    command: collection
    working-directory: .insomnia
    fail-on-error: "false"

- name: Deploy
  if: steps.tests.outputs.exit-code == '0'
  run: echo "Deploying..."
```
