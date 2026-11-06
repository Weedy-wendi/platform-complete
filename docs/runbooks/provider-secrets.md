# Provider Secrets

Provider rows store only a `secret://` reference. The plaintext key is resolved
at call time and is never written to `provider_config`, `model_call`, logs or
raw artifacts.

## Supported schemes

| Reference | Resolution |
|---|---|
| `secret://env/OPENAI_API_KEY` | environment variable |
| `secret://file//run/secrets/openai_key` | file contents (trimmed) |

Other schemes are rejected by the default resolver; inject a custom
`SecretResolver` (Vault, AWS Secrets Manager, ...) into `ModelGatewayService` for
those.

## Register a provider

```powershell
$env:OPENAI_API_KEY = "..."
python scripts/configure_provider.py `
  --dsn $env:PINGCE_DATABASE_URL `
  --tenant-id tenant-a `
  --name judge `
  --provider openai `
  --model gpt-4o-mini `
  --secret-ref secret://env/OPENAI_API_KEY `
  --check-secret
```

The script prints the provider id and the `secret_ref`, never the key.

## Rotation

1. Update the environment variable or secret file.
2. Restart the API/worker so the process picks up the new value.
3. No database migration is required; the reference is unchanged.
4. Revoke the old key at the provider.

## Verify

```bash
python -m pytest tests/unit/core/test_secrets.py tests/integration/model_gateway -q
```
