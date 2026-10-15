# Troubleshooting

## Collection/Test Not Found

**Error:** `No collection/test suite found`

**Fix:**
- Verify `working-directory` path is correct
- Check `identifier` matches exactly (case-sensitive)
- For legacy Git Sync data under `.insomnia/Workspace/`, pass the parent repository root (`working-directory: .`), not `.insomnia`
- For a YAML export or a file-based Git Sync project, pass the explicit file path, such as `working-directory: insomnia-export.yaml`

## Environment Not Found

**Error:** `No environment identified`

**Fix:**
- Check environment name matches exactly
- Ensure environment is included in export file

## PR Comments Not Appearing

**Checklist:**
- For pull requests, use the `pull_request` event and set `permissions: pull-requests: write`
- For manual, deployment, scheduled, or push workflows, set `comment-issue-number`
- For issue comments, set `permissions: issues: write`
- `github-token` is provided or the default token has the required permission

## Secrets Not Working

**Fix:**
- For collections, map secrets with `env-var`:
  ```yaml
  with:
    env-var: |
      API_KEY=${{ secrets.API_KEY }}
  ```
- Access in Insomnia as `{{ _.API_KEY }}`
- A runner `env:` block alone does not populate Insomnia environments. For legacy test suites, use an Insomnia environment and Inso's supported external vault integration.

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

### GitHub Tool Downloads

The action pins uv to `0.11.11` and reuses a matching preinstalled executable. Pinning avoids latest-version discovery, but a cold setup can still download a manifest and binary. On GitHub.com, `github-token` defaults to the workflow's token; no personal access token is required for public tool downloads.

The default Inso release has bundled checksums, so installation does not query the releases API for its digest. Custom versions without bundled checksums require release metadata. Verified archive caching reduces binary downloads, not every GitHub request.

Inso metadata requests stop on HTTP errors without automatic retries. For `429` or a rate-limited `403`, wait for GitHub's reset window before rerunning. A `403` can also indicate insufficient authorization; check the token and permissions rather than repeatedly retrying. A `404` can indicate an unavailable release. See [GitHub's rate-limit guidance](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api).

Outside GitHub.com, the action does not forward enterprise tokens to public GitHub download endpoints. If public downloads are unavailable, provision the exact uv and verified Inso versions on the runner; see [self-hosted installation](#installation-fails-on-self-hosted-runners).

### API Requests in Your Collections

To reduce the request rate to the API under test, add a collection delay. This does not affect GitHub's download or API limits:
```yaml
delay-request: "1000"
```

## Inso Installation Fails

Insomnia Run uses `inso` from `PATH` only when its version matches `inso-version` exactly. A version mismatch triggers installation of the requested version, even if another Inso binary is available.

If the runner cannot download Inso, provision the exact requested version in its image. For a provisioned `13.3.1` binary, select it explicitly:

```yaml
inso-version: "13.3.1"
```

Check `inso --version` on the runner before starting the action. If you provision a different version, set `inso-version` to that exact version instead.

## Inso Configuration Not Applied

**Fix:**
- Set run options through action inputs, not arbitrary `.insorc` defaults
- Inso 13.3.1 only imports truthy `workingDir`, `ci`, `verbose`, and `printOptions` configuration keys; command options/defaults then take precedence
- This wrapper does not expose `--config` or run `.insorc` scripts; see [configuration limits](reference/inputs.md#inso-configuration)

## Installation Fails on Self-Hosted Runners

**Fix:**
- Install Python 3.10 or newer
- Preinstall exactly `uv 0.11.11`, or allow the action to install that pinned version
- For offline runs, prepopulate uv's cache with frozen runtime packages and the build backend, then set `UV_OFFLINE=true`; an index override alone does not replace public URLs in the lockfile
- Ensure the preinstalled Inso binary matches `inso-version` exactly; see [Inso Installation Fails](#inso-installation-fails)

Automatic Inso installation supports Linux x64 and macOS Intel. Apple Silicon needs Rosetta or a compatible preinstalled Inso. Linux ARM requires a compatible preinstalled Inso. Windows is not supported.

Cached and downloaded archives must pass SHA-256 verification. For a custom `inso-version` without an official digest, preinstall and verify that binary in your runner image. Set `cache-inso: "false"` when the Actions cache service is unavailable.

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

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Command succeeded; does not guarantee assertions ran |
| `1` | Test or execution failure |
| Other nonzero | CLI or setup error; inspect the step diagnostics |

## No Assertions Executed

Empty runs retain exit code `0` and are labeled **No Assertions Executed**, with the summary **No assertions executed**, not **Passed**. This is not successful test validation. Check that collection scripts contain explicit assertions and that test-name filters match the intended tests. Runs containing only skipped results are labeled **Skipped**.

Report counts are test results, not HTTP requests; results may include assertions, skips, or synthetic execution failures.

## Debug Mode

Raw Inso diagnostics are captured, not streamed to workflow logs. Verbose alone does not expose them in reports. For a trusted debugging run, explicitly enable both options:

```yaml
verbose: "true"
include-raw-output: "true"
pr-comment: "false"
upload-artifact: "false"
```

For the standalone CLI, combine `--verbose` with `--include-raw-output`.

Raw output may contain secrets, credentials, URLs, and response bodies. Opting in adds it to Markdown and requested JSON reports, including job summaries, enabled comments, and uploaded report artifacts. Disabling comments and uploads does not remove it from the job summary. Only opt in when everyone with access to those reports may see the output; hiding raw output does not guarantee that parsed result names or error messages are redacted.

The workflow link provides execution details such as installation and step failures; it does not expose captured raw Inso diagnostics by default. Start with the parsed report, check the step diagnostics for CLI or installation errors, and use the explicit raw-output opt-in only when its disclosure is acceptable.

## Help

- [Open an issue](https://github.com/scarowar/insomnia-run/issues)
- [Start a discussion](https://github.com/scarowar/insomnia-run/discussions)
