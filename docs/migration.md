# Migration

During 0.x, minor releases may change defaults and behavior — that is the versioning
contract. This guide lists every change in v0.2.0 that can affect an existing workflow,
why it changed, and what you need to do.

## Update the action reference

```yaml
# before (v0.1.x)
- uses: scarowar/insomnia-run@v0.1.2

# after (v0.2.0)
- uses: scarowar/insomnia-run@v0.2.0
```

Pin the **exact** release tag. The moving minor alias `@v0.2` also works, but exact tags
are what keeps the runtime install reproducible (see the first row of the table below).

## Changes at a glance

| Change | Why | What to do |
|--------|-----|------------|
| The action runtime is now installed from a release-attached wheel, resolved from the exact tag in `uses:` and verified against the release `SHA256SUMS` and `constraints.txt` | Reproducible, checksum-verified installs with pinned transitive dependencies | Pin an exact `vX.Y.Z` tag. Branch/SHA/local refs (`uses: ./`) still work but install from source with a loud `::warning::` |
| Default `inso-version` bumped from 12\.2\.0 to 13.2.0 | Newer Inso CLI; its flags were verified byte-identical with the previous default | Nothing. Workflows that pinned an explicit `inso-version` keep it. The input accepts exact semver only |
| Secrets are redacted in every report (markdown, JUnit, annotations, artifacts) | `env-var` input values, `Authorization` headers, and tokenized URLs could leak into raw output | Nothing. Env-var values (4+ characters), `Authorization` headers, and tokenized URLs are all redacted — see [Handling Secrets](guides/secrets.md) |
| Raw Inso output in the markdown report is truncated (default 8192 bytes) | Keeps PR comments readable and bounded | Increase `raw-output-max-bytes` or use `include-raw-output: "false"`. The full redacted output is only in the artifact when `upload-report: "true"` |
| PR comments now update one comment instead of posting a duplicate per run | A PR with many pushes collected one comment per run | Nothing for the default. Stale duplicate comments from v0.1.x must be deleted manually once. Set a distinct `comment-tag` per invocation if the action runs multiple times on the same PR |
| New inputs: `junit-output`, `upload-report`, `report-artifact-name`, `include-raw-output`, `raw-output-max-bytes`, `comment-tag` | JUnit reporting, artifacts, and comment idempotency | None are required; all have defaults. See the [reference](reference/inputs.md) |
| New output: `junit-path` | Lets follow-up steps publish the JUnit report to test-reporting tools | Opt in with `junit-output` or `upload-report` |
| One `::error::` annotation per failing test (first 10 failures) | Failing tests show up on the workflow run and in the PR files view without reading logs | Nothing; annotations are emitted automatically |
| Supported runners are Linux x64 only; macOS, Windows, and arm64 fail with a clear error | Kong publishes Inso CLI binaries for Linux x64 only (no arm64 assets upstream) | Run on `ubuntu-latest` (x86_64) |
| Release assets download straight from the CDN instead of the REST API | Removes the API rate-limit failure class on GitHub Enterprise Cloud and shared runners. Exact-tag installs make at most one API call (release metadata); only PR comments (when enabled) and the private-repo asset fallback use authenticated calls | Nothing |
| The `rich` dependency was removed | Smaller runtime; errors are styled through the CLI framework itself | Nothing |

## Inso version

The default Inso CLI version is now 13.2.0. If your workflow relies on a specific Inso
version, pin it explicitly — the input accepts exact semver values only:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: collection
    working-directory: .insomnia
    inso-version: "13.2.0"
```

## Permissions

The action itself needs no more than `contents: read` by default. Two features request
more:

| Feature | Permission needed |
|---------|-------------------|
| `pr-comment: true` (default) on `pull_request` events | `pull-requests: write` |
| `upload-report: true` | None beyond the default — artifact uploads use the runner's runtime token, not your token |

Set the minimum that matches the features you enable:

```yaml
permissions:
  contents: read
  pull-requests: write   # only needed for PR comments
```

See [Handling Secrets](guides/secrets.md) for the redaction behavior, and
[Troubleshooting](troubleshooting.md) if the new install step reports a missing release
asset or a checksum failure.
