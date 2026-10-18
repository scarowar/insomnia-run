# Upstream Compatibility

## Verified Release

The default is Inso **13.3.1**. Compatibility is scoped to its versioned command interfaces and report formats, not every desktop feature or future CLI release. v0.2.0 is unreleased; new features still need release-candidate and hosted validation.

Sources: [official release](https://github.com/Kong/insomnia/releases/tag/core%4013.3.1), [collection reference](https://developer.konghq.com/inso-cli/reference/run_collection/), [test reference](https://developer.konghq.com/inso-cli/reference/run_test/), and [exact-release CLI source](https://github.com/Kong/insomnia/blob/abbf55892e16adafea6eb1d6c12af2fa85d32dc9/packages/insomnia-inso/src/cli.ts). Where published documentation and this release disagree, the verified binary and versioned implementation take precedence.

Insomnia Run supports the `run collection` and `run test` workflows. It is not a replacement for the desktop app, specification lint/export commands, or the `inso script` command.

## Option Mapping

Action inputs and wrapper CLI flags have the same kebab-case name unless the table distinguishes them. An omitted optional input normally leaves the corresponding Inso option unset.

| Upstream Option | Action Input / Wrapper Flag | Behavior |
| --- | --- | --- |
| `run collection`, `run test` | `command` / `run-collection`, `run-test` | Supported commands only. |
| Positional identifier | `identifier` / `--identifier` | Passed as a target after `--`, never interpreted as a flag. Collections may omit it to select the first workspace; test suites require it under CI selection. |
| `-w`, `--workingDir` | `working-directory` / `--working-dir` | Required explicit path; no implicit desktop app-data fallback. Export file, legacy Git repository root, or app-data directory. |
| `-e`, `--env` | `environment` / `--env` | Environment name or ID. Omission uses upstream noninteractive selection; ambiguous environments can fail. |
| `--requestNamePattern` | `request-name-pattern` | Collection regex, upstream default empty. |
| `--item` | `item` | Comma-separated action IDs are trimmed and become repeated wrapper and upstream flags, preserving order and interior characters. |
| `--globals` | `globals` | Global environment file, ID, or name. A file selects the first imported environment. |
| `--delay-request` | `delay-request` | Nonnegative integer milliseconds; upstream default `0`. Explicit zero is forwarded. |
| `--requestTimeout` | `request-timeout` | Nonnegative integer milliseconds; zero disables the request timeout. Omission keeps upstream settings (initialized default 30,000 ms). Both commands. |
| `--env-var` | `env-var` | Collection overrides, one occurrence per line; CLI flag is repeatable. Occurrences remain ordered and unchanged. See decoding below. |
| `--iteration-count` | `iteration-count` | Positive integer; upstream default `1`. The wrapper deliberately rejects zero/negative values instead of allowing a no-iteration success. |
| `--iteration-data` | `iteration-data` | CSV/JSON file path or HTTP(S) URL. Relative files resolve from the process working directory. Environment overrides take precedence over iteration data. |
| `--testNamePattern` | `test-name-pattern` | Literal full-title substring in 13.3.1, not regex; test-only. |
| `--bail` | `bail` | Boolean, default false. Stop after failed assertions/tests; HTTP status alone is not an assertion. |
| `--keepFile` | `keep-file` | Test-only boolean, default false. |
| `--disableCertValidation` | `disable-cert-validation` | Both commands; default false. The wrapper provides `-k` for both, while upstream only provides that short alias for test. |
| `--httpsProxy`, `--httpProxy`, `--noProxy` | `https-proxy`, `http-proxy`, `no-proxy` | Nonempty input overrides upstream proxy environment defaults. Empty inputs do not clear inherited proxies. |
| `--dataFolders [paths...]` | `data-folders` | Both commands. Comma-separated action paths become repeated wrapper flags and upstream variadic values. CLI paths may contain commas; the action's comma-separated input cannot represent such paths. |
| `--verbose` | `verbose` | Default false. Collections require native reporting; legacy test suites reject it before launch to prevent script logs spoofing TAP. |
| `--ci` | Always enabled | No interactive prompts. |
| `--reporter` | Always `tap` | Fallback/partial evidence. Native-capable collections additionally use a private `--output` file. Other reporters are not selectable. |

### Environment Decoding

Inso 13.3.1 parses each `--env-var` occurrence with `URLSearchParams`, then merges keys in order. Later occurrences override earlier keys. `A=old&B=keep` followed by `A=new` retains `B=keep`. `+` decodes to a space, percent escapes are decoded, and `&` separates entries. Insomnia Run does not silently re-encode or collapse occurrences.

Percent-encode literal values containing these characters before passing them, including secrets. For example, `VALUE=one%2Btwo%26three` produces `one+two&three`. Python's `urllib.parse.quote(value, safe="")` can encode a value. Encoded credentials remain sensitive. See [secret handling](../guides/secrets.md).

### Explicitly Unsupported Options

| Upstream Surface | Status |
| --- | --- |
| Reporter choices `dot`, `list`, `min`, `progress`, `spec` | Not exposed; reports require TAP. |
| Collection `--output` | Managed privately by the wrapper. `json-file` uses the normalized wrapper schema, not the unrestricted native export. |
| `--includeFullData` (`redact`, `plaintext`), `--acceptRisk` | Not unrestricted passthroughs. Only explicit `capture-response-headers` privately enables `redact` plus risk acknowledgement; the public report retains selected headers, never bodies. `include-raw-output` is a separate diagnostics opt-in. |
| `--config`, `--printOptions` | Not exposed. Automatic configuration discovery remains limited upstream behavior; see [configuration](inputs.md#inso-configuration). |
| Upstream `--version`, `--help` | Wrapper flags describe the wrapper, not an arbitrary Inso passthrough. Installation separately checks the Inso version. |
| Interactive selection and unrelated Inso commands | Not supported. |

## Reports and Extensions

Native-capable collections use validated private JSON as their primary evidence. Only request identity, status, timings, assertions, optional named headers, and run errors are projected; the native collection/environment/proxy export is not published. Assertion counts come from tests, not Inso's request-failure statistics. Native skip status is preserved.

Legacy suites and older collections use TAP, with unique result IDs across request-local blocks. Timeouts retain completed TAP evidence after the process group is stopped. Missing/incomplete plans, bailouts, and malformed native JSON are structured protocol errors, not synthetic failed assertions. An existing malformed native file never silently falls back to stdout.

Inso 13.3.1 can bail after an assertion failure with exit zero and no native file. Nonverbose mode recovers completed TAP assertions with `complete: false`. Verbose stdout can contain forged TAP: when no native file exists, verbose timeout recovery discards stdout assertions, and verbose bail is a protocol error. Both remain exit `3`. An available valid native file can provide completed evidence even after timeout, still marked incomplete with a timeout error.

A request whose script throws may be absent from Inso's native execution list; the wrapper does not invent that request or its duration. `requests` is the number of completed native records and is unknown for TAP.

The wrapper exits `0` for success, `1` for assertion-only failures, `2` for wrapper configuration/startup/report errors, and `3` for Inso execution/timeout/protocol errors. `fail-on-error: "false"` permits only `1`.

A collection can execute requests without assertions. This yields **No Assertions Executed**, not **Passed**. Legacy test suites require a TAP plan; an explicit empty plan remains neutral. `total`, `passed`, `failed`, and `skipped` describe assertion/test results, not HTTP requests. Failure reasons are published after shared redaction by default; unknown secrets in script output still need explicit protection.

`execution-timeout` is a wrapper-only positive timeout in seconds (default `300`). Numeric validation is stricter than Inso's permissive parsing. `workflow-url`, `output-format`, `include-raw-output`, `junit-output`, `json-output`, `markdown-output`, `raw-output-file`, `redact-value`, `progress`, and `annotations` are wrapper reporting options, not Inso flags. Action equivalents include `junit-report`, `junit-output-file`, and multiline `redact-values`. Progress reports trusted stages/elapsed time, never live counts inferred from stdout.

Action-only installation controls are `inso-version`, `inso-sha256`, `inso-archive`, `cache-inso`, `runtime-bundle`, `runtime-bundle-sha256`, `python-version`, `offline-install`, `github-com-token`, `download-token`, and `download-token-origin`.

Publication/policy controls are `github-token`, `pr-comment`, `comment-tag`, `comment-issue-number`, `fail-on-error`, `upload-artifact`, `artifact-name`, and `artifact-retention-days`. These interfaces belong to this action, not Inso. See [all inputs and outputs](inputs.md) and the [JSON schema/evidence contract](inputs.md#json-schema-and-evidence).

## Paths and Runners

Inso supports v4/v5 export files, legacy Git repositories, and NeDB app-data directories. For legacy `.insomnia/Workspace/` data, pass the parent repository root; the [Git adapter](https://github.com/Kong/insomnia/blob/abbf55892e16adafea6eb1d6c12af2fa85d32dc9/packages/insomnia-inso/src/db/adapters/git-adapter.ts) appends `.insomnia` itself. Explicit YAML exports are the documented examples, not the only accepted format.

Automatic installation uses the official Linux x64 `.tar.xz` and macOS `.zip` assets with digest verification. The current macOS executable requires Rosetta on Apple Silicon. Compatible preinstalled binaries may be used on Linux ARM. Windows and automatic installation from upstream PKG/Docker assets are not supported. See [enterprise runners](inputs.md#enterprise-runners).

## Upstream Discrepancies

- Help says `.insomnia` is a working directory; the legacy Git adapter expects its parent.
- Test-filter help says regex; the [test runner](https://github.com/Kong/insomnia/blob/abbf55892e16adafea6eb1d6c12af2fa85d32dc9/packages/insomnia-testing/src/run/run.ts) uses Mocha `fgrep`.
- Collection bail help mentions non-200 responses; execution checks failed assertions. Add explicit status assertions when status matters.
- The configuration guide describes more reusable defaults than 13.3.1 imports. Use explicit action inputs.
- [The collection reporter](https://github.com/Kong/insomnia/blob/abbf55892e16adafea6eb1d6c12af2fa85d32dc9/packages/insomnia-inso/src/reporter/index.ts) emits no TAP for assertion-free requests; absence alone is not evidence of collection failure.

The 13.3.1 update includes quoted-CSV parsing and Liquid-rendering fixes. Iteration data and rendering remain upstream responsibilities; this wrapper does not duplicate those engines.
