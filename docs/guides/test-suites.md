# Running Test Suites

## Basic Usage

Run a test suite by name:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: test
    working-directory: .insomnia
    identifier: "My Test Suite"
```

The `identifier` is required for test suites.

## Filter Tests

Run only tests matching a pattern:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: test
    working-directory: .insomnia
    identifier: "My Test Suite"
    test-name-pattern: ".*login.*"
```

## Stop on Failure

Stop execution immediately when a test fails:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: test
    working-directory: .insomnia
    identifier: "My Test Suite"
    bail: "true"
```

## Timeout

Set a timeout for individual requests:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: test
    working-directory: .insomnia
    identifier: "My Test Suite"
    request-timeout: "60000"
    execution-timeout: "600"
```

- `request-timeout`: Timeout for each individual request (milliseconds)
- `execution-timeout`: Max time for entire test run (seconds, default: 300)

## With Secrets

The `env-var` input — the supported way to deliver secrets to Insomnia — applies to
`command: collection` runs only. If a request under test needs a credential, run it
through a collection with `env-var` instead of committing the secret into the suite's
environment data. See [Handling Secrets](secrets.md) for the working pattern and the
redaction rules (Authorization headers and tokenized URLs are redacted in every run,
including test suites).

## Test vs Collection

| | Collection | Test Suite |
|-|-----------|------------|
| **Purpose** | Run requests | Run JavaScript tests |
| **Identifier** | Optional | Required |
| **Assertions** | Status codes | Any response data |

## Reports

Every run produces a markdown summary (posted as a PR comment on pull requests and
added to the job summary). Additional reporting options:

- `junit-output`: write a JUnit XML report; its path is exposed via the `junit-path` output
- `upload-report`: upload the JUnit report, markdown report, and full redacted raw output as a workflow artifact
- Every failing test emits an `::error::` annotation on the workflow run (first 10 failures)
- Raw output in the markdown report is redacted and truncated at `raw-output-max-bytes` (default 8192)
