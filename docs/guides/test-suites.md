# Running Test Suites

## Basic Usage

Run a test suite by name:

```yaml
- uses: scarowar/insomnia-run@v0.1.0
  with:
    command: test
    working-directory: .insomnia
    identifier: "My Test Suite"
```

The `identifier` is required for test suites.

## Filter Tests

Run only tests matching a pattern:

```yaml
- uses: scarowar/insomnia-run@v0.1.0
  with:
    command: test
    working-directory: .insomnia
    identifier: "My Test Suite"
    test-name-pattern: ".*login.*"
```

## Stop on Failure

Stop execution immediately when a test fails:

```yaml
- uses: scarowar/insomnia-run@v0.1.0
  with:
    command: test
    working-directory: .insomnia
    identifier: "My Test Suite"
    bail: "true"
```

## Timeout

Set a timeout for individual requests:

```yaml
- uses: scarowar/insomnia-run@v0.1.0
  with:
    command: test
    working-directory: .insomnia
    identifier: "My Test Suite"
    request-timeout: "60000"
```

## With Secrets

Pass secrets via environment variables:

```yaml
- uses: scarowar/insomnia-run@v0.1.0
  with:
    command: test
    working-directory: .insomnia
    identifier: "My Test Suite"
  env:
    API_KEY: ${{ secrets.API_KEY }}
```

## Test vs Collection

| | Collection | Test Suite |
|-|-----------|------------|
| **Purpose** | Run requests | Run JavaScript tests |
| **Identifier** | Optional | Required |
| **Assertions** | Status codes | Any response data |
