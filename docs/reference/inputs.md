# Action Inputs

## Required

| Input | Description |
|-------|-------------|
| `command` | `collection` or `test` |
| `working-directory` | Path to `.insomnia` directory or export file |

## Common

| Input | Default | Description |
|-------|---------|-------------|
| `identifier` | — | Collection or test suite name |
| `environment` | — | Insomnia environment name |
| `github-token` | — | Token for PR comments |
| `pr-comment` | `true` | Post results to PR |
| `fail-on-error` | `true` | Fail workflow on test failure |
| `bail` | `false` | Stop on first failure |
| `verbose` | `false` | Enable debug logging |
| `inso-version` | `12.2.0` | Inso CLI version |
| `execution-timeout` | `300` | Max execution time in seconds |

## Collection Only

| Input | Description |
|-------|-------------|
| `request-name-pattern` | Regex to filter requests |
| `item` | Request/folder IDs, comma-separated |
| `globals` | Global environment file |
| `delay-request` | Delay between requests (ms) |
| `iteration-count` | Number of iterations |
| `iteration-data` | Path to iteration data file |
| `env-var` | Environment variables, `key=value` per line |
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
| `exit-code` | `0` = success, `1` = failure |

## Using Outputs

Access the exit code and markdown report from subsequent steps:

```yaml
- uses: scarowar/insomnia-run@v0.1.0
  id: tests
  with:
    command: collection
    working-directory: .insomnia

- run: echo "Exit code: ${{ steps.tests.outputs.exit-code }}"
```

## Conditional Steps

Run steps based on test results:

```yaml
- uses: scarowar/insomnia-run@v0.1.0
  id: tests
  with:
    command: collection
    working-directory: .insomnia
    fail-on-error: "false"

- name: Deploy
  if: steps.tests.outputs.exit-code == '0'
  run: echo "Deploying..."
```
