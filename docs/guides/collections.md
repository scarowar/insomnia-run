# Running Collections

## Basic Usage

Run all requests in a collection:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: collection
    working-directory: .insomnia
```

## With Environment

Target a specific Insomnia environment:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: collection
    working-directory: .insomnia
    environment: staging
```

## Filter Requests

By pattern:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: collection
    working-directory: .insomnia
    request-name-pattern: ".*users.*"
```

By ID:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: collection
    working-directory: .insomnia
    item: "req_001,req_002"
```

## Iterations

Run the collection multiple times with data from a CSV or JSON file:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: collection
    working-directory: .insomnia
    iteration-count: "5"
    iteration-data: "test-data.csv"
```

## Timing

Control request delays and timeouts:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: collection
    working-directory: .insomnia
    delay-request: "500"
    request-timeout: "30000"
    execution-timeout: "600"
```

- `request-timeout`: Timeout for each individual request (milliseconds)
- `delay-request`: Delay between requests (milliseconds)
- `execution-timeout`: Max time for entire test run (seconds, default: 300)

## Stop on Failure

Stop execution immediately when a request fails:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: collection
    working-directory: .insomnia
    bail: "true"
```

## With Secrets

Pass secrets with the `env-var` input and reference them in Insomnia templates as `{{ _.API_KEY }}`:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: collection
    working-directory: .insomnia
    env-var: |
      API_KEY=${{ secrets.API_KEY }}
```

A step-level `env:` block does not reach Insomnia templates — `{{ _.API_KEY }}` resolves
to an empty string without `env-var`. Secret values (4+ characters) are redacted from
every report.

See [Handling Secrets](secrets.md) for more options.

## Reports

Every run produces a markdown summary (posted as a PR comment on pull requests and
added to the job summary). Additional reporting options:

- `junit-output`: write a JUnit XML report; its path is exposed via the `junit-path` output
- `upload-report`: upload the JUnit report, markdown report, and full redacted raw output as a workflow artifact
- Every failing request emits an `::error::` annotation on the workflow run (first 10 failures)
- Raw output in the markdown report is redacted and truncated at `raw-output-max-bytes` (default 8192)

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  id: tests
  with:
    command: collection
    working-directory: .insomnia
    junit-output: reports/junit.xml
    upload-report: "true"
```
