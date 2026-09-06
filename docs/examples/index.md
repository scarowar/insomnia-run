# Examples

Third-party actions in these examples are pinned to full commit SHAs (with the release
version in a comment) so examples stay reproducible. Pin `scarowar/insomnia-run` to the
exact release tag in every example.

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
      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2

      - uses: scarowar/insomnia-run@v0.2.0
        with:
          command: collection
          working-directory: .insomnia
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
      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2

      - uses: scarowar/insomnia-run@v0.2.0
        with:
          command: test
          working-directory: .insomnia
          identifier: "My Test Suite"
```

## JUnit Report and Artifact Upload

Write a JUnit XML report, upload it (plus the markdown report and the full redacted raw
output) as a workflow artifact, and publish it with a test-reporting action. Every
failing test also emits an `::error::` annotation on the workflow run automatically.

```yaml title="api-tests-with-report.yml"
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
        id: tests
        with:
          command: collection
          working-directory: .insomnia
          junit-output: reports/junit.xml
          upload-report: "true"        # artifact: junit + markdown + full raw output

      - name: Publish JUnit report
        uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02 # v4.6.2
        with:
          name: junit-report
          path: ${{ steps.tests.outputs.junit-path }}
          if-no-files-found: warn

      - name: Show JUnit path
        run: echo "JUnit report at ${{ steps.tests.outputs.junit-path }}"
```

With `upload-report: "true"` (and no `junit-output` override) the action itself uploads
an artifact named `insomnia-run-report` (configurable via `report-artifact-name`)
containing `junit.xml`, `report.md`, and `raw-output.txt`. If you set `junit-output` to
a workspace path as in the example above, the JUnit file is written there instead — the
artifact then carries `report.md` and `raw-output.txt`, and you upload the JUnit file
yourself, as the "Publish JUnit report" step does. The upload needs no extra workflow
permissions.

## With Secrets

Pass secrets to your Insomnia workspace with the `env-var` input and reference them in
templates as `{{ _.API_KEY }}`:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: collection
    working-directory: .insomnia
    env-var: |
      API_KEY=${{ secrets.API_KEY }}
```

Secret values are redacted from every report the action produces. A step-level `env:`
block does not reach Insomnia templates. See [Handling Secrets](../guides/secrets.md)
for details.

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
      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2

      - uses: scarowar/insomnia-run@v0.2.0
        with:
          command: collection
          working-directory: .insomnia
          environment: ${{ matrix.env }}
```

## Non-Blocking

Run tests without failing the workflow, then handle results manually:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
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

```yaml title="api-monitoring.yml"
name: API Monitoring

on:
  schedule:
    - cron: '0 */6 * * *'

jobs:
  monitor:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2

      - uses: scarowar/insomnia-run@v0.2.0
        with:
          command: collection
          working-directory: .insomnia
          pr-comment: "false"
```

## Behind Proxy

Route requests through a corporate proxy:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: collection
    working-directory: .insomnia
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
      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2

      - uses: scarowar/insomnia-run@v0.2.0
        id: tests
        with:
          command: collection
          working-directory: .insomnia
          pr-comment: "false"
          fail-on-error: "false"

      - name: Write report to file
        if: steps.tests.outputs.exit-code != '0'
        env:
          REPORT_MD: ${{ steps.tests.outputs.markdown }}
        run: printf '%s' "$REPORT_MD" > report.md

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
    working-directory: .insomnia
    fail-on-error: "false"

- name: Send Email on Failure
  if: steps.tests.outputs.exit-code != '0'
  uses: dawidd6/action-send-mail@62a2d05b79935ad4fb90ce9079928099579c14ac # v9
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
    working-directory: .insomnia
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
    working-directory: .insomnia
    execution-timeout: "600"  # 10 minutes
```

## Data-Driven Testing

Run collections with external data files:

```yaml
- uses: scarowar/insomnia-run@v0.2.0
  with:
    command: collection
    working-directory: .insomnia
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
    working-directory: .insomnia
    output-format: json

- name: Save JSON report
  env:
    JSON_OUTPUT: ${{ steps.run-cli.outputs.json-output }}
  run: |
    printf '%s' "$JSON_OUTPUT" > test-results.json
  # This will save the JSON report in the current workspace directory
```

If you want this file accessible across jobs in GitHub Actions, you can also upload it as an artifact:

```yaml
- name: Upload JSON report
  uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02 # v4.6.2
  with:
    name: insomnia-json-report
    path: test-results.json
```
