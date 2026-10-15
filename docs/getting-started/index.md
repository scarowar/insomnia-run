# Getting Started

## Prerequisites

- A GitHub repository
- An Insomnia workspace (exported or via Git Sync)
- Python 3.10+ (pre-installed on GitHub-hosted runners)

## Step 1: Export Your Workspace

### Option A: Git Sync

For legacy Git Sync data stored under `.insomnia/Workspace/`, set `working-directory` to the parent repository root, such as `working-directory: .`. Passing `.insomnia` itself makes Inso search for a nested `.insomnia/.insomnia` directory.

If your Git Sync project stores a collection as a YAML file instead, pass that file's explicit path as in Option B.

### Option B: Export File

Export your workspace as `insomnia-export.yaml` and commit it to your repository.

The workflow below uses `working-directory: insomnia-export.yaml`. Change it to `working-directory: .` only for the legacy Git Sync layout described above. See [input paths](../reference/inputs.md#input-paths).

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
      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
        with:
          persist-credentials: false

      - uses: scarowar/insomnia-run@v0.2.0
        with:
          command: collection
          working-directory: insomnia-export.yaml
```

## Step 3: Push and Run

```bash
git add .github/workflows/api-tests.yml
git commit -m "Add API tests"
git push
```

Open a pull request to see test results as a comment.

Collections need explicit [script assertions](../guides/collections.md#assertions). **No assertions executed** is not successful test validation, even when Inso exits successfully.

## Next Steps

- [Running Collections](../guides/collections.md)
- [Running Test Suites](../guides/test-suites.md)
- [Handling Secrets](../guides/secrets.md)
