# Quickstart

Get up and running with Insomnia Run in just a few steps.

## Prerequisites

- An Insomnia workspace or exported collection
- A GitHub repository with Actions enabled
- (Optional) GitHub secrets for API keys, tokens, etc.

---

## 1. Add the Workflow

Create a workflow file at `.github/workflows/insomnia-tests.yml`:

```yaml linenums="1" title=".github/workflows/insomnia-tests.yml"
name: "Insomnia API Tests"

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: scarowar/insomnia-run@v0.1.0
        with:
          command: "test"
          identifier: "My Test Suite"
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

---

## 2. Configure Your Data Source

You can use:

- A `.insomnia/` directory (from Git sync)
- An export file (`export.yaml`, `export.json`, or `data.db.json`)

Set the `working-directory` input as needed:

```yaml
working-directory: "./"           # .insomnia/ folder
working-directory: "./export.yaml" # Export file
```

---

## 3. Run and Review

- On every push or PR, the action will run your Insomnia tests.
- Results are posted as PR comments (if enabled) and as workflow outputs.

![PR Comment Example Placeholder](assets/images/pr-comment-example.png)
*_(Insert screenshot of a PR comment with test results)_*

---

## Next Steps

- See [Configuration](configuration.md) for all inputs and options
- Explore [Examples](examples.md) for advanced usage
- Learn about [Troubleshooting](troubleshooting.md) and best practices
