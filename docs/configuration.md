# Configuration

Customize Insomnia Run for your workflows and environments.

## Action Inputs

Add these under the `with:` section in your workflow YAML:

| Input                   | Description                                          | Required | Default   |
|-------------------------|------------------------------------------------------|----------|-----------|
| `command`               | `test` or `collection`                              | Yes      |           |
| `identifier`            | Test suite or collection name/ID                    | Yes*     |           |
| `github-token`          | GitHub token for PR comments                        | No       |           |
| `working-directory`     | Path to Insomnia data                               | No       | `.`       |
| `environment`           | Insomnia environment name                           | No       |           |
| `inso-version`          | Inso CLI version                                    | No       | `11.3.0`  |
| `env-var`               | Env vars (key=value, newline separated)             | No       |           |
| `pr-comment`            | Post PR comments                                    | No       | `true`    |
| `fail-on-error`         | Fail action on test failures                        | No       | `true`    |
| `debug`                 | Enable debug logging                                | No       | `false`   |
| `test-name-pattern`     | Regex to filter test names (test command)           | No       |           |
| `bail`                  | Stop on first failure (test command)                | No       | `false`   |
| `request-name-pattern`  | Regex to filter request names (collection command)  | No       |           |
| `item`                  | Request/folder UIDs (collection command)            | No       |           |
| `delay-request`         | Delay between requests (ms, collection command)     | No       |           |
| `iteration-count`       | Number of iterations (collection command)           | No       |           |
| `iteration-data`        | Path to iteration data file (collection command)    | No       |           |
| `disable-cert-validation`| Disable SSL cert validation                        | No       | `false`   |
| `https-proxy`           | HTTPS proxy URL                                     | No       |           |
| `http-proxy`            | HTTP proxy URL                                      | No       |           |
| `no-proxy`              | Hostnames to exclude from proxy                     | No       |           |

\* **Required for `test` command; conditional for `collection`**

---

## Action Outputs

| Output         | Description                |
|----------------|---------------------------|
| `results`      | Raw Inso CLI output       |
| `summary`      | Test summary              |
| `comment_body` | PR comment markdown       |

---

## Data Sources

- **.insomnia directory**: Use `working-directory: "./"` (must contain `.insomnia/`)
- **Export files**: Use `working-directory: "./export.yaml"` or similar

---

## Environment Variables

Set with `env-var` (newline-separated):

```yaml
env-var: |
  api_key=${{ secrets.API_KEY }}
  base_url=https://api.example.com
```

Use in Insomnia as `{{api_key}}`, `{{base_url}}`.

!!! note
    Environment variables only work with the `collection` command. The `test` command will show a warning if `env-var` is provided.

---

## PR Comments

PR comments are posted automatically when:

- The event is `pull_request`
- `pr-comment` is `true` (default)
- `github-token` is provided

Required permissions: `pull-requests: write`

---

## Best Practices

- Use secrets for sensitive data
- Enable debug mode for troubleshooting
- Use test/collection filters for large suites

---

See [Examples](examples.md) for advanced usage and [Troubleshooting](troubleshooting.md) for help.
