# Handling Secrets

!!! warning "Security Best Practice"
    Never hardcode secrets in workflow files. Always use [GitHub Secrets](https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions) and reference them via `${{ secrets.SECRET_NAME }}`.

## Recommended: env Block

Pass secrets using the `env` block (preferred method):

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: collection
    working-directory: .insomnia
  env:
    API_KEY: ${{ secrets.API_KEY }}
    AUTH_TOKEN: ${{ secrets.AUTH_TOKEN }}
```

Access in Insomnia templates:

```jinja2
{{ _.API_KEY }}
{{ _.AUTH_TOKEN }}
```

## Alternative: env-var Input

Use the `env-var` input only when you need explicit key-value overrides for Inso:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: collection
    working-directory: .insomnia
    env-var: |
      API_KEY=${{ secrets.API_KEY }}
      BASE_URL=https://api.example.com
```

## Comparison

| Method | Use Case |
|--------|----------|
| `env:` block | Default for secrets |
| `env-var` input | Explicit mapping, static values |

## Report Output

Markdown reports include parsed test results and a link to the workflow logs. Raw Inso output is hidden from Markdown reports by default. Enable `include-raw-output: "true"` only in trusted workflows where the output is safe to share.

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
        env:
          API_KEY: ${{ secrets.STAGING_API_KEY }}

  production:
    runs-on: ubuntu-latest
    steps:
      - uses: scarowar/insomnia-run@v0.2.0
        with:
          command: collection
          working-directory: .insomnia
          environment: production
        env:
          API_KEY: ${{ secrets.PRODUCTION_API_KEY }}
```
