# Quickstart

Get started with Insomnia Run in your repository in just a few steps.

## Prerequisites

Before you begin, make sure you have:

- A GitHub repository with Insomnia test suites or collections
- GitHub Actions enabled in your repository
- Workflow permissions configured for `pull-requests: write` (uses automatic `GITHUB_TOKEN`, no personal token needed)

## 1. Add the Workflow

Create a workflow file at `.github/workflows/insomnia-tests.yml` in your repository:

```yaml linenums="1" title=".github/workflows/insomnia-tests.yml"
name: "Insomnia Run"

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read
  pull-requests: write

jobs:
  api_test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run API Tests
        uses: scarowar/insomnia-run@v0.1.0
        with:
          command: "test"
          identifier: "My Test Suite"
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

## 2. Configure Data Source

Specify where your Insomnia data is located. The `working-directory` input can point to either a directory containing `.insomnia/` (for Git Sync) or the path to an Insomnia export file.

**Git Sync (.insomnia directory):**
```yaml linenums="1" title="Using Git Sync"
- name: Run API Tests
  uses: scarowar/insomnia-run@v0.1.0
  with:
    command: "test"
    identifier: "My Test Suite"
    working-directory: "./"  # Directory containing .insomnia/
    github-token: ${{ secrets.GITHUB_TOKEN }}
```

**Export files:**
```yaml linenums="1" title="Using export files"
- name: Run API Tests from export
  uses: scarowar/insomnia-run@v0.1.0
  with:
    command: "test"
    identifier: "My Test Suite"
    working-directory: "./insomnia-export.yaml"  # Path to export file
    github-token: ${{ secrets.GITHUB_TOKEN }}
```

## 3. Test from Pull Requests

Create a pull request to see the workflow in action:

- Tests execute automatically on PR creation and updates
- Results are posted as PR comments with detailed feedback
- Failed tests can prevent merging if branch protection rules require the test job to pass

!!! tip "Using Different Environments"

    Target specific Insomnia environments by adding the `environment` parameter:

    ```yaml linenums="1" title="Using staging environment"
    - name: Run API Tests on Staging
      uses: scarowar/insomnia-run@v0.1.0
      with:
        command: "test"
        identifier: "My Test Suite"
        environment: "staging"
        github-token: ${{ secrets.GITHUB_TOKEN }}
    ```

## Next Steps

- See [Configuration](configuration.md) for advanced options and all available inputs
- Explore [Examples](examples.md) for common patterns and real-world workflows
