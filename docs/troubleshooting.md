# Troubleshooting

## Collection/Test Not Found

Check that `identifier` matches the intended collection/suite and that the workspace contains it. Use an explicit export path such as `insomnia-export.yaml`. For legacy `.insomnia/Workspace/` data, pass the parent repository root, not `.insomnia`.

A missing target is an execution/configuration problem, not an assertion failure. Keep the parsed run-error details and installation diagnostics when reporting the issue; do not attach credentials or raw exports.

## Environment Not Found

Check the name/ID and whether the environment is included in the export. Runner `env:` values do not automatically populate Insomnia environments. Collections need explicit `env-var` mappings; legacy suites need an Insomnia environment or the supported vault integration.

## PR Comments Not Appearing

Check `comment-status` before changing permissions:

- `skipped`: comments are disabled, no target/token is available, or the PR is from a fork/Dependabot.
- `warning`: publication failed. Check instance-token permissions and API availability. Tests still follow their execution result.
- `stale`: a newer run already owns the comment.
- `updated` or `unchanged`: the existing comment was reused; a new comment is not expected.

Use `pull-requests: write` for PR comments and `issues: write` for explicit issue comments. Outside PR events, set `comment-issue-number`. Multiple invocations in one job need distinct `comment-tag` values. Serialize matching writers with `cancel-in-progress: false`; see [comment concurrency](reference/inputs.md#comment-identity-and-concurrency).

## Secrets Not Working

Inso URL-form decoding turns `+` into a space, decodes percent escapes, and treats `&` as a separator. Use the [encoding step](guides/secrets.md#collection-overrides) for arbitrary values. Access collection variables as `{{ _.API_KEY }}`.

The `env-var` input is collection-only. For legacy suites, select an Insomnia environment and use the supported vault integration. Add sensitive values to `redact-values` when they are not already known overrides. Redaction does not protect process listings; see [report privacy](guides/secrets.md#report-output).

## TLS and Timeouts

Prefer a trusted certificate chain to `disable-cert-validation`. Disabling certificate verification weakens API transport security.

`request-timeout` is milliseconds per request; `execution-timeout` is positive seconds for the whole run. For example:

```yaml
request-timeout: "60000"
execution-timeout: "600"
```

The whole-run timeout stops Inso's process group and returns wrapper exit `3`. Reports are incomplete. Completed native evidence or trustworthy nonverbose TAP may be recovered; an interrupted request and its timing are not invented. Verbose stdout cannot be trusted as TAP and is discarded when no native report exists.

## Rate Limiting

### GitHub Tool Downloads

The action pins `uv 0.13.1` and reuses that exact installed version. Inso installation uses bundled or caller-supplied trusted SHA-256 digests, with no release-metadata API lookup. Unbundled releases require `inso-sha256`; this is not a request to fetch a checksum automatically.

Verified archive caching reduces repeat binary downloads. Cold uv/Python setup, archive downloads, dependency actions, caches, comments, and artifact services can still require network requests and remain subject to their own limits.

Download errors are not repeatedly retried. For `429` or rate-limited `403`, respect the reset window before rerunning. A `403` can also mean missing authorization; `404` can mean an unavailable asset. See [GitHub rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api).

On GitHub.com, public downloads can use the workflow token without a separate PAT. On enterprise instances, use a GitHub.com credential only in `github-com-token`, not the instance comment token. Private HTTPS archives use `download-token` plus its exact authorized origin.

For disconnected runners, provision local materials and select `offline-install: "true"`; see [enterprise installation](reference/inputs.md#enterprise-runners).

### Collection API Requests

`delay-request` slows collection API requests, not GitHub downloads or API calls:

```yaml
delay-request: "1000"
```

Respect the API-under-test's own rate limits and retry policy.

## Inso Installation Fails

A preinstalled `inso` must match `inso-version` exactly. A mismatch triggers installation; `inso-archive` explicitly selects archive installation even if a matching binary exists.

Custom/unbundled archives require a trusted `inso-sha256`. Never replace it with the hash of an untrusted download merely to make verification pass. A supplied digest that conflicts with a bundled digest fails. Verify the source, asset platform, and expected version independently.

Automatic Inso installation supports Linux x64 and macOS. Apple Silicon requires Rosetta for the official x64 binary. Linux ARM needs compatible provisioned tools; Windows is unsupported.

## Installation Fails on Self-Hosted Runners

Provision Python 3.10+ in system mode, or select the reviewed managed `3.14.8` option. The action requires exactly `uv 0.13.1`. Check runner compatibility with the pinned dependency actions.

Default source installation builds this action's wheel with `uv_build 0.13.1` and installs locked dependency wheels. Offline source installation needs the exact cached backend and runtime artifacts. An index override does not redirect public URLs already recorded in `uv.lock`.

An explicit runtime bundle needs a trusted archive digest and matching source, lockfile, Python, and platform identities. A mismatch is fatal; the installer does not silently switch modes.

`offline-install` disables installer/cache network access, not collection HTTP traffic, comments, artifact uploads, or GitHub's resolution of dependency actions. Mirror/allowlist those actions through the installation's supported process. Built-in report upload supports GitHub.com/GHEC, not GHES; use a GHES-compatible uploader with `report-directory`.

## Invalid Action Input

Configuration errors identify incompatible command-specific inputs or the numeric input to correct. Collection-only inputs such as `request-name-pattern` cannot be used with `command: test`; remove the input or select `command: collection`.

`request-timeout` and `delay-request` are non-negative integer milliseconds. `execution-timeout` is positive integer seconds, and `iteration-count` is a positive integer number of iterations. For example, use `request-timeout: "5000"` for five seconds; do not include a unit suffix in the value. Diagnostics explain the accepted form without printing the supplied value.

## Inso Configuration Not Applied

Set run options through action inputs. Inso 13.3.1 imports only truthy `workingDir`, `ci`, `verbose`, and `printOptions` configuration keys before applying command defaults. This wrapper does not expose `--config` or execute `.insorc` scripts. See [configuration limits](reference/inputs.md#inso-configuration).

## JSON Output Not Appearing

Use `json-file` for automation. `json-output` is populated only when `output-format: json` is requested and the complete JSON fits the 64 KiB UTF-16 convenience limit. If `json-output-omitted` is `true`, read the file or artifact instead. No truncated JSON is returned.

If `json-file` is empty, execution may have failed before producing a report. Inspect wrapper exit `2` and step diagnostics rather than parsing arbitrary stderr.

For standalone use, `--json-output path` writes a file. Legacy `--output-format json` uses stderr only for valid report JSON once a report exists; progress and publication diagnostics then go to stdout.

## Exit Codes

| Code | Meaning |
| --- | --- |
| `0` | No assertion/run failure; does not prove assertions ran. |
| `1` | Assertion/test failure only. |
| `2` | Wrapper configuration, validation, startup, or report-writing error. |
| `3` | Inso execution failure, timeout, or reporting-protocol error. |

`fail-on-error: "false"` permits only `1`. Comment API failures warn independently. Installation or artifact/publication failures can fail a workflow separately, before an execution output exists.

## No Assertions Executed

Check collection after-response scripts, request selection, suite selection, and test filters. A successful HTTP response alone is not an assertion. Empty runs are neutral, not successful test validation; skipped-only results are labeled Skipped.

Assertion counts exclude structured run errors. `requests` is completed native execution occurrences, not all attempted HTTP requests, and is empty when TAP cannot provide that evidence.

## Debug Mode

Inso stdout and stderr share a 32 MiB capture limit. Exceeding it stops the process group and returns exit `3` with an incomplete report. Captured streams are discarded; valid completed native evidence can still be reported. Reduce collection logging before retrying. Published raw diagnostics are limited to the last 1 MiB after redaction.

Start with redacted failure reasons, run errors, and trusted progress. Generic execution errors include up to six redacted stderr lines (at most 2 KiB) so startup and connection problems can be diagnosed without raw publication. Add unknown sensitive values to `redact-values`; redaction cannot recognize every credential. For a trusted collection debugging run, opt into raw diagnostics explicitly:

```yaml
verbose: "true"
include-raw-output: "true"
pr-comment: "false"
upload-artifact: "false"
```

Legacy `command: test` rejects verbose mode. For collections, verbose requires native reporting; when a timeout/bail run has no native file, stdout assertions are discarded to prevent console-log forgery. Timeout remains exit `3`; verbose bail without native evidence is a protocol error, also `3`. Nonverbose assertion bail can recover TAP with exit `1` and incomplete evidence.

Standalone collection use can combine `--verbose` and `--include-raw-output`; `--raw-output-file` independently writes redacted diagnostics. Raw output may still disclose secrets, bodies, or URLs unknown to the redactor. Disabling comments/uploads does not remove opted-in raw output from job summaries. Only enable it when everyone with report access may see it.

## Help

[Open an issue](https://github.com/scarowar/insomnia-run/issues) with the action/Inso versions, platform, selected inputs without credentials, and a minimal sanitized reproduction. Follow the private reporting instructions in SECURITY.md for vulnerabilities.
