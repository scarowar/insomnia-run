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

- uses: scarowar/insomnia-run@v0.2.0
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

A GitHub `env:` block sets operating-system variables. It does not automatically create Insomnia variables such as `{{ _.API_KEY }}`. Map the specific values you need into `env-var`:

```yaml
env:
  API_KEY: ${{ secrets.API_KEY }}
steps:
  - uses: scarowar/insomnia-run@v0.2.0
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

Markdown reports include parsed test results and a link to the workflow run. Raw Inso output is captured, not streamed to workflow logs, and is hidden from Markdown and JSON reports by default. `verbose: "true"` alone does not expose that captured output. For debugging, explicitly combine it with `include-raw-output: "true"`; see [Debug Mode](../troubleshooting.md#debug-mode).

Raw output may contain secrets, credentials, URLs, or response bodies. Opting in includes it in Markdown and requested JSON reports, including job summaries, enabled comments, and uploaded report artifacts. Disable comments and uploads during a private debugging run; the job summary still contains the opted-in output. Parsed result names and CLI error messages can also contain sensitive data, so hiding raw output is not a guarantee of redaction.

## Multi-Environment

Use different secrets for different environments:

```yaml
jobs:
  staging:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: scarowar/insomnia-run@v0.2.0
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
      - uses: scarowar/insomnia-run@v0.2.0
        with:
          command: collection
          working-directory: insomnia-export.yaml
          environment: production
          env-var: |
            API_KEY=${{ secrets.PRODUCTION_API_KEY }}
```
