# Action Inputs

## Required

| Input | Description |
| --- | --- |
| `command` | `collection` or `test`. |
| `working-directory` | Export file, legacy Git Sync repository root, or Insomnia app-data directory. |

## Input Paths

For a YAML export or file-based Git Sync project, use the explicit path, such as `working-directory: insomnia-export.yaml`.

For legacy data under `.insomnia/Workspace/`, use the parent repository root (`working-directory: .`), not `.insomnia`. Inso appends `.insomnia` when loading this layout.

Paths resolve from the workflow step's current directory unless absolute. Check out project files before running the action.

## Execution

An empty default below means the input is omitted and Inso keeps its default.

| Input | Default | Description |
| --- | --- | --- |
| `identifier` | Empty | Collection name/workspace ID, or legacy test suite name/API spec ID. Legacy suites require a target in CI. |
| `environment` | Empty | Insomnia environment name or ID. |
| `execution-timeout` | `300` | Positive whole-run timeout in seconds. Stops the Inso process group on expiry. |
| `request-timeout` | Empty | Nonnegative per-request timeout in milliseconds; `0` disables it. |
| `bail` | `false` | Stop after the first failed assertion/test. HTTP status alone is not an assertion. |
| `verbose` | `false` | Additional collection diagnostics; requires native reporting. Rejected for legacy `command: test`. |
| `data-folders` | Empty | Comma-separated paths accessible to Inso and scripts, for either command. |
| `disable-cert-validation` | `false` | Disable TLS certificate validation for API requests. Avoid in production. |
| `https-proxy` | Empty | HTTPS proxy URL for Inso. |
| `http-proxy` | Empty | HTTP proxy URL for Inso. |
| `no-proxy` | Empty | Comma-separated hosts that bypass the proxy. |

Omitted proxy inputs preserve inherited proxy settings. `item` and `data-folders` trim surrounding whitespace without changing quotes, backslashes, or interior spaces. Their comma-separated action inputs cannot represent a value containing a comma; standalone CLI flags are repeatable.

### Collection Only

| Input | Default | Description |
| --- | --- | --- |
| `request-name-pattern` | Empty | Regex matching request names. |
| `item` | Empty | Comma-separated request or folder IDs, in order. |
| `globals` | Empty | Global environment file, ID, or name. |
| `delay-request` | Empty | Nonnegative delay between requests in milliseconds. |
| `iteration-count` | Empty | Positive iteration count; upstream defaults to one. |
| `iteration-data` | Empty | CSV/JSON file path or HTTP(S) URL. Relative files use the process working directory. |
| `env-var` | Empty | Ordered environment overrides, one `KEY=VALUE` occurrence per line, with Inso URL-form decoding. |
| `capture-response-headers` | Empty | Comma-separated, explicit, case-insensitive response header names. No wildcards or credential-bearing names. Values exceeding 2,048 UTF-8 bytes are omitted whole. Requires native reporting. |

Header capture privately enables Inso's `--includeFullData redact --acceptRisk`, then retains only the named headers in the normalized report. It does not publish response bodies or the native export. Header values remain subject to redaction and size limits. See [secret handling](../guides/secrets.md#response-headers).

### Test Only

| Input | Default | Description |
| --- | --- | --- |
| `test-name-pattern` | Empty | Literal substring of the full test title in Inso 13.3.1, not a regex. |
| `keep-file` | `false` | Retain Inso's generated legacy test file. |

## Reports and Publication

| Input | Default | Description |
| --- | --- | --- |
| `output-format` | Empty | Set `json` to request the bounded `json-output` step output. The JSON file is generated regardless. |
| `include-raw-output` | `false` | Include redacted raw diagnostics in Markdown/JSON and a raw report file. Still carries disclosure risk. |
| `redact-values` | Empty | Additional sensitive values, one per line, to remove from published reports. |
| `progress` | `true` | Trusted start, completion, and elapsed-time heartbeat messages. No inferred live request counts. |
| `annotations` | `true` | At most ten bounded, escaped failure/run-error annotations. No invented source locations. |
| `junit-report` | `true` | Generate JUnit XML. |
| `junit-output-file` | Empty | Optional additional JUnit destination. The upload directory still contains the current run's canonical JUnit file. |
| `upload-artifact` | `false` | Upload the report directory on GitHub.com or GitHub Enterprise Cloud. GHES needs a separate uploader. |
| `artifact-name` | `insomnia-run-reports` | Use a distinct name for each action invocation and matrix job. |
| `artifact-retention-days` | `14` | Integer from 1 to 400, subject to repository policy. |
| `pr-comment` | `true` | Replace this workflow/job/matrix/tag's report comment when publication is permitted. |
| `comment-tag` | `default` | Separate multiple action invocations in the same job. |
| `comment-issue-number` | Empty | Explicit issue/PR target for manual, push, scheduled, or deployment workflows. |
| `github-token` | `github.token` | Instance token for comments only; not a public-download token. |
| `fail-on-error` | `true` | Set `false` to permit assertion-failure exit `1` only. Exits `2` and `3` remain fatal. |

Report destinations in Actions must be below the workspace or runner temporary directory. Root destinations, escaping symlinks, colliding reports, and GitHub control files such as `GITHUB_OUTPUT` are rejected. Standalone CLI use supports ordinary local paths.

## Installation

| Input | Default | Description |
| --- | --- | --- |
| `inso-version` | `13.3.1` | Exact requested Inso version. A matching preinstalled binary is reused unless `inso-archive` is set. |
| `inso-sha256` | Empty | Trusted 64-hex-character archive digest. Required when installing an archive with no bundled digest; archive verification rejects conflicts with bundled digests. |
| `inso-archive` | Empty | Explicit local archive path or HTTPS URL. Requires `inso-sha256`; forces archive verification even if Inso is preinstalled. |
| `cache-inso` | `true` | Cache verified archives. Identity includes version, platform, digest, and custom archive source. Restores are verified again. |
| `runtime-bundle` | Empty | Explicit local path or HTTPS URL for a runtime wheelhouse bundle. Omission selects source installation. |
| `runtime-bundle-sha256` | Empty | Required trusted archive digest when `runtime-bundle` is set. |
| `download-token` | Empty | Private archive credential restricted to `download-token-origin`. |
| `download-token-origin` | Empty | Exact HTTPS origin authorized to receive `download-token`. No path or query. |
| `github-com-token` | Empty | Public GitHub download credential. On GitHub.com the workflow token is the fallback; enterprise instance tokens are not forwarded. |
| `offline-install` | `false` | Forbid installer/cache network access. Requires provisioned tools and local installation materials. |
| `python-version` | `system` | Use system Python 3.10+, or select the reviewed managed CPython `3.14.8` build. |

## Action Outputs

Files, not process streams or step-output JSON, are the authoritative reports.

| Output | Description |
| --- | --- |
| `report-directory` | Current invocation's report directory under `RUNNER_TEMP`. |
| `json-file` | Complete normalized JSON report path, when a report exists. |
| `markdown` | Bounded Markdown report used for the job summary and comments. |
| `json-output` | JSON only when requested and within 64 KiB measured as UTF-16. Otherwise empty; never partial JSON. |
| `json-output-omitted` | `true` when requested JSON exceeds that convenience-output budget. |
| `junit-file` | Generated JUnit path, or empty if disabled/unavailable. |
| `raw-file` | Redacted raw diagnostics path only when explicitly enabled. |
| `total` | Number of assertion/test results. |
| `passed` | Passing result count. |
| `failed` | Failing assertion/test count, not a count of run errors. |
| `skipped` | Skipped result count. |
| `requests` | Number of completed native execution records. Empty when unknown, including TAP reports. |
| `run-error` | `true` or `false` when a report exists; empty otherwise. |
| `exit-code` | Wrapper execution result: `0`, `1`, `2`, or `3`; see below. |
| `comment-status` | `created`, `updated`, `unchanged`, `skipped`, `stale`, or `warning`. |
| `comment-id` | Published/existing comment ID when known, otherwise empty. |

Counts are empty when no report exists. GitHub imposes an aggregate job-output budget in addition to this action's convenience-output limit. Prefer `json-file` or report artifacts for downstream processing.

### Exit Codes

| Code | Meaning |
| --- | --- |
| `0` | Execution completed without failing assertions or run errors. Zero assertions is not proof of test coverage. |
| `1` | Assertion/test failures only. |
| `2` | Wrapper configuration, validation, startup, or report-writing error. |
| `3` | Inso execution failure, timeout, or invalid/incomplete reporting protocol. |

These are wrapper codes, not an unconditional pass-through of Inso's exit code. Installation and workflow-publication steps can fail separately, sometimes before an `exit-code` output exists. Comment failures warn and do not replace this execution policy.

### JSON Schema and Evidence

The versioned schema is [`schemas/report-v1.schema.json`](https://github.com/scarowar/insomnia-run/blob/main/schemas/report-v1.schema.json), with a [failed collection example](https://github.com/scarowar/insomnia-run/blob/main/schemas/examples/failed-collection.json).

`schema_version: 1` preserves the flat `results` list and adds `executions`, `source`, `complete`, and `run_error`. Results contain `id`, `status` (`PASS`, `FAIL`, `SKIP`), `description`, nullable `message`, nullable `duration_seconds`, and nullable `execution_id`. Execution records contain an occurrence `id`, original `request_id`, name, zero-based iteration, HTTP status/code, nullable duration in seconds, and selected headers.

An execution occurrence ID is not an Insomnia request ID: iterations and jumps may execute one request more than once. Unknown durations are `null`, not fabricated zero timings.

Collections use a private native JSON report when Inso supports it, projecting only permitted fields. Private native reports are limited to 32 MiB; an oversized or malformed file is a protocol error, not a reason to trust stdout instead. Legacy suites, older collection CLIs, and trustworthy timeout recovery use TAP. The `source` field distinguishes them.

`complete: false` marks partial evidence, including timeouts and the Inso 13.3.1 bail path that omits its native file. Completed native evidence or trustworthy nonverbose TAP may be retained. Verbose stdout is never trusted as TAP: without a native file, verbose timeouts have no recovered assertions, and verbose bail is a protocol error. Both exit `3`. Normal nonverbose assertion bail may recover TAP with exit `1`. `requests` counts completed native records only: it does not count an interrupted request omitted by Inso, and it is unknown for TAP. Run errors have a separate `kind` (`execution`, `timeout`, or `protocol`) and message; they are not synthetic failed assertions.

Markdown groups native results by request, puts failures first, and collapses passing groups. It has a 60,000 UTF-8-byte budget, at most 50 displayed results, bounded names/messages, and at most 8,192 bytes of opted-in raw diagnostics. Truncation is marked. JSON and JUnit result lists are not truncated.

### Standalone CLI

```sh
insomnia-run run-collection -w insomnia-export.yaml \
  --json-output reports/report.json \
  --markdown-output reports/report.md \
  --junit-output reports/junit.xml
```

`--raw-output-file` explicitly writes redacted raw diagnostics without enabling them in the other formats. `--redact-value` is repeatable. `--capture-response-headers` is collection-only. Standalone progress and annotations default to off; enable `--progress` and `--annotations` explicitly.

Legacy `--output-format json` still writes JSON only to stderr once a report exists. Progress, annotations, and report-write diagnostics then use stdout. Without that legacy option, progress and annotations use stderr; Markdown goes to stdout. The action reads files instead of parsing either stream.

## Comment Identity and Concurrency

The comment identity includes workflow path, job ID, matrix values, and `comment-tag`. It is not one combined comment for the whole matrix. Owned comments are found through paginated lookup and replaced only after verifying their author and exact marker.

Callers must serialize writers sharing an identity. Use a distinct `comment-tag` for multiple invocations in one job. For example:

```yaml
permissions:
  contents: read
  pull-requests: write

jobs:
  api:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        environment: [staging, production]
    concurrency:
      group: insomnia-api-${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}-${{ matrix.environment }}
      cancel-in-progress: false
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: scarowar/insomnia-run@v0.2.0
        with:
          command: collection
          working-directory: insomnia-export.yaml
          environment: ${{ matrix.environment }}
          comment-tag: api
```

Include every matrix dimension in the concurrency group, and use a job-specific prefix when copying this example to another job. Keep `cancel-in-progress: false` so an active writer is not interrupted. Generation metadata rejects stale updates under this cooperative serialization. GitHub's comments API provides no atomic upsert or cross-runner exactly-once guarantee. See [GitHub concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency).

Fork and Dependabot PRs skip comment publication. Insufficient permissions, API errors, and ambiguous responses produce a warning rather than failing tests; inspect `comment-status`. Skipping comments does not make untrusted collection scripts safe or grant fork workflows access to secrets. Do not execute untrusted PR code with privileged credentials through `pull_request_target`.

Automatic PR comments need `pull-requests: write`. Explicit issue comments need `issues: write`; set `comment-issue-number` outside PR events. Disabling comments needs no comment-write permission.

## Enterprise Runners

System mode uses an existing Python 3.10+ interpreter. Managed mode selects the reviewed standard CPython 3.14.8 build for Linux x64, macOS Intel, or macOS ARM64; it is not a moving latest-Python selector. The toolchain pins `uv 0.13.1` and `uv_build 0.13.1`. Automatic uv/Inso installation supports Linux x64 and macOS; Apple Silicon needs Rosetta for the official x64 Inso binary. Linux ARM requires provisioned compatible tools; Windows is unsupported. Dependency actions require a compatible Actions Runner (at least 2.327.1 for the pinned Node.js 24 actions).

These asset targets do not qualify every operating-system revision or Linux distribution. Validate the selected binaries against the runner's OS/runtime requirements. Managed Python uses the reviewed local download manifest and its build hashes; later installation/execution does not implicitly download a different interpreter.

Source installation is the default: build this action's wheel with its pinned backend, install runtime dependencies from the frozen lockfile using wheels only, then install the application without dependency resolution. A bundle is an explicit alternative, not an automatic fallback. Its trusted archive hash, source/lock identity, Python/platform identity, wheel hashes, and manifest must all agree. A bundle built for a different checkout or interpreter is rejected.

`offline-install: "true"` disables installer downloads and remote cache operations. Provision matching Inso and uv, an interpreter (or the reviewed managed build), and either the frozen dependency/backend cache or a compatible local bundle. Public artifact URLs in the lockfile are not redirected merely by setting an index mirror. GitHub must still resolve dependency actions through the installation's supported mirroring/allowlisting. Optional comments and uploads use their own network services; collection HTTP requests are not sandboxed by offline installation.

There are three separate GitHub credential audiences:

- `github-token`: instance API access for comments.
- `github-com-token`: GitHub.com tool downloads, not enterprise API access.
- Runner runtime credentials: artifact services, managed by GitHub, not either input token.

Private archive downloads may additionally use `download-token`, restricted to the exact HTTPS `download-token-origin`. HTTPS redirects are validated and credentials are not forwarded to another origin. Installer credentials are not intended for collection execution; use `env-var` or the supported vault integration for API-test credentials.

Built-in uploads support GitHub.com and valid HTTPS `*.ghe.com` GitHub Enterprise Cloud origins. They do not support GitHub Enterprise Server (GHES). Use `report-directory` with an installation-supported uploader on GHES. See [upload-artifact support](https://github.com/actions/upload-artifact#v4---whats-new).

Verified archives avoid checksum release-metadata API calls; they do not remove every download or GitHub rate limit. Supply trusted digests for unbundled Inso versions, use verified archive caching, or provision local archives when public downloads are unavailable.

## Inso Configuration

Inso 13.3.1 attempts automatic configuration discovery starting at `workingDir`. Its implementation imports truthy `workingDir`, `ci`, `verbose`, and `printOptions` keys, then overlays command options and defaults. It does not load arbitrary collection defaults from `.insorc`.

Set run options through action inputs. Insomnia Run does not expose `--config`, `--printOptions`, or `inso script`, and does not execute `.insorc` scripts. See [upstream compatibility](compatibility.md).
