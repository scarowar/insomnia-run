# Running Collections

## Basic Usage

```yaml
- uses: scarowar/insomnia-run@v0.1.0
  with:
    command: collection
    working-directory: .insomnia
```

## With Environment

```yaml
- uses: scarowar/insomnia-run@v0.1.0
  with:
    command: collection
    working-directory: .insomnia
    environment: staging
```

## Filter Requests

By pattern:

```yaml
- uses: scarowar/insomnia-run@v0.1.0
  with:
    command: collection
    working-directory: .insomnia
    request-name-pattern: ".*users.*"
```

By ID:

```yaml
- uses: scarowar/insomnia-run@v0.1.0
  with:
    command: collection
    working-directory: .insomnia
    item: "req_001,req_002"
```

## Iterations

```yaml
- uses: scarowar/insomnia-run@v0.1.0
  with:
    command: collection
    working-directory: .insomnia
    iteration-count: "5"
    iteration-data: "test-data.csv"
```

## Timing

```yaml
- uses: scarowar/insomnia-run@v0.1.0
  with:
    command: collection
    working-directory: .insomnia
    delay-request: "500"
    request-timeout: "30000"
```

## Stop on Failure

```yaml
- uses: scarowar/insomnia-run@v0.1.0
  with:
    command: collection
    working-directory: .insomnia
    bail: "true"
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

Access in Insomnia templates as `{{ _.API_KEY }}`.

See [Handling Secrets](secrets.md) for more options.
