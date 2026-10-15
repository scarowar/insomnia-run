# Upstream Compatibility

## Verified Release

The default is Inso **13.3.1**, released on **2026-10-09** and checked against the latest stable release on **2026-10-15**. This is a versioned compatibility statement, not a guarantee about future releases or every Insomnia feature.

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
| `--item` | `item` | Comma-separated action IDs become repeated wrapper and upstream flags, preserving order. |
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
| `--verbose` | `verbose` | Default false; captures diagnostics. Publication additionally requires `include-raw-output`. |
| `--ci` | Always enabled | No interactive prompts. |
| `--reporter` | Always `tap` | Required for parsed reports; other upstream reporters are not selectable. |

### Environment Decoding

Inso 13.3.1 parses each `--env-var` occurrence with `URLSearchParams`, then merges keys in order. Later occurrences override earlier keys. `A=old&B=keep` followed by `A=new` retains `B=keep`. `+` decodes to a space, percent escapes are decoded, and `&` separates entries. Insomnia Run does not silently re-encode or collapse occurrences.

Percent-encode literal values containing these characters before passing them, including secrets. For example, `VALUE=one%2Btwo%26three` produces `one+two&three`. Python's `urllib.parse.quote(value, safe="")` can encode a value. Encoded credentials remain sensitive. See [secret handling](../guides/secrets.md).

### Explicitly Unsupported Options

| Upstream Surface | Status |
| --- | --- |
| Reporter choices `dot`, `list`, `min`, `progress`, `spec` | Not exposed; reports require TAP. |
| Collection `--output` | Not exposed. Wrapper `output-format: json` is a parsed test-report schema, not Inso's execution-data file. |
| `--includeFullData` (`redact`, `plaintext`), `--acceptRisk` | Not exposed. `include-raw-output` is not an equivalent security acknowledgement or execution-data export. |
| `--config`, `--printOptions` | Not exposed. Automatic configuration discovery remains limited upstream behavior; see [configuration](inputs.md#inso-configuration). |
| Upstream `--version`, `--help` | Wrapper flags describe the wrapper, not an arbitrary Inso passthrough. Installation separately checks the Inso version. |
| Interactive selection and unrelated Inso commands | Not supported. |

## Reports and Extensions

Collections emit repeated request-local TAP blocks with restarted assertion IDs. Legacy test suites emit Mocha TAP with a trailing plan. Reports aggregate these into unique result IDs. Incomplete plans and bailouts fail; nonzero process exits become report failures without copying arbitrary diagnostics into result descriptions. The wrapper exits `1` for a failed report rather than preserving every upstream numeric exit code.

A successful collection can legitimately emit no TAP when it has no assertions. This yields **No Assertions Executed**, not **Passed**. Test suites require a TAP plan; an explicit empty plan remains a neutral empty report. Counts describe test results, not HTTP requests. Scripts and test descriptions can themselves disclose sensitive values; default raw-output omission is not universal redaction.

`execution-timeout` is a wrapper-only positive timeout in seconds (default `300`). Numeric validation is deliberately stricter than Inso's permissive integer parsing. `workflow-url`, Markdown, `output-format`, `include-raw-output`, `junit-output`, and the action's `junit-report` / `junit-output-file` are report extensions, not Inso flags.

`github-token`, `pr-comment`, `comment-issue-number`, `fail-on-error`, `inso-version`, `cache-inso`, `upload-artifact`, `artifact-name`, and `artifact-retention-days` control action installation, publication, or workflow failure policy. Their contracts are described in [inputs and outputs](inputs.md), not inherited from the upstream CLI.

## Paths and Runners

Inso supports v4/v5 export files, legacy Git repositories, and NeDB app-data directories. For legacy `.insomnia/Workspace/` data, pass the parent repository root; the [Git adapter](https://github.com/Kong/insomnia/blob/abbf55892e16adafea6eb1d6c12af2fa85d32dc9/packages/insomnia-inso/src/db/adapters/git-adapter.ts) appends `.insomnia` itself. Explicit YAML exports are the documented examples, not the only accepted format.

Automatic installation uses the official Linux x64 `.tar.xz` and macOS `.zip` assets with digest verification. The current macOS executable requires Rosetta on Apple Silicon. Compatible preinstalled binaries may be used on Linux ARM. Windows and automatic installation from upstream PKG/Docker assets are not supported. See [enterprise runners](inputs.md#enterprise-runners).

## Upstream Discrepancies

- Help says `.insomnia` is a working directory; the legacy Git adapter expects its parent.
- Test-filter help says regex; the [test runner](https://github.com/Kong/insomnia/blob/abbf55892e16adafea6eb1d6c12af2fa85d32dc9/packages/insomnia-testing/src/run/run.ts) uses Mocha `fgrep`.
- Collection bail help mentions non-200 responses; execution checks failed assertions. Add explicit status assertions when status matters.
- The configuration guide describes more reusable defaults than 13.3.1 imports. Use explicit action inputs.
- [The collection reporter](https://github.com/Kong/insomnia/blob/abbf55892e16adafea6eb1d6c12af2fa85d32dc9/packages/insomnia-inso/src/reporter/index.ts) emits no TAP for assertion-free requests; absence alone is not evidence of collection failure.

The 13.3.1 update includes quoted-CSV parsing and Liquid-rendering fixes. Iteration data and rendering remain upstream responsibilities; this wrapper does not duplicate those engines. Recheck release notes, both command help screens, option mapping, real-binary compatibility, platform assets, and digests for every default-version update.
