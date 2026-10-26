# Handling Secrets

!!! warning "Security Best Practice"
    Never hardcode secrets in workflow files. Always use [GitHub Secrets](https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions) and reference them via `${{ secrets.SECRET_NAME }}`.

## Collection Overrides

Map secrets explicitly into the collection's Insomnia environment with `env-var`. Encode the values first so reserved characters survive Inso's URL decoding:

```yaml
- name: Encode collection secrets for Inso
  id: inso-secrets
  env:
    API_KEY: ${{ secrets.API_KEY }}
    AUTH_TOKEN: ${{ secrets.AUTH_TOKEN }}
  run: |
    python3 - <<'PY'
    import os
    from urllib.parse import quote

    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        for name in ("API_KEY", "AUTH_TOKEN"):
            encoded = quote(os.environ[name], safe="")
            if encoded:
                command_value = encoded.replace("%", "%25")
                print(f"::add-mask::{command_value}")
            print(f"{name}={encoded}", file=output)
    PY

- uses: scarowar/insomnia-run@v0.2.1
  with:
    command: collection
    working-directory: insomnia-export.yaml
    env-var: |
      API_KEY=${{ steps.inso-secrets.outputs.API_KEY }}
      AUTH_TOKEN=${{ steps.inso-secrets.outputs.AUTH_TOKEN }}
```

Access in Insomnia templates:

```jinja2
{{ _.API_KEY }}
{{ _.AUTH_TOKEN }}
```

Inso 13.3.1 applies URL decoding to overrides: `+` becomes a space, `%` introduces percent escapes, and `&` separates keys. The encoding step masks the encoded form before publishing step outputs. Never print unmasked credentials. The shorter direct mappings below assume URL-safe values; otherwise reuse the encoding step. See [environment decoding](../reference/compatibility.md#environment-decoding).

## Runner Environment

A GitHub `env:` block sets operating-system variables. It does not automatically create Insomnia variables such as `{{ _.API_KEY }}`. Map the specific values you need into `env-var`. The direct mapping below requires URL-safe values; otherwise use the encoding step above.

Inso inherits only supported runtime settings and selected public GitHub context. Every other variable is excluded by default, regardless of its name or whether its value looks like a secret. Custom collection values must use `env-var` or a selected Insomnia environment; placing them in `env:` alone does not forward them to collection scripts.

| Runtime settings | Supported variables |
| --- | --- |
| Executables, home, temporary files, and configuration | `PATH`, `HOME`, `TMPDIR`, `TMP`, `TEMP`, `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `XDG_CACHE_HOME` |
| Locale and timezone | `LANG`, `LANGUAGE`, `LC_ALL`, `LC_CTYPE`, `LC_COLLATE`, `LC_MESSAGES`, `LC_MONETARY`, `LC_NUMERIC`, `LC_TIME`, `TZ` |
| Console output | `CI`, `TERM`, `NO_COLOR`, `FORCE_COLOR` |
| Network proxies | `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY`, and their lowercase forms |
| Certificate authorities | `SSL_CERT_FILE`, `SSL_CERT_DIR`, `NODE_EXTRA_CA_CERTS`, `NODE_USE_SYSTEM_CA` |

Selected public GitHub context includes repository, workflow, run, actor, ref, commit SHA, and workspace metadata. GitHub control-file paths and new variables sharing a supported prefix are not automatically inherited. Startup injection settings such as `NODE_OPTIONS` and loader paths are excluded. The same policy applies to capability probes, collection runs, and legacy test-suite runs. It does not change the parent environment or restrict access to files on the runner.

```yaml
env:
  API_KEY: ${{ secrets.API_KEY }}
steps:
  - uses: scarowar/insomnia-run@v0.2.1
    with:
      command: collection
      working-directory: insomnia-export.yaml
      env-var: |
        API_KEY=${{ env.API_KEY }}
```

## Comparison

| Method | Use Case |
|--------|----------|
| `env-var` input | Collection environment overrides, including secrets |
| `env:` block | Runner and process configuration; explicitly map collection values |

The `env-var` input is available only for `command: collection`. For legacy `command: test` suites, select an Insomnia environment with `environment` and use Inso's supported [external vault integration](https://developer.konghq.com/insomnia/external-vault/) when resolving secrets.

## Report Output

Insomnia Run disables Inso CLI telemetry for its child process. It does not change the environment of later workflow steps.

Failure reasons are included by default after shared redaction. Environment overrides are automatically redacted and masked when their key names indicate credentials or their literal/decoded values contain at least eight characters. Literal assignment values are registered in addition to Inso’s URL-form-decoded values; this does not change Inso’s decoding behavior. Short configuration values such as `RETRIES=1` and `DEBUG=true` remain readable. Explicit `redact-values` apply regardless of length. Known encoded/decoded values, proxy credentials, and recognized credential-bearing headers/URLs/query parameters are removed from published names, messages, selected headers, and optional raw diagnostics. JSON, Markdown, JUnit, annotations, comments, and uploaded files use the redacted projection.

Add sensitive values that are not collection overrides, including legacy-suite credentials:

```yaml
- uses: scarowar/insomnia-run@v0.2.1
  with:
    command: collection
    working-directory: insomnia-export.yaml
    redact-values: |
      ${{ secrets.EXTERNAL_CREDENTIAL }}
```

The action input accepts one value per line. For standalone use, repeat `--redact-value`. Very short values may remove unrelated text. Empty values are ignored. Redaction cannot identify every secret or transformation; do not make assertions that print credentials or sensitive response bodies.

Raw Inso output is captured, not streamed. It is hidden by default. `verbose: "true"` alone does not publish it and is rejected for legacy suites. `include-raw-output: "true"` adds redacted diagnostics to reports and a raw file, including summaries, enabled comments, and uploads. Disabling comments/uploads does not remove them from the job summary. See [Debug Mode](../troubleshooting.md#debug-mode).

Log masks are additional protection for logs, not sanitizers for files, comments, artifacts, or process listings. Percent-encoded and other transformed values remain credentials. Inso receives collection overrides as command-line arguments, and standalone `--redact-value` is also an argument. Other processes with access to process listings may see them. The action calls the runner in-process, keeping `redact-values` out of child Python command lines. Both action and standalone execution use the explicit [runtime environment policy](#runner-environment), so unrelated credentials and custom variables do not reach Inso through ambient inheritance. Authenticated proxy settings remain part of the supported network configuration. Integrations must use explicit collection overrides or supported vault configuration instead of relying on ambient credentials. Environment isolation is not a filesystem sandbox and does not make an untrusted collection safe. Use isolated runners, trusted collections, minimal environment credentials, and explicit redaction values.

## Response Headers

`capture-response-headers` is empty by default. It accepts explicit, case-insensitive names such as `X-Request-ID, Server`; wildcards and credential-bearing names such as Authorization, Cookie, and token/API-key headers are rejected.

The opt-in privately enables Inso's full-data `redact` mode and risk acknowledgement. That native file can still contain sensitive data despite its upstream mode name. Insomnia Run publishes only the selected, bounded, redacted headers and discards the private capture; it does not publish native environments, proxy settings, request/response bodies, or arbitrary metadata. A permitted custom header can still contain a sensitive value: add that value to `redact-values` or omit the header.

## Publication Access

Comments and artifacts have repository-specific access and retention policies. Cross-repository and Dependabot PR comments are skipped, but running a collection still executes its scripts. Never use `pull_request_target` with a privileged token to execute untrusted PR content. A skipped comment is not a sandbox.

Keep instance comment tokens, GitHub.com download credentials, and runner artifact credentials separate. Private archive credentials are scoped to `download-token-origin`; see [enterprise credential routing](../reference/inputs.md#enterprise-runners).

## Multi-Environment

Use different secrets for different environments. These direct mappings require URL-safe values; otherwise use the encoding step in [Collection Overrides](#collection-overrides) in each job.

Before using the production job, replace `REVIEWED_RELEASE_SHA` with the full 40-character commit SHA of the v0.2.1 release you reviewed. Obtain it from the verified release tag on the [release page](https://github.com/scarowar/insomnia-run/releases/tag/v0.2.1). The placeholder must be replaced before the workflow can run; keep the version comment when updating the pin.

```yaml
permissions:
  contents: read
  pull-requests: write

jobs:
  staging:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: scarowar/insomnia-run@v0.2.1
        with:
          command: collection
          working-directory: insomnia-export.yaml
          environment: staging
          env-var: |
            API_KEY=${{ secrets.STAGING_API_KEY }}

  production:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: scarowar/insomnia-run@REVIEWED_RELEASE_SHA # v0.2.1
        with:
          command: collection
          working-directory: insomnia-export.yaml
          environment: production
          env-var: |
            API_KEY=${{ secrets.PRODUCTION_API_KEY }}
```
