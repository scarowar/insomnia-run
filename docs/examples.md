# Examples

Explore common and advanced usage patterns for Insomnia Run.

---

## Basic Test Suite

```yaml
- uses: scarowar/insomnia-run@v0.1.0
  with:
    command: "test"
    identifier: "Auth Tests"
    github-token: ${{ secrets.GITHUB_TOKEN }}
```

---

## Collection with Environment

```yaml
- uses: scarowar/insomnia-run@v0.1.0
  with:
    command: "collection"
    identifier: "API Collection"
    environment: "staging"
    github-token: ${{ secrets.GITHUB_TOKEN }}
```

---

## With Secrets

```yaml
- uses: scarowar/insomnia-run@v0.1.0
  with:
    command: "collection"
    identifier: "Secure Tests"
    env-var: |
      api_key=${{ secrets.API_KEY }}
      password=${{ secrets.PASSWORD }}
    github-token: ${{ secrets.GITHUB_TOKEN }}
```

---

## Matrix Testing

```yaml
strategy:
  matrix:
    env: [dev, staging, prod]
steps:
  - uses: actions/checkout@v4
  - uses: scarowar/insomnia-run@v0.1.0
    with:
      command: "test"
      identifier: "API Tests"
      environment: ${{ matrix.env }}
      github-token: ${{ secrets.GITHUB_TOKEN }}
```

---

## Advanced Collection Testing

```yaml
- uses: scarowar/insomnia-run@v0.1.0
  with:
    command: "collection"
    identifier: "Load Tests"
    iteration-count: 10
    delay-request: 1000
    disable-cert-validation: true
    bail: true
    github-token: ${{ secrets.GITHUB_TOKEN }}
```

---

## Data Source Examples

```yaml
working-directory: "./"             # .insomnia/ folder
working-directory: "./export.yaml"  # Workspace or collection export
working-directory: "./export.json"  # JSON format
working-directory: "./data.db.json" # NeDB format
```
