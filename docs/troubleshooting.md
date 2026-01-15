# Troubleshooting

## Collection/Test Not Found

**Error:** `No collection/test suite found`

**Fix:**
- Verify `working-directory` path is correct
- Check `identifier` matches exactly (case-sensitive)
- For Git Sync, ensure `.insomnia/` directory exists

## Environment Not Found

**Error:** `No environment identified`

**Fix:**
- Check environment name matches exactly
- Ensure environment is included in export file

## PR Comments Not Appearing

**Checklist:**
- Workflow triggered by `pull_request` event
- `permissions: pull-requests: write` is set
- `github-token` provided or using default

## Secrets Not Working

**Fix:**
- Use `env:` block:
  ```yaml
  env:
    API_KEY: ${{ secrets.API_KEY }}
  ```
- Access in Insomnia as `{{ _.API_KEY }}`

## SSL Certificate Errors

For self-signed certificates (dev only):
```yaml
disable-cert-validation: "true"
```

## Timeout Errors

**Per-request timeout:** Increase timeout for individual requests:
```yaml
request-timeout: "60000"  # 60 seconds per request
```

**Execution timeout:** Increase timeout for the entire test run:
```yaml
execution-timeout: "600"  # 10 minutes total
```

## Rate Limiting

Add delay between requests:
```yaml
delay-request: "1000"
```

## JSON Output Not Appearing

**Problem:** `json-output` is empty

**Fix:**
- Ensure `output-format: json` is set:
  ```yaml
  output-format: json
  ```
- Access via `steps.<id>.outputs.json-output`

## Python Version Errors

**Error:** `insomnia-run requires Python 3.10 or higher`

**Fix:**
- GitHub-hosted runners include Python 3.10+
- For self-hosted runners, install Python 3.10+:
  ```bash
  sudo apt install python3.10
  ```

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | All tests passed |
| `1` | One or more tests failed |

## Debug Mode

Enable verbose logging:
```yaml
verbose: "true"
```

## Help

- [Open an issue](https://github.com/scarowar/insomnia-run/issues)
- [Start a discussion](https://github.com/scarowar/insomnia-run/discussions)

