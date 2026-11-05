# Canary and Rollback Runbook

## Canary

1. Build an immutable image and record its digest.
2. Deploy the canary to one worker / one API replica behind the same load balancer.
3. Watch for 10 minutes:
   - HTTP 5xx rate and P95 latency
   - queue depth and dead-letter count
   - model error rate and cost
   - audit write failures
4. Promote only when all signals stay within the release budget; otherwise roll back.

## Rollback

1. Identify the failing release and the last known-good digest.
2. Enable the relevant kill switch (`models`, `evaluation`, `mcp`) if the blast
   radius is still growing.
3. Deploy the previous digest; keep the current schema during the rollback.
4. Verify `/healthz`, `/readyz`, error rate and queue depth.
5. Replay DLQ jobs that failed during the rollout and record the incident.

## Evidence

Store the canary dashboard snapshot, image digests, decision timestamp and
rollback reason with the release record.
