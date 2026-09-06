# Getting Started

## Prerequisites

- A GitHub repository
- An Insomnia workspace (exported or via Git Sync)
- Python 3.10+ (pre-installed on GitHub-hosted runners)
- Runner tools: `curl`, `tar` with xz support (`xz-utils`), and `jq` — all pre-installed on GitHub-hosted Ubuntu runners
- Outbound HTTPS from the runner to `github.com`, `pypi.org` + `files.pythonhosted.org`, and your API host — see the [Egress requirements](https://github.com/scarowar/insomnia-run#egress-requirements) section in the README

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
      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2

      - uses: scarowar/insomnia-run@v0.2.0
        with:
          command: collection
          working-directory: .insomnia
```

`pull-requests: write` is needed because `pr-comment` defaults to `true`. If you disable
PR comments, `contents: read` alone is sufficient.

### Pin the exact release tag

The example pins the exact tag `v0.2.0`. When it runs, the action downloads
the wheel from that release. It checks the wheel against `SHA256SUMS`. It
installs the wheel with fixed dependencies. Then the code matches the
pinned release. The alias `@v0.2` also works. Other references install from
source and show a warning.

## Step 3: Push and Run

```bash
git add .github/workflows/api-tests.yml
git commit -m "Add API tests"
git push
```

Open a pull request to see test results as a comment. Each failing test also gets an
`::error::` annotation on the workflow run.

## Next Steps

- [Running Collections](../guides/collections.md)
- [Running Test Suites](../guides/test-suites.md)
- [Handling Secrets](../guides/secrets.md)
- [JUnit Reports & Artifacts](../examples/index.md#junit-report-and-artifact-upload)
