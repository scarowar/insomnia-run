# Handling Secrets

## Recommended: env Block

Pass secrets using the `env` block (preferred method):

```yaml
- uses: scarowar/insomnia-run@v0.1.0
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

Use the `env-var` input for explicit key-value mapping:

```yaml
- uses: scarowar/insomnia-run@v0.1.0
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

## Multi-Environment

Use different secrets for different environments:

```yaml
jobs:
  staging:
    runs-on: ubuntu-latest
    steps:
      - uses: scarowar/insomnia-run@v0.1.0
        with:
          command: collection
          working-directory: .insomnia
          environment: staging
        env:
          API_KEY: ${{ secrets.STAGING_API_KEY }}

  production:
    runs-on: ubuntu-latest
    steps:
      - uses: scarowar/insomnia-run@v0.1.0
        with:
          command: collection
          working-directory: .insomnia
          environment: production
        env:
          API_KEY: ${{ secrets.PRODUCTION_API_KEY }}
```
