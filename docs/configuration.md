# Configuration

Learn how to configure Insomnia Run for your workflows, test environments, and advanced use cases.

## Action Inputs

The action accepts several inputs to customize its behavior. Add these under the `with:` section in your workflow YAML.

| Input                     | Description                                          | Default   | Required | Example                         |
|---------------------------|------------------------------------------------------|-----------|----------|---------------------------------|
| `command`                 | Command to execute: `test` or `collection`          | —         | Yes      | `test`                          |
| `identifier`              | Test suite or collection name/ID                    | —         | No       | `My Test Suite`                 |
| `github-token`            | GitHub token for PR comments                        | —         | No       | `${{ secrets.GITHUB_TOKEN }}`   |
| `working-directory`       | Path to Insomnia data directory or export file      | `.`       | No       | `./api-tests/`                  |
| `environment`             | Insomnia environment name                           | —         | No       | `staging`                       |
| `inso-version`            | Inso CLI version to use                             | `11.3.0`  | No       | `latest`                        |
| `env-var`                 | Environment variables (key=value, newline separated)| —         | No       | `API_KEY=${{ secrets.API_KEY }}` |
| `pr-comment`              | Post results as PR comments                         | `true`    | No       | `false`                         |
| `fail-on-error`           | Fail workflow on test failures                      | `true`    | No       | `false`                         |
| `debug`                   | Enable debug logging                                | `false`   | No       | `true`                          |

!!! note "Working Directory vs Step-Level Working Directory"
    The `working-directory` input is specific to this action and specifies where your Insomnia data is located (either a directory containing `.insomnia/` folder or an export file). This is different from the GitHub Actions step-level `working-directory` property, which changes the working directory for the entire step execution.

!!! tip
    Most users only need to set `command`, `identifier`, and optionally `github-token`. Other inputs are for advanced scenarios.

### Test Command Options

Additional inputs when `command: "test"`:

| Input               | Description                | Default |
|---------------------|----------------------------|---------|
| `test-name-pattern` | Regex to filter test names | —       |
| `bail`              | Stop on first failure      | `false` |

### Collection Command Options

Additional inputs when `command: "collection"`:

| Input                   | Description                               | Default |
|-------------------------|-------------------------------------------|---------|
| `request-name-pattern`  | Regex to filter request names             | —       |
| `item`                  | Request/folder UIDs (comma-separated)     | —       |
| `delay-request`         | Delay between requests (ms)               | —       |
| `iteration-count`       | Number of iterations                      | —       |
| `iteration-data`        | Path to iteration data file               | —       |

### Network Options

| Input                     | Description                        | Default |
|---------------------------|------------------------------------|---------|
| `disable-cert-validation` | Disable SSL certificate validation | `false` |
| `https-proxy`             | HTTPS proxy URL                    | —       |
| `http-proxy`              | HTTP proxy URL                     | —       |
| `no-proxy`                | Hostnames to exclude from proxy    | —       |

!!! danger "Certificate Validation Security Warning"
    Setting `disable-cert-validation: true` disables SSL/TLS certificate validation, making your API tests vulnerable to man-in-the-middle attacks. Only use this option in controlled development environments with self-signed certificates. **Never disable certificate validation in production workflows.**

!!! info "Proxy Configuration Precedence"
    Proxy settings are resolved in the following order:
    1. **Action inputs** (`https-proxy`, `http-proxy`, `no-proxy`) take highest precedence
    2. **Environment variables** (`HTTPS_PROXY`, `HTTP_PROXY`, `NO_PROXY`) are used if action inputs are not provided
    3. If neither are set, no proxy configuration is applied

    Action inputs will override any existing environment variables for the same proxy settings.

## Action Outputs

Outputs are available as step outputs in your workflow. Use them for conditional logic or chaining steps.

| Output         | Description                |
|----------------|----------------------------|
| `results`      | Raw Inso CLI output        |
| `summary`      | Test execution summary     |
| `comment_body` | PR comment markdown        |

## Data Sources

Insomnia Run supports multiple data source configurations:

**Git Sync (.insomnia directory):**
```yaml linenums="1" title="Git Sync configuration"
working-directory: "./"  # Repository root containing .insomnia/
```

**Export Files:**
```yaml linenums="1" title="Export file configurations"
working-directory: "./export.yaml"    # YAML workspace export
working-directory: "./export.json"    # JSON workspace export
working-directory: "./data.db.json"   # NeDB workspace export
```

## Environment Variables

Pass environment variables to your Insomnia tests using the `env-var` input:

```yaml linenums="1" title="Environment variables example"
env-var: |
  API_KEY=${{ secrets.API_KEY }}
  BASE_URL=https://api.staging.example.com
  TIMEOUT=30000
  MY_JSON='{"key": "value", "count": 42}'
  MESSAGE='Hello world with spaces'
  CONFIG_WITH_HASH='value#with#hash'
```

Access these in Insomnia as `{{API_KEY}}`, `{{BASE_URL}}`, etc.

!!! tip "Quoting Environment Variable Values"
    Quote values that contain special characters like spaces, `#`, `=`, or JSON structures:
    ```yaml
    env-var: |
      SIMPLE_VALUE=no_quotes_needed
      JSON_CONFIG='{"api": {"host": "localhost", "port": 3000}}'
      MESSAGE='This value has spaces and needs quotes'
      HASH_VALUE='config#with#special=characters'
    ```

!!! warning "Environment Variables and Commands"
    Environment variables (`env-var`) **only work with the `collection` command**. The `test` command will display a warning if `env-var` is provided.
    
    **For the `test` command**: Define environment variables within **Insomnia Environment files** instead of using the `env-var` input. This is the recommended approach for test suites as it provides better integration with Insomnia's testing framework.

## PR Comments and Permissions

PR comments are posted automatically when:

- Workflow is triggered by `pull_request` event
- `pr-comment` is `true` (default)
- `github-token` is provided

**Required permissions:**
```yaml linenums="1" title="Required workflow permissions"
permissions:
  pull-requests: write
  contents: read
```

## Identifier Requirements

Understanding when the `identifier` input is required:

- **Test command**: Always required (test suite name or ID)
- **Collection command**: Required for workspace exports with multiple collections; optional for single collection exports

## Best Practices

- Use descriptive test suite and collection names for better reporting
- Store sensitive data in GitHub secrets, not directly in workflows
- Enable PR comments for immediate feedback on test results
- Use environment-specific configurations for comprehensive testing
- Set `fail-on-error: false` for non-critical test suites that shouldn't block deployments
- Pin CLI versions for reproducible builds: Use specific `inso-version` (e.g., `"11.3.0"`) instead of `"latest"` to ensure consistent behavior across runs
- Use matrix strategies for parallel testing: Run tests across multiple environments simultaneously to reduce total execution time and improve coverage

---

See [Quickstart](quickstart.md) to get started, or [Examples](examples.md) for real-world usage patterns.
