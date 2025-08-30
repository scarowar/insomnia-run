# Examples

Real-world workflow examples demonstrating how to use Insomnia Run in different scenarios.

!!! warning "Complete Workflow Structure"
    All examples below show complete GitHub Actions workflow jobs with proper structure. When copying examples, ensure you include the complete `jobs.<job-id>` structure with `runs-on`, `steps`, and the required `actions/checkout` step before the Insomnia Run action. Partial code snippets must be placed within the `steps:` array of a job configuration.

## Basic Test Execution

Execute a simple test suite with PR feedback:

```yaml linenums="1" title="Basic test suite"
# Required permissions for GITHUB_TOKEN
permissions:
  contents: read          # Read repository contents
  pull-requests: write    # Post PR comments

jobs:
  api-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: scarowar/insomnia-run@v0.1.0
        with:
          command: "test"
          identifier: "Authentication Tests"
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

## Environment-Specific Testing

Run collections against different environments:

```yaml linenums="1" title="Staging environment tests"
jobs:
  staging-tests:
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - uses: actions/checkout@v4
      - uses: scarowar/insomnia-run@v0.1.0
        with:
          command: "collection"
          identifier: "API Collection"
          environment: "staging"
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

## Secure API Testing

Inject secrets and environment variables:

```yaml linenums="1" title="Using secrets for API testing"
jobs:
  secure-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: scarowar/insomnia-run@v0.1.0
        with:
          command: "collection"
          identifier: "Authenticated Tests"
          env-var: |
            API_KEY=${{ secrets.API_KEY }}
            BASE_URL=${{ secrets.STAGING_URL }}
            JWT_TOKEN=${{ secrets.JWT_TOKEN }}
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

!!! info "Secret Security"
    The action automatically sanitizes all sensitive values in logs, showing placeholders like `[${ENV_VAR_COUNT} variables]` instead of actual secret values to prevent accidental exposure.

## Matrix Testing Strategy

Test across multiple environments efficiently:

```yaml linenums="1" title="Multi-environment matrix testing"
jobs:
  matrix-tests:
    runs-on: ubuntu-latest
    # Use environment-scoped secrets for consistent secret access
    environment: ${{ matrix.environment }}
    strategy:
      matrix:
        environment: [development, staging, production]
    steps:
      - uses: actions/checkout@v4
      - name: Test ${{ matrix.environment }} environment
        uses: scarowar/insomnia-run@v0.1.0
        with:
          command: "test"
          identifier: "Core API Tests"
          environment: ${{ matrix.environment }}
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

## Load Testing Configuration

Advanced collection testing with iterations and delays:

```yaml linenums="1" title="Load testing setup"
jobs:
  load-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: scarowar/insomnia-run@v0.1.0
        with:
          command: "collection"
          identifier: "Performance Tests"
          iteration-count: 50
          delay-request: 500
          # disable-cert-validation: false  # DEFAULT: Keep SSL validation enabled for security
          # fail-on-error: true             # DEFAULT: Fail workflow on test failures
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

!!! danger "Load Testing Security Warning"
    **Never disable certificate validation in production environments!** Setting `disable-cert-validation: true` makes your tests vulnerable to man-in-the-middle attacks. Only use this in controlled development environments with self-signed certificates.

!!! warning "Error Handling in Load Tests"
    Setting `fail-on-error: false` may hide critical issues during load testing. Consider using the default (`true`) to catch performance regressions and only disable for experimental load tests where some failures are expected.
```

## Data Source Patterns

Different ways to structure your Insomnia data:

```yaml linenums="1" title="Git Sync (recommended)"
jobs:
  api-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run tests from Git Sync
        uses: scarowar/insomnia-run@v0.1.0
        with:
          command: "test"
          identifier: "My Test Suite"
          working-directory: "./insomnia/"  # Directory containing .insomnia/
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

```yaml linenums="1" title="Workspace export"
jobs:
  api-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run tests from workspace export
        uses: scarowar/insomnia-run@v0.1.0
        with:
          command: "test"
          identifier: "My Test Suite"
          working-directory: "./api-tests.yaml"  # Full workspace export file
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

```yaml linenums="1" title="Collection export"
jobs:
  api-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run collection export
        uses: scarowar/insomnia-run@v0.1.0
        with:
          command: "collection"
          # identifier is automatically ignored for single collection exports
          working-directory: "./auth-collection.json"  # Individual collection file
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

## Complete CI/CD Workflow

Production-ready workflow with comprehensive testing:

```yaml linenums="1" title=".github/workflows/api-testing.yml"
name: API Testing Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

permissions:
  pull-requests: write
  contents: read

jobs:
  unit-tests:
    name: Unit API Tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run unit tests
        uses: scarowar/insomnia-run@v0.1.0
        with:
          command: "test"
          identifier: "Unit Tests"
          environment: "test"
          github-token: ${{ secrets.GITHUB_TOKEN }}
          debug: true

  integration-tests:
    name: Integration Tests
    runs-on: ubuntu-latest
    # Use environment-scoped secrets named API_URL and API_KEY in each environment
    environment: ${{ matrix.environment }}
    needs: unit-tests
    strategy:
      matrix:
        environment: [staging, production]
    steps:
      - uses: actions/checkout@v4

      - name: Test ${{ matrix.environment }}
        uses: scarowar/insomnia-run@v0.1.0
        with:
          command: "collection"
          identifier: "Integration Suite"
          environment: ${{ matrix.environment }}
          env-var: |
            API_BASE_URL=${{ secrets.API_URL }}
            API_KEY=${{ secrets.API_KEY }}
          github-token: ${{ secrets.GITHUB_TOKEN }}
          fail-on-error: ${{ matrix.environment == 'production' }}

  smoke-tests:
    name: Smoke Tests
    runs-on: ubuntu-latest
    environment: production
    needs: integration-tests
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4

      - name: Production smoke tests
        uses: scarowar/insomnia-run@v0.1.0
        with:
          command: "collection"
          identifier: "Smoke Tests"
          environment: "production"
          request-name-pattern: "smoke.*"
          env-var: |
            API_BASE_URL=${{ secrets.API_URL }}
            API_KEY=${{ secrets.API_KEY }}
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

## Best Practices

- **Environment separation**: Use different Insomnia environments for development, staging, and production testing
- **Secret management**: Store all sensitive data in GitHub secrets, never hardcode in workflows
- **Environment-scoped secrets**: Use GitHub repository environments with consistent secret names (e.g., `API_URL`, `API_KEY`) rather than dynamic secret references
- **Test organization**: Group related tests into suites and collections for better reporting
- **Conditional execution**: Use matrix strategies and conditional logic for efficient CI/CD pipelines
- **Failure handling**: Set `fail-on-error: false` for non-critical tests that shouldn't block deployments
- **Security hardening**: Pin GitHub Actions to specific commit SHAs instead of version tags for enhanced security (e.g., `actions/checkout@8ade135a41bc03ea155e62e844d188df1ea18608`)
- **Token permissions**: Configure minimal required permissions (`contents: read`, `pull-requests: write`) to enable PR feedback while following the principle of least privilege

!!! tip "Security and Environment Setup"
    **For enhanced security:**
    
    - Pin all GitHub Actions to commit SHAs: Use SHA hashes instead of version tags to prevent supply chain attacks
    - Set explicit permissions in your workflow to limit token scope
    
    **For environment secrets:**
    
    - Create repository environments (Settings → Environments) named `development`, `staging`, and `production`
    - In each environment, define secrets with consistent names like `API_URL` and `API_KEY`
    - This allows matrix jobs to access environment-specific secrets automatically

---

See [Quickstart](quickstart.md) to get started, or [Configuration](configuration.md) for the complete reference.
