# Troubleshooting

## Collection/Test Not Found

**Error:** `Inso CLI Error (exit code N): <Inso's own stderr>` — Inso prints what went
wrong after the wrapper text. When Inso exits 0 but produces no results, the report
shows `No test results parsed from Inso output` instead.

**Fix:**
- Verify `working-directory` path is correct
- Check `identifier` matches exactly (case-sensitive)
- For Git Sync, ensure `.insomnia/` directory exists

## Environment Not Found

**Error:** `No environment identified`

**Fix:**
- Check environment name matches exactly
- Ensure environment is included in export file

## PR Comments Not Appearing

**Checklist:**
- Workflow triggered by `pull_request` event — other events skip the comment step
- `permissions: pull-requests: write` is set
- `github-token` provided or using default

Since v0.2.0 the action posts **one** comment per pull request, identified by
`comment-tag` (default `insomnia-run-report`), and updates it on every run instead of
posting duplicates. If you are missing the comment, check that no old duplicate comment
from a previous version was deleted along with the tag.

### Fork Pull Requests

On `pull_request` events from forks, `GITHUB_TOKEN` is **read-only**, so the comment
step fails with a permissions error and shows up as a warning annotation — the run
itself still passes. This is expected GitHub behavior, not an action bug.

**Fix:**
- Set `pr-comment: "false"` in fork-heavy repositories
- Or pass a personal access token with `pull-requests: write` via `github-token`
  (note: first-time contributors cannot grant this)

## Secrets Not Working

**Fix:**
- Deliver secrets with the `env-var` input (collection runs only):
  ```yaml
  env-var: |
    API_KEY=${{ secrets.API_KEY }}
  ```
- Reference the value in Insomnia templates as `{{ _.API_KEY }}`
- A step-level `env:` block does **not** work: `{{ _.API_KEY }}` resolves the Insomnia
  environment (fed by `env-var`), not the process environment, so the template renders
  as an empty string and requests fail with authentication errors

See [Handling Secrets](guides/secrets.md) for the full guide and the redaction rules.

## SSL Certificate Errors

For self-signed certificates (dev only):
```yaml
disable-cert-validation: "true"
```

## Timeout Errors

**Per-request timeout:** Increase timeout for individual requests:
```yaml
request-timeout: "60000"  # 60 seconds per request
```

**Execution timeout:** Increase timeout for the entire test run:
```yaml
execution-timeout: "600"  # 10 minutes total
```

## Rate Limiting

### Target API rate limits

Add delay between requests:
```yaml
delay-request: "1000"
```

### GitHub API rate limits (403 / `API rate limit exceeded`)

Fixed by design in v0.2.0: release assets download straight from the release CDN, so
the install path makes at most **one** REST API call on github.com (a single
release-metadata read for exact `vX.Y.Z` pins) — asset bytes never flow through the
API. This includes GitHub Enterprise Cloud and shared runners that exhaust the API
quota. If you still see GitHub API 403s, check where they come from:

- PR comments (enabled by default) legitimately call the API on `pull_request` events —
  set `pr-comment: "false"` to rule them out
- Private/enterprise mirrors fall back to authenticated API calls for the assets —
  see the GHES section below

## Invalid `inso-version`

**Error:** `::error::Invalid inso-version '...'. Provide an exact semver (e.g. 13.2.0).`

**Fix:**
- The input accepts exact semver only — `13.2.0`, not `13`, `13.x`, `latest`, or a URL
- Check the version exists in the [Kong/insomnia releases](https://github.com/Kong/insomnia/releases) (tags look like `core@13.2.0`)
- The download URL is built from your value, so a typo fails with a download error — the release page lists the valid versions

## Wheel or Checksum Failures

**Error:** `Release asset '...' not found on release vX.Y.Z` or
`Checksum verification failed for release vX.Y.Z assets`

The runtime installs a wheel attached to the exact release tag, verified against the
release `SHA256SUMS` and installed with the release `constraints.txt`.

**Fix:**
- Pin an **exact** `vX.Y.Z` tag — branch/SHA/`./` refs skip the release download and install from source with a `::warning::`
- Make sure the pinned tag is a published release of this action (releases list the wheel, `SHA256SUMS`, and `constraints.txt` as assets)
- Check the runner has network egress to `github.com` (or your GHES host)
- A checksum failure means the downloaded bytes do not match the published sums — do not retry blindly; re-check the pinned tag and any proxy that rewrites downloads

## GitHub Enterprise Server and Private Repos

On hosts other than `github.com`, the action first tries the anonymous release CDN
(this works for public repos) and falls back to an authenticated release-asset download
through the GitHub API:

**Fix for private repos / GHES:**
- Provide a token with **read access to the action's repository** (the repo the wheel comes from):
  ```yaml
  - uses: scarowar/insomnia-run@v0.2.0
    with:
      github-token: ${{ secrets.ACTION_REPO_TOKEN }}
      command: collection
      working-directory: .insomnia
  ```
- On GHES, mirror this action's repository with its release assets attached, then pin the matching exact tag

## JSON Output Not Appearing

**Problem:** `json-output` is empty

**Fix:**
- Ensure `output-format: json` is set:
  ```yaml
  output-format: json
  ```
- Access via `steps.<id>.outputs.json-output`

## Python Version Errors

**Error:** `insomnia-run requires Python 3.10 or higher`

**Fix:**
- GitHub-hosted runners include Python 3.10+
- For self-hosted runners, install Python 3.10+:
  ```bash
  sudo apt install python3.10
  ```

## Exit Code 2: Configuration Errors

**Error:** the `exit-code` output is `2` (and with the default `fail-on-error: "true"`,
the run fails with `::error::Insomnia run failed (exit code 2).`)

This is **not a test failure** — the CLI rejected an input or could not write a report.
For CLI-level errors the markdown report may be empty, so there is no report "above" to
read; check the step log for the real cause:

- Invalid `output-format` — only `json` is supported
- Invalid `env-var` format — each line must be `KEY=VALUE`
- A `junit-output` or report path that cannot be written (missing parent directories
  are created automatically; remaining failures are permission/OS errors)
- Missing runner tools — the validation step fails the run directly with
  `::error::Missing required runner tools: ...` (needs `python3`, `curl`, `tar` with
  xz support, and `jq`)

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | All tests passed |
| `1` | One or more tests failed (a timed-out run also exits `1`) |
| `2` | Configuration or usage error — not a test failure |

With the default `fail-on-error: "true"`, any non-zero exit code fails the workflow.
Setting `fail-on-error: "false"` keeps test failures (`1`) from failing the workflow;
`2` signals a configuration or usage error rather than a test result — see
[Exit Code 2](#exit-code-2-configuration-errors).

## Debug Mode

Enable verbose logging:
```yaml
verbose: "true"
```

## Help

- [Open an issue](https://github.com/scarowar/insomnia-run/issues)
- [Start a discussion](https://github.com/scarowar/insomnia-run/discussions)
