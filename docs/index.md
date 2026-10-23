# Insomnia Run

![Insomnia Run Cover](assets/images/cover-dark.png#only-dark)
![Insomnia Run Cover](assets/images/cover-light.png#only-light)

Run Insomnia collections and legacy test suites in GitHub Actions with request-grouped reports, redacted failure details, and CI outputs. Insomnia Run is unofficial and is not maintained by Kong.

## Usage

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  id: api
  with:
    command: collection
    working-directory: insomnia-export.yaml
```

The action writes JSON, Markdown, and default-enabled JUnit files. Use `json-file` or `report-directory` for downstream processing, rather than relying on limited step-output JSON. Optional PR comments replace a report per job/matrix/tag; callers must serialize matching writers.

The default Inso version is `13.3.1`. Installation verifies downloaded/cached archives and uses frozen Python dependencies. Optional runtime bundles and local archives support provisioned runners without silently changing the default source-install path.

## Results

`total`, `passed`, `failed`, and `skipped` count assertion/test results. `requests` counts completed native execution records and is empty for TAP reports. Partial evidence is marked; interrupted requests and unknown timings are not invented.

Exit `1` means assertion failures; `2` means a wrapper/configuration/report error; `3` means an Inso execution/timeout/protocol error. `fail-on-error: "false"` permits only `1`.

**No assertions executed** is not successful test validation. Add [collection assertions](guides/collections.md#assertions) and check filters before using a run to gate deployment.

## Documentation

| Page | Description |
| --- | --- |
| [Getting Started](getting-started/index.md) | Create a workflow. |
| [Collections](guides/collections.md) | Assertions, filters, iterations, and timeouts. |
| [Test Suites](guides/test-suites.md) | Legacy suite selection and TAP limits. |
| [Secrets](guides/secrets.md) | Override encoding, redaction, headers, and process exposure. |
| [Reference](reference/inputs.md) | Every action input/output, JSON schema, comments, and installation. |
| [Upstream Compatibility](reference/compatibility.md) | Versioned Inso option mapping and known discrepancies. |
| [Examples](examples/index.md) | Workflow snippets. |
| [Migration](migration.md) | Changes from v0.1.x. |
| [Troubleshooting](troubleshooting.md) | Configuration, privacy, and download errors. |
