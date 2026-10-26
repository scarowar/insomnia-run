# Migration

## v0.2.0 to v0.2.1

- Markdown no longer cuts off after 50 assertions. Totals and per-request counts use compact tables, followed by a visible table of failed assertions and their first-line reasons. Full failure output, overviews with more than 10 request occurrences, and optional assertion/header details are expandable without nested sections. Omission counts use the actual output budget; job summaries have a separate budget from comments.
- Credential-bearing dynamic dictionary keys/values and literal override forms receive additional redaction. The child environment now filters recognized cloud/package credentials and GitHub/Actions/state variables. Reviewed GitHub metadata (workspace, repository, ref, and SHA), proxy configuration, and certificate configuration remain supported; GitHub control-file paths are removed. Review integrations that relied on inherited credentials; filtering does not sandbox collection scripts or hide credentials in files.
- Incomplete evidence with no failures or recorded execution error is a protocol error (exit `3`). Assertion-only bail retains exit `1` and `complete: false`; `fail-on-error: false` still permits that case.
- Available truncated TAP failure diagnostics are retained. Markdown simplifies native error wrappers; JSON and JUnit bodies retain the original redacted reason. JUnit summary attributes are bounded and unknown empty-suite duration is omitted.

## v0.1.x to v0.2.0

For production workflows, pin the action to the full commit SHA of the reviewed release.

### Execution and Failure Policy

The default Inso CLI is `13.3.1`. A preinstalled binary must match the requested version exactly. Native collection JSON is now the primary report source when available; legacy test suites and older collection CLIs use TAP.

Wrapper exits distinguish assertion failures (`1`), configuration/reporting errors (`2`), and Inso execution, timeout, or protocol failures (`3`). `fail-on-error: "false"` permits only `1`. Workflows that previously tolerated execution errors must handle this stricter policy.

Legacy `command: test` rejects `verbose: "true"` before launch because script logs can spoof TAP results. Collection verbose mode requires native reporting. Use assertion messages and run-error details before opting into raw diagnostics.

Empty and skipped-only runs do not prove assertions passed. Check `total`, `skipped`, `run-error`, and the selected filters before allowing deployment.

### Reports

The action always writes normalized JSON and Markdown files. Use `json-file` for automation; `output-format: json` requests only the convenience `json-output`, which is empty when it exceeds 64 KiB measured as UTF-16. Check `json-output-omitted` rather than parsing an empty value.

The [version 1 report schema](reference/inputs.md#json-schema-and-evidence) retains flat `results` and adds request execution occurrences, messages, nullable seconds timings, source/completeness metadata, and structured run errors. Run errors are no longer synthetic failed assertions. `requests` counts completed native execution records and is empty for TAP; it is not the number of attempted HTTP requests.

Markdown is bounded and may omit groups/results. JSON and JUnit result lists remain complete for the evidence available. Timeouts and bail runs can have partial evidence; consult `complete`.

JUnit remains enabled by default. A custom `junit-output-file` does not remove the canonical report from `report-directory`. Action report destinations must be under the workspace or runner temp directory, without report collisions, control-file overwrites, or symlink escapes.

### Privacy

Raw output is off by default. Failure details now appear in redacted reports by default. Environment override values are automatically redacted when the key indicates credentials or the decoded value has at least eight characters. Short configuration values remain readable; use explicit `redact-values` for sensitive short values. Explicit values and recognized credential patterns are removed across publication formats. Redaction is best effort, not a guarantee that arbitrary assertion text or response data is secret-free.

Header capture is off by default; `capture-response-headers` accepts literal, non-credential header names only. Raw diagnostics still need `include-raw-output: "true"`. They may reach summaries, comments, artifacts, and JSON files.

Encoded secrets remain sensitive. CLI arguments can appear in process listings, and collection scripts retain access to ordinary runner environment variables and filesystem resources. Use isolated runners and minimum credentials; see [secret handling](guides/secrets.md).

### Comments and Artifacts

Comments now replace an owned comment per workflow/job/matrix/`comment-tag`. Set distinct tags for repeated invocations and [serialize matching writers](reference/inputs.md#comment-identity-and-concurrency) with `cancel-in-progress: false`. Matrix comments are separate, not aggregated. Cross-repository and Dependabot PR comments are skipped with a notice, and comment API failures warn without changing execution results.

Progress and at most ten failure annotations are enabled by default in the action; set `progress: "false"` or `annotations: "false"` to disable them. Standalone CLI defaults remain off.

Optional `upload-artifact` supports GitHub.com and GitHub Enterprise Cloud, including valid `*.ghe.com` instances. GHES requires its own uploader. Use unique artifact names per matrix job/invocation; default retention is 14 days.

### Installation

The toolchain pins `uv 0.13.1` and `uv_build 0.13.1`. Source installation with frozen runtime dependencies remains the default. Only this action's application is built from source; runtime dependency source builds are disabled.

Unbundled Inso archives require a trusted `inso-sha256`; checksum discovery no longer calls the release-metadata API. An explicit local/HTTPS `inso-archive` requires that digest and does not skip verification when a matching binary is preinstalled. Bundled digest conflicts fail. Cached archives are verified on restore.

Optional `runtime-bundle` installation requires `runtime-bundle-sha256`, matching source/lock/Python/platform identity, and a valid hashed wheelhouse. It never silently switches from bundle to source mode.

`python-version: system` keeps an existing Python 3.10+ interpreter for source installation. Setting `runtime-bundle` automatically selects managed CPython `3.14.8`, including when `python-version` is `system`. The explicit managed option is reviewed CPython `3.14.8`, not latest. Linux x64 and macOS support automatic installation; Apple Silicon still needs Rosetta for the official Inso binary. Linux ARM needs compatible provisioned tools; Windows is unsupported.

For offline installation, provision tools and caches or local archives/bundles, then set `offline-install: "true"`. This disables installer/cache network access, not API traffic from your collection or network access by comments/uploads. Dependency actions still need approved mirroring/allowlisting. See [enterprise requirements](reference/inputs.md#enterprise-runners).

Use `inso-archive` and `inso-sha256` for provisioned local Inso archives rather than relying on internal cache filenames. Archive-cache identities change with the cache layout.

Keep credentials separate: `github-token` is for instance comments, `github-com-token` is for public GitHub downloads, and artifacts use runner runtime credentials. A private archive token requires an exact `download-token-origin`; enterprise instance credentials are not public-download credentials.

Inso and runtime-bundle downloads allow only GitHub.com, its API, and its release-asset host by default. List a private mirror's initial HTTPS origin and every additional redirect origin in `download-origins`; credentials remain restricted separately to `download-token-origin`. Local archives remain supported without origin authorization. See the [download configuration example](reference/inputs.md#enterprise-runners). This restriction does not apply to uv's managed-Python downloads or collection HTTP requests.

### Input Paths and Configuration

For a YAML export, use `working-directory: insomnia-export.yaml`. For legacy `.insomnia/Workspace/` data, use its parent repository root, not `.insomnia`.

Set run options through action inputs. Inso 13.3.1 imports only a limited set of global configuration options before applying command defaults. The wrapper does not execute `.insorc` scripts. See [configuration limits](reference/inputs.md#inso-configuration).
