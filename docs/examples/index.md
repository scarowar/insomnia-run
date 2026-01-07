# Examples

## Basic Collection

Run a collection on every PR and push to main:

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

Run a specific test suite on pull requests:

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

Pass secrets to your Insomnia workspace via environment variables:

```yaml
- uses: scarowar/insomnia-run@v0.1.0
  with:
    command: collection
    working-directory: .insomnia
  env:
    API_KEY: ${{ secrets.API_KEY }}
```

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
      - uses: actions/checkout@v4

      - uses: scarowar/insomnia-run@v0.1.0
        with:
          command: collection
          working-directory: .insomnia
          environment: ${{ matrix.env }}
```

## Non-Blocking

Run tests without failing the workflow, then handle results manually:

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

Run API health checks on a schedule (every 6 hours):

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

Route requests through a corporate proxy:

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

> **Warning:** Only use in development environments.

```yaml
- uses: scarowar/insomnia-run@v0.1.0
  with:
    command: collection
    working-directory: .insomnia
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
      - uses: actions/checkout@v4

      - uses: scarowar/insomnia-run@v0.1.0
        id: tests
        with:
          command: collection
          working-directory: .insomnia
          pr-comment: "false"
          fail-on-error: "false"

      - name: Create Issue on Failure
        if: steps.tests.outputs.exit-code != '0'
        uses: peter-evans/create-issue-from-file@v6
        with:
          title: "API Tests Failing"
          content-filepath: /dev/stdin
          labels: bug,automated
          update-existing: true
        env:
          MARKDOWN: ${{ steps.tests.outputs.markdown }}
```

## Email Notification

Send email notification on test failure. This example uses AWS SES, but any SMTP server works (SendGrid, Mailgun, Gmail, etc.):

```yaml
- uses: scarowar/insomnia-run@v0.1.0
  id: tests
  with:
    command: collection
    working-directory: .insomnia
    fail-on-error: "false"

- name: Send Email on Failure
  if: steps.tests.outputs.exit-code != '0'
  uses: dawidd6/action-send-mail@v7
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
- uses: scarowar/insomnia-run@v0.1.0
  id: tests
  with:
    command: collection
    working-directory: .insomnia
    fail-on-error: "false"

- name: Notify Slack on Failure
  if: steps.tests.outputs.exit-code != '0'
  uses: slackapi/slack-github-action@v2
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
- uses: scarowar/insomnia-run@v0.1.0
  with:
    command: collection
    working-directory: .insomnia
    execution-timeout: "600"  # 10 minutes
```

## Data-Driven Testing

Run collections with external data files:

```yaml
- uses: scarowar/insomnia-run@v0.1.0
  with:
    command: collection
    working-directory: .insomnia
    iteration-data: "tests/data/users.csv"
    iteration-count: "10"
```
