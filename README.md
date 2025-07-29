# Insomnia Run

**🚀 Run Insomnia Collections & Tests in GitHub Actions with PR Comments & GitHub Secrets Integration**

This action executes Insomnia collections and test suites using the Inso CLI, generates comprehensive reports, and posts results as PR comments with full GitHub Actions secrets integration.

This action provides the following functionality for GitHub Actions users:

- **🧪 Execute Insomnia test suites and collections** with full CLI support
- **🔐 Secure GitHub Actions secrets integration** with automatic masking  
- **📊 Comprehensive test reporting** with detailed markdown output
- **💬 Smart PR comments** with pass/fail status and detailed results
- **⚙️ Full Inso CLI feature support** including environments, filtering, and proxies

---

## Usage

See [action.yml](action.yml)

**Basic:**
```yaml
steps:
- uses: actions/checkout@v4
- uses: scarowar/insomnia-run@v1
  with:
    command: 'test'
    identifier: 'My Test Suite'
    github-token: ${{ secrets.GITHUB_TOKEN }}
```

**With GitHub Secrets:**
```yaml
- uses: scarowar/insomnia-run@v1
  with:
    command: 'collection'
    identifier: 'API Tests'
    environment: 'Production'
    env-var: |
      api_key=${{ secrets.API_KEY }}
      password=${{ secrets.PASSWORD }}
    github-token: ${{ secrets.GITHUB_TOKEN }}
```

### Inputs

| Input | Description | Required | Default |
|-------|-------------|----------|---------|
| `github-token` | GitHub token for API access. Pass `secrets.GITHUB_TOKEN` | ❌ | |
| `inso-version` | Version of inso CLI to use | ❌ | `11.3.0` |
| `working-directory` | Working directory or export file where Insomnia data is located | ❌ | `.` |
| `environment` | Name of the Insomnia environment to use | ❌ | |
| `command` | Command to run: **`test` or `collection`** | ✅ | |
| `identifier` | Name or ID of test suite (for `test`) or collection (for `collection`) | ❌ | |
| `test-name-pattern` | Regex pattern to filter test names (for `test`) | ❌ | |
| `request-name-pattern` | Regex pattern to filter request names (for `collection`) | ❌ | |
| `item` | Request or folder UID(s) to run (for `collection`). Comma-separated | ❌ | |
| `delay-request` | Delay in milliseconds between requests (for `collection`) | ❌ | |
| `iteration-count` | Number of times to run the collection (for `collection`) | ❌ | |
| `iteration-data` | Path or URL to iteration data file - JSON or CSV (for `collection`) | ❌ | |
| `disable-cert-validation` | Disable certificate validation for SSL requests | ❌ | `false` |
| `https-proxy` | URL for the proxy server for HTTPS requests | ❌ | |
| `http-proxy` | URL for the proxy server for HTTP requests | ❌ | |
| `no-proxy` | Comma separated list of hostnames that do not require a proxy | ❌ | |
| `bail` | Exit on first test failure | ❌ | `false` |
| `debug` | Enable debug logging for troubleshooting | ❌ | `false` |
| **`env-var`** | **🔐 Environment variables from GitHub secrets (key=value format, newline separated)** | ❌ | |
| `pr-comment` | Whether to post results as a PR comment | ❌ | `true` |
| `fail-on-error` | Fail the GitHub Action if inso CLI reports failures | ❌ | `true` |

### Outputs

| Output | Description |
|--------|-------------|
| `results` | Raw output from the inso CLI command |
| `summary` | Summarized result of the inso run |
| `comment_body` | Formatted Markdown body of the PR comment |

---

## Examples

### Basic Test Execution

```yaml
name: API Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: scarowar/insomnia-run@v1
        with:
          command: 'test'
          identifier: 'Authentication Tests'
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

### Collection with Environment

```yaml
- uses: scarowar/insomnia-run@v1
  with:
    command: 'collection'
    identifier: 'API Collection'
    environment: 'staging'
    working-directory: './insomnia-export.yaml'
    github-token: ${{ secrets.GITHUB_TOKEN }}
```

### GitHub Actions Secrets Integration

Perfect for injecting secrets into Insomnia environment variables:

```yaml
- uses: scarowar/insomnia-run@v1
  with:
    command: 'collection'
    identifier: 'Secure API Tests'
    env-var: |
      api_key=${{ secrets.API_KEY }}
      username=${{ secrets.USERNAME }}
      password=${{ secrets.PASSWORD }}
      base_url=${{ secrets.BASE_URL }}
    github-token: ${{ secrets.GITHUB_TOKEN }}
```

**How it works:**
- All secret values are automatically masked in GitHub Actions logs
- Variables are injected at runtime using Inso CLI's `--env-var` option
- Use these variables in Insomnia with `{{api_key}}`, `{{username}}`, etc.

### Advanced Collection Testing

```yaml
- uses: scarowar/insomnia-run@v1
  with:
    command: 'collection'
    identifier: 'Load Tests'
    iteration-count: 10
    delay-request: 1000
    disable-cert-validation: true
    https-proxy: 'http://proxy.company.com:8080'
    github-token: ${{ secrets.GITHUB_TOKEN }}
```

### Test Suite with Filtering

```yaml
- uses: scarowar/insomnia-run@v1
  with:
    command: 'test'
    identifier: 'All Tests'
    test-name-pattern: '^(Auth|Login).*'
    bail: true
    debug: true
    github-token: ${{ secrets.GITHUB_TOKEN }}
```

### Matrix Testing

```yaml
strategy:
  matrix:
    environment: [development, staging, production]
    
steps:
  - uses: scarowar/insomnia-run@v1
    with:
      command: 'collection'
      identifier: 'API Tests'
      environment: ${{ matrix.environment }}
      env-var: |
        api_key=${{ secrets[format('{0}_API_KEY', matrix.environment)] }}
      github-token: ${{ secrets.GITHUB_TOKEN }}
```

---

## Working Directory Support

This action supports multiple Insomnia data formats:

### .insomnia Directory (Git Sync)
```yaml
working-directory: './'  # Contains .insomnia/ folder
```

### Workspace/Collection Exports (YAML)
```yaml
working-directory: './insomnia-export.yaml'    # YAML export (recommended)
working-directory: './my-collection.yml'       # Also supports .yml extension
```

### Workspace/Collection Exports (JSON)  
```yaml
working-directory: './insomnia-export.json'    # JSON export format
working-directory: './api-collection.json'     # Single collection export
```

### NeDB Database Files
```yaml
working-directory: './insomnia.db.json'        # NeDB database format
```

> **Note:** For collection exports (single collection files), the `identifier` parameter is automatically ignored as the CLI processes the export file directly.

---

## Supported Commands

This action **only supports the following commands:**

### `test`
Execute Insomnia test suites with Jest-style assertions.

```yaml
command: 'test'
identifier: 'Test Suite Name'  # Required: test suite name or ID
```

**Additional Options:**
- `test-name-pattern`: Filter tests by regex pattern
- `bail`: Stop on first failure

### `collection`  
Execute Insomnia request collections.

```yaml
command: 'collection'
identifier: 'Collection Name'  # Optional: collection name or ID
```

**Additional Options:**
- `request-name-pattern`: Filter requests by regex pattern
- `item`: Specific request/folder UIDs (comma-separated)
- `delay-request`: Delay between requests (ms)
- `iteration-count`: Number of collection iterations
- `iteration-data`: CSV/JSON data file for iterations

> **Note:** Other Inso CLI commands like `export spec`, `lint spec`, etc. are **not supported** and will cause the action to fail.

---

## GitHub Actions Secrets Integration

### Automatic Secret Masking

GitHub Actions automatically masks all secret values in logs:

```yaml
env-var: |
  password=${{ secrets.PASSWORD }}
  api_key=${{ secrets.API_KEY }}
```

**In logs you'll see:**
```
inso run collection --env-var "password=***" --env-var "api_key=***"
```

### Environment-Specific Secrets

```yaml
# Development
env-var: |
  api_key=${{ secrets.DEV_API_KEY }}
  base_url=${{ secrets.DEV_BASE_URL }}

# Production  
env-var: |
  api_key=${{ secrets.PROD_API_KEY }}
  base_url=${{ secrets.PROD_BASE_URL }}
```

### Using in Insomnia Templates

Variables injected via `env-var` can be used in Insomnia:

```
Authorization: Bearer {{api_key}}
POST {{base_url}}/api/login
{
  "username": "{{username}}",
  "password": "{{password}}"
}
```

---

## PR Comments

When running on pull requests, this action automatically posts detailed results:

### Automatic PR Comments
- **✅ Enabled by default** for `pull_request` events
- **📊 Rich markdown formatting** with pass/fail status
- **🔍 Detailed test breakdown** by suite/collection
- **📋 Failure details** with error messages
- **🔗 GitHub context** (branch, actor, run links)

### Disable PR Comments
```yaml
pr-comment: false
```

### Requires GitHub Token
```yaml
github-token: ${{ secrets.GITHUB_TOKEN }}
```

---

## Error Handling

### Fail Action on Test Failures (Default)
```yaml
fail-on-error: true  # Default behavior
```

### Continue on Test Failures
```yaml
fail-on-error: false  # Action succeeds even if tests fail
```

### Debug Mode
```yaml
debug: true  # Enable detailed logging
```

---

## Migration Notes

### From Insomnia CLI Direct Usage

**Before (direct CLI):**
```yaml
- run: inso run test "My Tests" --env dev
```

**After (this action):**
```yaml
- uses: scarowar/insomnia-run@v1
  with:
    command: 'test'
    identifier: 'My Tests'
    environment: 'dev'
    github-token: ${{ secrets.GITHUB_TOKEN }}
```

### From Other Insomnia Actions

This action provides:
- **✅ Built-in PR comments** with rich formatting
- **✅ GitHub secrets integration** with automatic masking
- **✅ All Inso CLI options** supported
- **✅ Comprehensive error handling** and reporting

---

## Limitations

### Supported Commands
- **✅ `test`** - Execute test suites
- **✅ `collection`** - Execute collections  
- **❌ `export spec`** - Not supported
- **❌ `lint spec`** - Not supported
- **❌ Custom commands** - Not supported

### File Format Support
- **✅ `.insomnia/` directories** (Git Sync)
- **✅ YAML exports** (`.yaml`, `.yml`) - Recommended format
- **✅ JSON exports** (`.json`) - Legacy format  
- **✅ NeDB database files** (`.db.json`)
- **❌ Other formats** - Not supported

### Reporter Format
- **Fixed to `spec`** for optimal PR comment formatting
- Other reporters are not configurable

---

## Troubleshooting

### Common Issues

**"Command not supported" error:**
```
Only 'test' and 'collection' commands are supported
```
**Solution:** Use only supported commands in the `command` input.

**"Identifier ignored" warning:**
```
Detected collection export file. Identifier will be ignored
```
**Solution:** This is expected behavior for single collection exports. The action detects files containing `type: collection.insomnia.rest` and automatically ignores the identifier parameter since collection exports are processed directly.

**Missing PR comments:**
- Ensure `github-token` is provided
- Check that `pr-comment` is not set to `false`
- Verify the event is `pull_request`

**Environment variable not found in Insomnia:**
- Ensure `env-var` format is correct: `key=value`
- Use newlines to separate multiple variables
- Reference in Insomnia templates as `{{key}}`

### Debug Mode

Enable detailed logging:
```yaml
debug: true
```

This provides:
- Command construction details
- Environment variable processing
- CLI execution logs
- Report generation details

---

## Contributing

We welcome contributions! Please see our [Contributing Guidelines](CONTRIBUTING.md) when they become available.

### Development

The core implementation consists of:
- `action.yml` - GitHub Action definition and input validation
- `scripts/execute-insomnia.sh` - Inso CLI execution wrapper  
- `scripts/generate_report.py` - Report parsing and formatting

### Reporting Issues

- 🐛 **Bug reports:** Use GitHub Issues
- 💡 **Feature requests:** Use GitHub Issues  
- 🔒 **Security issues:** See [SECURITY.md](SECURITY.md)

---

## License

This project is licensed under the [MIT License](LICENSE).

---

## Support

- 📖 **Documentation:** [Insomnia CLI Docs](https://docs.insomnia.rest/inso-cli/introduction)
- 💬 **Discussions:** [GitHub Discussions](https://github.com/scarowar/insomnia-action/discussions)
- 🐛 **Issues:** [GitHub Issues](https://github.com/scarowar/insomnia-action/issues)
- 🔒 **Security:** [Security Policy](SECURITY.md)
