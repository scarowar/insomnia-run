# Handling Secrets

!!! warning "Security Best Practice"
    Never hardcode secrets in workflow files. Always use [GitHub Secrets](https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions) and reference them via `${{ secrets.SECRET_NAME }}`.

## Recommended: the `env-var` Input

Pass secrets with the `env-var` input. Each `KEY=VALUE` pair is handed to Inso as an
`--env-var` override, which merges it into the Insomnia environment data — so
`{{ _.KEY }}` templates in your requests resolve, and the values are redacted from
every report the action produces:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: collection
    working-directory: .insomnia
    env-var: |
      API_KEY=${{ secrets.API_KEY }}
      BASE_URL=https://api.example.com
```

Reference the values in Insomnia templates (headers, body, URLs):

```jinja2
{{ _.API_KEY }}
{{ _.BASE_URL }}
```

For example, an `Authorization` header value of `Bearer {{ _.API_KEY }}` resolves at
run time to `Bearer <your secret>`.

The `env-var` input applies to `command: collection` runs only — see the
[collection-only inputs](../reference/inputs.md#collection-only).

## Why Not the Step `env:` Block?

Setting `env:` on the action step does **not** deliver secrets to Insomnia:

```yaml
# Does NOT work — do not use for secrets
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: collection
    working-directory: .insomnia
  env:
    API_KEY: ${{ secrets.API_KEY }}
```

`{{ _.API_KEY }}` resolves the Insomnia environment object, not the process
environment, and Inso has no built-in template tag for OS environment variables in CI.
With a step `env:` block the template resolves to an **empty string** — requests go out
without the secret and fail with authentication errors that do not point at the cause.
Values passed this way also never reach the action's redactor. Pass secrets through the
`env-var` input instead.

| Method | Reaches Insomnia templates | Redacted from reports |
|--------|----------------------------|-----------------------|
| `env-var` input | Yes (merged into the environment data) | Yes (4+ character values) |
| Step `env:` block | No (renders as empty) | No |

## What Gets Redacted

Every report the action renders (markdown PR comment, JUnit XML, failure annotations,
artifact files) passes through redaction. The following are replaced with
`***REDACTED***`:

- Values passed through the `env-var` input (values of 4+ characters)
- `Authorization` header values captured in Inso output — including `X-Api-Key` and
  `Cookie` headers, and JSON-serialized or indented header dumps
- Tokenized URL query parameters such as `token=`, `access_token=`, `api_key=`,
  `client_secret=`, `password=`, `secret=`, and `signature=`

!!! note "Minimum length for env-var redaction"
    `env-var` values shorter than **4 characters** are not redacted. The CLI emits a
    `::warning::` for each such value (`env-var 'KEY' value is shorter than 4
    characters and will not be redacted from reports.`) — keep secrets at least 4
    characters long.

In addition, the raw output embedded in the markdown report is truncated at
`raw-output-max-bytes` (default 8192 bytes) and can be excluded entirely with
`include-raw-output: "false"`. The full redacted raw output is only written to the
workflow artifact when `upload-report: "true"` is set.

## Multi-Environment

Use different secrets for different environments:

```yaml
jobs:
  staging:
    runs-on: ubuntu-latest
    steps:
      - uses: scarowar/insomnia-run@v0.2.0
        with:
          command: collection
          working-directory: .insomnia
          environment: staging
          env-var: |
            API_KEY=${{ secrets.STAGING_API_KEY }}

  production:
    runs-on: ubuntu-latest
    steps:
      - uses: scarowar/insomnia-run@v0.2.0
        with:
          command: collection
          working-directory: .insomnia
          environment: production
          env-var: |
            API_KEY=${{ secrets.PRODUCTION_API_KEY }}
```
