# Examples

## Basic Collection

```yaml
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

## Basic Test Suite

```yaml
name: Unit Tests

on:
  pull_request:

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
          command: test
          working-directory: .insomnia
          identifier: "My Test Suite"
```

## With Secrets

```yaml
- uses: scarowar/insomnia-run@v0.1.0
  with:
    command: collection
    working-directory: .insomnia
  env:
    API_KEY: ${{ secrets.API_KEY }}
```

## Multi-Environment

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        env: [staging, production]
    steps:
      - uses: actions/checkout@v4

      - uses: scarowar/insomnia-run@v0.1.0
        with:
          command: collection
          working-directory: .insomnia
          environment: ${{ matrix.env }}
```

## Non-Blocking

```yaml
- uses: scarowar/insomnia-run@v0.1.0
  id: tests
  with:
    command: collection
    working-directory: .insomnia
    fail-on-error: "false"

- name: Check results
  run: |
    if [ "${{ steps.tests.outputs.exit-code }}" != "0" ]; then
      echo "Tests failed"
    fi
```

## Scheduled Monitoring

```yaml
name: API Monitoring

on:
  schedule:
    - cron: '0 */6 * * *'

jobs:
  monitor:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: scarowar/insomnia-run@v0.1.0
        with:
          command: collection
          working-directory: .insomnia
          pr-comment: "false"
```

## Behind Proxy

```yaml
- uses: scarowar/insomnia-run@v0.1.0
  with:
    command: collection
    working-directory: .insomnia
    https-proxy: "https://proxy.example.com:8080"
    http-proxy: "https://proxy.example.com:8080"
    no-proxy: "localhost,127.0.0.1"
```

## Self-Signed Certificates

```yaml
- uses: scarowar/insomnia-run@v0.1.0
  with:
    command: collection
    working-directory: .insomnia
    disable-cert-validation: "true"
```

Only use in development environments.
