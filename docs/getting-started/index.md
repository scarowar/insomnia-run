# Getting Started

v0.2.0 is unreleased. Examples use its intended tag; use a reviewed full commit SHA until the release exists, and keep SHA pinning in production.

## Prerequisites

- A GitHub repository
- An Insomnia workspace (exported or via Git Sync)
- System Python 3.10+, or the explicit reviewed managed Python option
- Trusted collection scripts and suitable API credentials

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
    concurrency:
      group: insomnia-tests-${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
      cancel-in-progress: false
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
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
git commit -m "test: run collection assertions in CI" -m "Check API behavior on pull requests and main branch pushes."
git push
```

The run writes a job summary and report files. Trusted same-repository PR runs can also publish a comment; fork/Dependabot PR comments are skipped, and comment API failures warn. Repeated runs replace the same job's owned comment under the configured concurrency group.

Collections need explicit [script assertions](../guides/collections.md#assertions). **No assertions executed** is not successful test validation, even when Inso exits successfully.

## Next Steps

- [Running Collections](../guides/collections.md)
- [Running Test Suites](../guides/test-suites.md)
- [Handling Secrets](../guides/secrets.md)
