# Running Test Suites

## Basic Usage

Run a test suite by name:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: test
    working-directory: insomnia-export.yaml
    identifier: "My Test Suite"
```

The `identifier` is required for test suites. Examples use a YAML export containing the legacy suite. For legacy Git Sync, pass the parent repository root instead; see [input paths](../reference/inputs.md#input-paths).

## Filter Tests

Inso 13.3.1 filters tests by a literal substring (Mocha `fgrep`), despite the upstream help describing a regex. Run only tests whose full title contains `login`:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: test
    working-directory: insomnia-export.yaml
    identifier: "My Test Suite"
    test-name-pattern: "login"
```

If the filter matches no tests, Inso can exit successfully without running assertions. **No assertions executed** is not successful test validation; check the pattern and suite contents before relying on the result.

## Stop on Failure

Stop execution immediately when a test fails:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: test
    working-directory: insomnia-export.yaml
    identifier: "My Test Suite"
    bail: "true"
```

## Timeout

Set a timeout for individual requests:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: test
    working-directory: insomnia-export.yaml
    identifier: "My Test Suite"
    request-timeout: "60000"
    execution-timeout: "600"
```

- `request-timeout`: Timeout for each individual request (milliseconds)
- `execution-timeout`: Max time for entire test run (seconds, default: 300)

## With Secrets

Select an Insomnia environment for the suite:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: test
    working-directory: insomnia-export.yaml
    identifier: "My Test Suite"
    environment: CI
```

For secret values, configure Inso's supported [external vault integration](https://developer.konghq.com/insomnia/external-vault/). A runner `env:` block alone does not populate Insomnia environment variables. The `env-var` input is collection-only; see [Handling Secrets](secrets.md).

## Test vs Collection

| | Collection | Test Suite |
|-|-----------|------------|
| **Purpose** | Run requests | Run JavaScript tests |
| **Identifier** | Optional | Required |
| **Assertions** | Explicit script tests | JavaScript unit tests |
