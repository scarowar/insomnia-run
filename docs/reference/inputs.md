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
| `comment-issue-number` | — | Issue or PR number for comments outside `pull_request` workflows |
| `pr-comment` | `true` | Post results to a PR or explicit issue |
| `fail-on-error` | `true` | Fail workflow on test failure |
| `bail` | `false` | Stop on first failure |
| `verbose` | `false` | Enable debug logging |
| `inso-version` | `12.6.0` | Inso CLI version |
| `execution-timeout` | `300` | Max execution time in seconds |
| `output-format` | — | JSON output in addition to Markdown |
| `include-raw-output` | `false` | Include raw Inso output in the Markdown report |
| `junit-report` | `true` | Generate a JUnit XML report file |
| `junit-output-file` | — | Custom path for the JUnit XML report |

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
| `json-output` | Generated JSON report |
| `junit-file` | Path to the generated JUnit XML report |
| `exit-code` | `0` = success, `1` = failure |

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

Use the generated JUnit report with test reporting or artifact upload:

Grant `checks: write` when publishing a GitHub test report.

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  id: tests
  with:
    command: collection
    working-directory: .insomnia
    fail-on-error: "false"

- name: Publish JUnit report
  if: always() && steps.tests.outputs.junit-file != ''
  uses: dorny/test-reporter@a43b3a5f7366b97d083190328d2c652e1a8b6aa2 # v3.0.0
  with:
    name: Insomnia API Tests
    path: ${{ steps.tests.outputs.junit-file }}
    reporter: java-junit

- name: Upload JUnit report
  if: always() && steps.tests.outputs.junit-file != ''
  uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1
  with:
    name: insomnia-run-junit
    path: ${{ steps.tests.outputs.junit-file }}

- name: Fail workflow on test failures
  if: steps.tests.outputs.exit-code != '0'
  run: exit 1
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

## Comments Outside Pull Requests

Pull request workflows are detected automatically. For manual, scheduled, deployment, or push workflows, set `comment-issue-number` to the PR or issue that should receive the report:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: collection
    working-directory: .insomnia
    comment-issue-number: "123"
```

The workflow token needs `issues: write` for issues and `pull-requests: write` for pull requests.

## Enterprise Runners

Insomnia Run uses `inso` from `PATH` when it is already available. If `inso` is missing, the action installs the requested `inso-version`.

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: collection
    working-directory: .insomnia
```

On runners without public internet access, add `inso` to `PATH` in the runner image before the workflow starts and configure pip to use an internal package mirror.

## Inso Configuration

Inso loads its supported configuration files from the workspace. Keep configuration such as `.insorc` with the Insomnia project when you need Inso defaults, scripts, or shared options.

Insomnia Run does not add a separate configuration input. Values passed through action inputs are sent as command options for the current run.
