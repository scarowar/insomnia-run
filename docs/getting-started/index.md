# Getting Started

## Prerequisites

- A GitHub repository
- An Insomnia workspace (exported or via Git Sync)
- Python 3.10+ (pre-installed on GitHub-hosted runners)

## Step 1: Export Your Workspace

### Option A: Git Sync

Enable Git Sync in Insomnia. Your workspace will be saved as `.insomnia/` directory.

### Option B: Export File

Export your workspace as `insomnia-export.yaml` and commit it to your repository.

## Step 2: Create Workflow

Create `.github/workflows/api-tests.yml`:

```yaml title=".github/workflows/api-tests.yml"
name: API Tests

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read
  pull-requests: write

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: scarowar/insomnia-run@v0.1.0
        with:
          command: collection
          working-directory: .insomnia
```

## Step 3: Push and Run

```bash
git add .github/workflows/api-tests.yml
git commit -m "Add API tests"
git push
```

Open a pull request to see test results as a comment.

## Next Steps

- [Running Collections](../guides/collections.md)
- [Running Test Suites](../guides/test-suites.md)
- [Handling Secrets](../guides/secrets.md)
