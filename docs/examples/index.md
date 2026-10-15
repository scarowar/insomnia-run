# Examples

Examples use an explicit YAML export path. For legacy Git Sync, pass the parent repository root instead; see [input paths](../reference/inputs.md#input-paths).

## Basic Collection

Run a collection on every PR and push to main:

```yaml title="collection-tests.yml"
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
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false

      - uses: scarowar/insomnia-run@v0.2.0
        with:
          command: collection
          working-directory: insomnia-export.yaml
```

## Basic Test Suite

Run a specific test suite on pull requests:

```yaml title="unit-tests.yml"
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
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false

      - uses: scarowar/insomnia-run@v0.2.0
        with:
          command: test
          working-directory: insomnia-export.yaml
          identifier: "My Test Suite"
```

## With Secrets

Map URL-safe secrets into the collection environment:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: collection
    working-directory: insomnia-export.yaml
    env-var: |
      API_KEY=${{ secrets.API_KEY }}
```

For arbitrary secret values, use the [encoding step](../guides/secrets.md#collection-overrides) to preserve reserved characters through Inso's URL decoding.

## Multi-Environment

Test against multiple environments using a matrix strategy:

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        env: [staging, production]
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false

      - uses: scarowar/insomnia-run@v0.2.0
        with:
          command: collection
          working-directory: insomnia-export.yaml
          environment: ${{ matrix.env }}
```

## Non-Blocking

Run tests without failing the workflow, then handle results manually:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  id: tests
  with:
    command: collection
    working-directory: insomnia-export.yaml
    fail-on-error: "false"

- name: Check results
  run: |
    if [ "${{ steps.tests.outputs.exit-code }}" != "0" ]; then
      echo "Tests failed"
    fi
```

## CI Test Report

Publish a JUnit report while keeping the final failure decision explicit:

Grant `checks: write` when publishing a GitHub test report.

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  id: tests
  with:
    command: collection
    working-directory: insomnia-export.yaml
    fail-on-error: "false"

- name: Publish JUnit report
  if: always() && steps.tests.outputs.junit-file != ''
  uses: dorny/test-reporter@a6ddd83ac95ff4586f5d3aceeb314d9a1841db95 # v3.0.0
  with:
    name: Insomnia API Tests
    path: ${{ steps.tests.outputs.junit-file }}
    reporter: java-junit

- name: Upload JUnit report
  if: always() && steps.tests.outputs.junit-file != ''
  uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
  with:
    name: insomnia-run-junit
    path: ${{ steps.tests.outputs.junit-file }}

- name: Fail workflow on test failures
  if: steps.tests.outputs.exit-code != '0'
  run: exit 1
```

## Scheduled Monitoring

Run API health checks on a schedule (every 6 hours):

```yaml title="api-monitoring.yml"
name: API Monitoring

on:
  schedule:
    - cron: '0 */6 * * *'

jobs:
  monitor:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false

      - uses: scarowar/insomnia-run@v0.2.0
        with:
          command: collection
          working-directory: insomnia-export.yaml
          pr-comment: "false"
```

## Behind Proxy

Route requests through a corporate proxy:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: collection
    working-directory: insomnia-export.yaml
    https-proxy: "https://proxy.example.com:8080"
    http-proxy: "https://proxy.example.com:8080"
    no-proxy: "localhost,127.0.0.1"
```

## Self-Signed Certificates

!!! warning "Development Only"
    Disabling certificate validation is insecure. Only use in development environments.

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: collection
    working-directory: insomnia-export.yaml
    disable-cert-validation: "true"
```

## Create Issue on Failure

Automatically create a GitHub issue when scheduled tests fail:

```yaml
name: API Monitoring

on:
  schedule:
    - cron: '0 */6 * * *'

permissions:
  contents: read
  issues: write

jobs:
  monitor:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false

      - uses: scarowar/insomnia-run@v0.2.0
        id: tests
        with:
          command: collection
          working-directory: insomnia-export.yaml
          pr-comment: "false"
          fail-on-error: "false"

      - name: Write report to file
        if: steps.tests.outputs.exit-code != '0'
        env:
          REPORT_MARKDOWN: ${{ steps.tests.outputs.markdown }}
        run: |
          printf '%s\n' "$REPORT_MARKDOWN" > report.md

      - name: Create Issue on Failure
        if: steps.tests.outputs.exit-code != '0'
        uses: peter-evans/create-issue-from-file@fca9117c27cdc29c6c4db3b86c48e4115a786710 # v6.0.0
        with:
          title: "API Tests Failing"
          content-filepath: report.md
          labels: bug,automated
          update-existing: true
```

## Email Notification

Send email notification on test failure. This example uses AWS SES, but any SMTP server works (SendGrid, Mailgun, Gmail, etc.):

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  id: tests
  with:
    command: collection
    working-directory: insomnia-export.yaml
    fail-on-error: "false"

- name: Send Email on Failure
  if: steps.tests.outputs.exit-code != '0'
  uses: dawidd6/action-send-mail@6e71c855c9a091d80a519621b9fd3e8d252ca40c # v7
  with:
    server_address: email-smtp.${{ secrets.AWS_REGION }}.amazonaws.com
    server_port: 587
    username: ${{ secrets.SMTP_USER }}
    password: ${{ secrets.SMTP_PASSWORD }}
    subject: "API Tests Failed - ${{ github.repository }}"
    to: team@example.com
    from: alerts@example.com
    body: |
      API tests failed in ${{ github.repository }}.

      View results: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
```

## Slack Notification

Send test results to Slack:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  id: tests
  with:
    command: collection
    working-directory: insomnia-export.yaml
    fail-on-error: "false"

- name: Notify Slack on Failure
  if: steps.tests.outputs.exit-code != '0'
  uses: slackapi/slack-github-action@91efab103c0de0a537f72a35f6b8cda0ee76bf0a # v2.1.1
  with:
    webhook: ${{ secrets.SLACK_WEBHOOK }}
    webhook-type: incoming-webhook
    payload: |
      {
        "text": "API Tests Failed in ${{ github.repository }}",
        "blocks": [
          {
            "type": "section",
            "text": {
              "type": "mrkdwn",
              "text": "<${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}|View Results>"
            }
          }
        ]
      }
```

## Long-Running Collections

For large collections or slow APIs, increase the execution timeout:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: collection
    working-directory: insomnia-export.yaml
    execution-timeout: "600"  # 10 minutes
```

## Data-Driven Testing

Run collections with external data files:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: collection
    working-directory: insomnia-export.yaml
    iteration-data: "tests/data/users.csv"
    iteration-count: "10"
```

## JSON Output

Run a collection and save the machine-readable JSON report:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  id: run-cli
  with:
    command: collection
    working-directory: insomnia-export.yaml
    output-format: json

- name: Save JSON report
  env:
    JSON_OUTPUT: ${{ steps.run-cli.outputs.json-output }}
  run: |
    printf '%s' "$JSON_OUTPUT" > test-results.json
```

Upload the report for use in another job:

```yaml
- name: Upload JSON report
  uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
  with:
    name: insomnia-json-report
    path: test-results.json
```
