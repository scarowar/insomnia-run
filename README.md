# Insomnia Run

GitHub Action for running Insomnia API tests and collections using the Inso CLI with PR comment reporting.

## What it does

- Executes Insomnia test suites and collections
- Posts detailed results as PR comments\*\*
- Integrates with GitHub Actions secrets
- Generates formatted reports

## Quick Start

```yaml
- uses: actions/checkout@v4
- uses: scarowar/insomnia-run@v0.1.0
  with:
    command: "test"
    identifier: "My Test Suite"
    github-token: ${{ secrets.GITHUB_TOKEN }}
```

## Inputs

| Input               | Description                                          | Required                                     | Default  |
| ------------------- | ---------------------------------------------------- | -------------------------------------------- | -------- |
| `command`           | `test` or `collection`                               | Yes                                          |          |
| `identifier`        | Test suite or collection name/ID                     | Yes for `test`, conditional for `collection` |          |
| `github-token`      | GitHub token for PR comments                         | No                                           |          |
| `working-directory` | Path to Insomnia data                                | No                                           | `.`      |
| `environment`       | Insomnia environment name                            | No                                           |          |
| `inso-version`      | Inso CLI version                                     | No                                           | `11.3.0` |
| `env-var`           | Environment variables (key=value, newline separated) | No                                           |          |
| `pr-comment`        | Post PR comments                                     | No                                           | `true`   |
| `fail-on-error`     | Fail action on test failures                         | No                                           | `true`   |
| `debug`             | Enable debug logging                                 | No                                           | `false`  |

### Test Command Options

| Input               | Description                | Default |
| ------------------- | -------------------------- | ------- |
| `test-name-pattern` | Regex to filter test names |         |
| `bail`              | Stop on first failure      | `false` |

### Collection Command Options

| Input                  | Description                               | Default |
| ---------------------- | ----------------------------------------- | ------- |
| `request-name-pattern` | Regex to filter request names             |         |
| `item`                 | Request/folder UIDs (comma-separated)     |         |
| `delay-request`        | Delay between requests (ms)               |         |
| `iteration-count`      | Number of iterations                      |         |
| `iteration-data`       | Path to iteration data file (JSON or CSV) |         |

### Network Options

| Input                     | Description                        | Default |
| ------------------------- | ---------------------------------- | ------- |
| `disable-cert-validation` | Disable SSL certificate validation | `false` |
| `https-proxy`             | HTTPS proxy URL                    |         |
| `http-proxy`              | HTTP proxy URL                     |         |
| `no-proxy`                | Hostnames to exclude from proxy    |         |

## Outputs

| Output         | Description         |
| -------------- | ------------------- |
| `results`      | Raw inso CLI output |
| `summary`      | Test summary        |
| `comment_body` | PR comment markdown |

## Examples

### Basic Test

```yaml
name: API Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: scarowar/insomnia-run@v0.1.0
        with:
          command: "test"
          identifier: "Auth Tests"
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

### Pull Request with Comments

```yaml
name: API Tests
on:
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: scarowar/insomnia-run@v0.1.0
        with:
          command: "test"
          identifier: "API Tests"
          github-token: ${{ secrets.GITHUB_TOKEN }}
          # PR comments are automatically enabled for pull_request events
```

### Collection with Environment

```yaml
- uses: scarowar/insomnia-run@v0.1.0
  with:
    command: "collection"
    identifier: "API Collection"
    environment: "staging"
    github-token: ${{ secrets.GITHUB_TOKEN }}
```

### With Secrets

```yaml
- uses: scarowar/insomnia-run@v0.1.0
  with:
    command: "collection"
    identifier: "Secure Tests"
    env-var: |
      api_key=${{ secrets.API_KEY }}
      password=${{ secrets.PASSWORD }}
    github-token: ${{ secrets.GITHUB_TOKEN }}
```

### Matrix Testing

```yaml
strategy:
  matrix:
    env: [dev, staging, prod]
steps:
  - uses: actions/checkout@v4
  - uses: scarowar/insomnia-run@v0.1.0
    with:
      command: "test"
      identifier: "API Tests"
      environment: ${{ matrix.env }}
      github-token: ${{ secrets.GITHUB_TOKEN }}
```

### Advanced Collection Testing

```yaml
- uses: scarowar/insomnia-run@v0.1.0
  with:
    command: "collection"
    identifier: "Load Tests"
    iteration-count: 10
    delay-request: 1000
    disable-cert-validation: true
    bail: true
    github-token: ${{ secrets.GITHUB_TOKEN }}
```

## Data Sources

### Git Sync (.insomnia directory)

```yaml
working-directory: "./" # Contains .insomnia/ folder
```

### Export Files

```yaml
working-directory: "./export.yaml"    # Workspace or collection export
working-directory: "./export.json"    # JSON format
working-directory: "./data.db.json"   # NeDB format
```

## Identifier Requirements

- **Test command**: Always required (test suite name/ID)
- **Collection command**:
  - Required for workspace exports and .insomnia directories
  - Optional for single collection exports (automatically ignored)

## PR Comments

Automatic when:

- Event is `pull_request`
- `pr-comment` is `true` (default)
- `github-token` is provided

Required permissions: `pull-requests: write`

## Environment Variables

Variables in `env-var` are passed to inso CLI and available in Insomnia templates:

```yaml
env-var: |
  api_key=${{ secrets.API_KEY }}
  base_url=https://api.example.com
```

Use in Insomnia: `{{api_key}}`, `{{base_url}}`

## Limitations

- Only supports `test` and `collection` commands
- Uses fixed `spec` reporter for consistent PR comments
- Requires inso CLI version 11.3.0+

## Troubleshooting

**"Command not supported"**: Only `test` and `collection` are allowed

**"Identifier ignored"**: Expected for single collection exports

**Missing PR comments**: Check token permissions and event type

**Debug mode**: Set `debug: true` for detailed logs
