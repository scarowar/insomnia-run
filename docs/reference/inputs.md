# Action Inputs

## Required

| Input | Description |
|-------|-------------|
| `command` | `collection` or `test` |
| `working-directory` | Explicit YAML export path, or repository root for legacy Git Sync |

## Input Paths

For an exported workspace or a Git Sync project stored as a YAML file, pass that file's explicit path, for example `working-directory: insomnia-export.yaml`.

For legacy Git Sync data under `.insomnia/Workspace/`, pass the parent repository root, such as `working-directory: .`. Do not pass `.insomnia` itself: Inso appends `.insomnia` when loading this layout and would search for `.insomnia/.insomnia`.

Paths are relative to the workflow step's current directory unless absolute paths are provided. The action must run after the project files have been checked out.

## Common

| Input | Default | Description |
|-------|---------|-------------|
| `identifier` | — | Collection or test suite name |
| `environment` | — | Insomnia environment name |
| `github-token` | — | Token for PR comments and authenticated public GitHub tool downloads |
| `comment-issue-number` | — | Issue or PR number for comments outside `pull_request` workflows |
| `pr-comment` | `true` | Post results to a PR or explicit issue |
| `fail-on-error` | `true` | Fail workflow on test failure |
| `bail` | `false` | Stop on first failure |
| `verbose` | `false` | Capture additional Inso diagnostics; requires `include-raw-output` to expose them in reports |
| `inso-version` | `13.3.1` | Exact Inso CLI version |
| `cache-inso` | `true` | Cache verified Inso archives between workflow runs |
| `execution-timeout` | `300` | Positive max execution time in seconds |
| `output-format` | — | JSON output in addition to Markdown |
| `include-raw-output` | `false` | Include raw Inso output in Markdown and JSON; logs may contain secrets |
| `junit-report` | `true` | Generate a JUnit XML report file |
| `junit-output-file` | — | Custom path for the JUnit XML report |
| `upload-artifact` | `false` | Upload generated reports on GitHub.com, including test failures |
| `artifact-name` | `insomnia-run-reports` | Unique artifact name per invocation and matrix job |
| `artifact-retention-days` | `14` | Retention within repository policy, from 1 to 400 days |
| `data-folders` | - | Folders Insomnia can read/write, comma-separated; supported for both collection and test commands |

For both collection and test commands, separate `data-folders` paths with commas, for example:

```yaml
data-folders: "./fixtures,./uploads"
```

## Collection Only

| Input | Description |
|-------|-------------|
| `request-name-pattern` | Regex to filter requests |
| `item` | Request/folder IDs, comma-separated |
| `globals` | Global environment file, ID, or name |
| `delay-request` | Delay between requests (ms) |
| `iteration-count` | Positive integer; upstream defaults to one iteration |
| `iteration-data` | CSV/JSON file path or HTTP(S) URL; relative files use the process working directory |
| `env-var` | Environment variables, `key=value` per line |

## Test Only

| Input | Default | Description |
|-------|---------|-------------|
| `test-name-pattern` | — | Literal substring of the full test title in Inso 13.3.1 (Mocha `fgrep`) |
| `keep-file` | `false` | Keep generated test file |

## Network

| Input | Default | Description |
|-------|---------|-------------|
| `request-timeout` | — | Timeout per request (ms) |
| `disable-cert-validation` | `false` | Skip SSL verification |
| `https-proxy` | — | HTTPS proxy URL |
| `http-proxy` | — | HTTP proxy URL |
| `no-proxy` | — | Hosts to bypass proxy |

# Action Outputs

| Output | Description |
|--------|-------------|
| `markdown` | Generated Markdown report |
| `json-output` | Generated JSON report |
| `junit-file` | Path to the generated JUnit XML report |
| `exit-code` | `0` = success, nonzero = test or execution failure |

Report counts are **test results**, which can include assertions, skips, and synthetic execution failures, not HTTP requests. Empty runs retain exit code `0`, but show **No Assertions Executed** with the summary **No assertions executed**; this is not successful test validation. Runs with only skipped results are labeled **Skipped**. Invalid CLI options can produce a nonzero exit code without a test report.

Raw Inso diagnostics are captured, not streamed to workflow logs. `verbose` alone does not expose them. Explicitly enable `include-raw-output: "true"` to include them in Markdown and requested JSON reports; raw output may contain secrets and is then shared through job summaries, enabled comments, and uploaded report artifacts. See [Debug Mode](../troubleshooting.md#debug-mode) before opting in.

## Using Outputs

Access the exit code and markdown report from subsequent steps:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  id: tests
  with:
    command: collection
    working-directory: insomnia-export.yaml

- run: |
    echo "Exit code: ${{ steps.tests.outputs.exit-code }}"
```

Access json report from subsequent steps:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  id: tests
  with:
    command: collection
    working-directory: insomnia-export.yaml
    output-format: json

- name: Save JSON report
  env:
    JSON_OUTPUT: ${{ steps.tests.outputs.json-output }}
  run: |
    printf '%s' "$JSON_OUTPUT" > test-results.json
```

Use the generated JUnit report with test reporting or artifact upload:

Grant `checks: write` when publishing a GitHub test report.

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  id: tests
  with:
    command: collection
    working-directory: insomnia-export.yaml
    fail-on-error: "false"

- name: Publish JUnit report
  if: always() && steps.tests.outputs.junit-file != ''
  uses: dorny/test-reporter@a6ddd83ac95ff4586f5d3aceeb314d9a1841db95 # v3.0.0
  with:
    name: Insomnia API Tests
    path: ${{ steps.tests.outputs.junit-file }}
    reporter: java-junit

- name: Upload JUnit report
  if: always() && steps.tests.outputs.junit-file != ''
  uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1
  with:
    name: insomnia-run-junit
    path: ${{ steps.tests.outputs.junit-file }}

- name: Fail workflow on test failures
  if: steps.tests.outputs.exit-code != '0'
  run: exit 1
```

## Conditional Steps

Run steps based on test results:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  id: tests
  with:
    command: collection
    working-directory: insomnia-export.yaml
    fail-on-error: "false"

- name: Deploy
  if: steps.tests.outputs.exit-code == '0'
  run: echo "Deploying..."
```

## Comments Outside Pull Requests

Pull request workflows are detected automatically. For manual, scheduled, deployment, or push workflows, set `comment-issue-number` to the PR or issue that should receive the report:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: collection
    working-directory: insomnia-export.yaml
    comment-issue-number: "123"
```

The workflow token needs `issues: write` for issues and `pull-requests: write` for pull requests.

## Enterprise Runners

Insomnia Run uses `inso` from `PATH` only when its version matches `inso-version`. Otherwise, the action installs the requested version from official Insomnia release assets and verifies the archive's SHA-256 digest before extraction. Cached archives are verified again before use.

Automatic installation supports Linux x64 and macOS Intel runners. On Apple Silicon, the official macOS binary requires Rosetta; provision Rosetta or preinstall a compatible Inso binary. Linux ARM requires a compatible preinstalled Inso binary. Windows is not supported.

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: collection
    working-directory: insomnia-export.yaml
```

The action requires Python 3.10 or newer and uses that interpreter without downloading another Python. Provision exactly `uv 0.11.11` to skip its installer. A different preinstalled uv version triggers setup of the pinned version. Self-hosted runners must support Node.js 24 actions.

The default Inso version and previous defaults have bundled digests and do not query the GitHub release API. Other versions require access to `api.github.com` for their official SHA-256 digest. GitHub Enterprise Server tokens are never sent to public GitHub download APIs.

Runners without public internet access must preinstall matching Inso and uv versions and prepopulate uv's cache with the exact locked runtime packages and build backend. A frozen lockfile contains public artifact URLs; an index environment variable alone does not redirect those URLs to an internal mirror. Set `UV_OFFLINE=true` after provisioning the cache. Set `cache-inso: "false"` if your runner cannot use the Actions cache service.

GitHub Enterprise Server installations must also make the pinned dependency actions available through their supported action mirroring or allowlisting process. Preinstalling tools skips their installers, but GitHub still needs to resolve the referenced actions.

Built-in report uploads use `actions/upload-artifact` for GitHub.com. On GitHub Enterprise Server, use the report outputs with an uploader supported by your installation. Artifact uploads occur before `fail-on-error` is applied. Set distinct `artifact-name` values for matrix jobs and multiple invocations; uploads with the same name conflict.

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: collection
    working-directory: insomnia-export.yaml
    upload-artifact: "true"
    artifact-name: api-tests-${{ matrix.environment }}
    artifact-retention-days: "14"
```

## Inso Configuration

Inso 13.3.1 attempts automatic configuration discovery starting at `workingDir` (or its process working directory when omitted). Its implementation only imports truthy `workingDir`, `ci`, `verbose`, and `printOptions` keys, then overlays command options and defaults. It does not load arbitrary request or collection defaults from `.insorc`.

Use action inputs for run options. Insomnia Run does not expose `--config`, `--printOptions`, or `inso script`; it does not execute `.insorc` scripts. See [upstream compatibility](compatibility.md) for the complete supported option mapping and known documentation discrepancies.
