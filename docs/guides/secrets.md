# Handling Secrets

!!! warning "Security Best Practice"
    Never hardcode secrets in workflow files. Always use [GitHub Secrets](https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions) and reference them via `${{ secrets.SECRET_NAME }}`.

## Collection Overrides

Map secrets explicitly into the collection's Insomnia environment with `env-var`:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: collection
    working-directory: .insomnia
    env-var: |
      API_KEY=${{ secrets.API_KEY }}
      AUTH_TOKEN=${{ secrets.AUTH_TOKEN }}
```

Access in Insomnia templates:

```jinja2
{{ _.API_KEY }}
{{ _.AUTH_TOKEN }}
```

## Runner Environment

A GitHub `env:` block sets operating-system variables. It does not automatically create Insomnia variables such as `{{ _.API_KEY }}`. Map the specific values you need into `env-var`:

```yaml
env:
  API_KEY: ${{ secrets.API_KEY }}
steps:
  - uses: scarowar/insomnia-run@v0.2.0
    with:
      command: collection
      working-directory: .insomnia
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

Markdown reports include parsed test results and a link to the workflow logs. Raw Inso output is hidden from Markdown and JSON reports by default. Enable `include-raw-output: "true"` only in trusted workflows where the output is safe to share. Uploaded report artifacts follow the same setting.

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
