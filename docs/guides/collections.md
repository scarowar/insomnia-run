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

Empty runs retain exit code `0`, but **No assertions executed** is not successful test validation. Check that requests have supported script assertions and that the selected requests and iterations include them. Assertion/test counts are separate from request counts and structured run errors. Native collection reports retain completed request occurrences, available HTTP status/timing, assertion messages, and skip status. Timeouts and bail runs can retain partial evidence; an interrupted request may be absent. See [report evidence](../reference/inputs.md#json-schema-and-evidence).

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

Stop after the first failed assertion. Add status assertions when HTTP errors should fail:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: collection
    working-directory: insomnia-export.yaml
    bail: "true"
```

## With Secrets

Map URL-safe secrets into the collection environment:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: collection
    working-directory: insomnia-export.yaml
    env-var: |
      API_KEY=${{ secrets.API_KEY }}
```

Access in Insomnia templates as `{{ _.API_KEY }}`.

For arbitrary secret values, use the [encoding step](secrets.md#collection-overrides) to preserve reserved characters through Inso's URL decoding.

## Response Headers

Header capture is off by default. Retain only explicit, non-credential header names when troubleshooting a request:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: collection
    working-directory: insomnia-export.yaml
    capture-response-headers: "X-Request-ID, Server"
```

Names are case-insensitive; wildcards and credential-bearing names are rejected. This enables a private full-data capture upstream, but publishes only selected, bounded, redacted header values. Response bodies and the native payload are not included. See [header privacy](secrets.md#response-headers).
