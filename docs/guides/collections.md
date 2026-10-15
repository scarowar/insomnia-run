# Running Collections

## Basic Usage

Run all requests in a YAML export. For legacy Git Sync, use the parent repository root instead; see [input paths](../reference/inputs.md#input-paths).

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: collection
    working-directory: insomnia-export.yaml
```

## Assertions

Running requests does not automatically assert HTTP status codes or response data. Add explicit tests in the collection's after-response scripts, for example:

```javascript
insomnia.test('Status code is 200', () => {
    insomnia.expect(insomnia.response.code).to.eql(200);
});
```

Empty runs retain exit code `0`, but **No assertions executed** is not successful test validation. Check that requests have supported script assertions and that the selected requests and iterations include them. Report counts are test results, not HTTP requests; results may include assertions, skips, or synthetic execution failures.

## With Environment

Target a specific Insomnia environment:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: collection
    working-directory: insomnia-export.yaml
    environment: staging
```

## Filter Requests

By pattern:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: collection
    working-directory: insomnia-export.yaml
    request-name-pattern: ".*users.*"
```

By ID:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: collection
    working-directory: insomnia-export.yaml
    item: "req_001,req_002"
```

## Iterations

Run the collection multiple times with data from a CSV or JSON file:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: collection
    working-directory: insomnia-export.yaml
    iteration-count: "5"
    iteration-data: "test-data.csv"
```

## Timing

Control request delays and timeouts:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: collection
    working-directory: insomnia-export.yaml
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
    working-directory: insomnia-export.yaml
    bail: "true"
```

## With Secrets

Pass secrets via environment variables:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: collection
    working-directory: insomnia-export.yaml
    env-var: |
      API_KEY=${{ secrets.API_KEY }}
```

Access in Insomnia templates as `{{ _.API_KEY }}`.

See [Handling Secrets](secrets.md) for more options.
