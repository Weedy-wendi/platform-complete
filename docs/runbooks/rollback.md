# Rollback Runbook

1. Identify the failing release and the last known-good image digest.
2. Enable the relevant kill switch:
   - `models`: stop model calls
   - `evaluation`: stop new runs
   - `mcp`: stop MCP traffic
3. Deploy the previous image digest; keep the current database schema.
4. Verify `/healthz`, `/readyz`, error rate and queue depth.
5. If the schema changed, run the release's `downgrade` only after confirming
   the N-1 application compatibility matrix.
6. Replay DLQ jobs that failed during the rollout.
7. Record the incident timeline, root cause and follow-up actions.
