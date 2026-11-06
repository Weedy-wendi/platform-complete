# Technical Debt Ledger

| ID | Area | Description | Owner | Severity | Exit criteria |
|---|---|---|---|---|---|
| TD-001 | Frontend | E2E Playwright suite not yet wired to CI | agent-frontend | medium | Key paths run in CI |
| TD-002 | Storage | S3 adapters need the optional `storage` extra in production images | agent-data | medium | Image build includes boto3 |
| TD-003 | Jobs | Celery worker crash injection needs a real worker in integration | agent-eval | medium | Kill-worker test in CI |
| TD-004 | Evaluation | Judge calibration report needs a golden set | agent-eval | high | κ report ≥0.7 |
| TD-005 | Search | Qdrant client is behind an adapter; no live integration yet | agent-search | medium | Qdrant contract run |
| TD-006 | Quality | Contract snapshot must be regenerated after public API changes | agent-qa | low | CI diff gate |
| TD-007 | Frontend | Admin page covers endpoints but not full tenant/user/role/API-key/provider management UI | agent-frontend | medium | CRUD panels + one-time key display |
| TD-008 | Frontend | Run/Badcase views lack metrics charts, failure drill-down and tag/dataset filters | agent-frontend | medium | FE-003/FE-007 parity |
| TD-009 | Operations | Canary promotion is documented but not automated | agent-core | low | Automated canary gate in CI/CD |

Add new debt only with an owner, severity, and a measurable exit criterion.
