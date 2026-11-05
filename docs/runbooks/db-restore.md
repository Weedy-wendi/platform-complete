# Database Restore Runbook

1. Put the application in maintenance mode / enable the `database` kill switch.
2. Stop writers (API, workers) and confirm the queue is drained or paused.
3. Restore the latest verified MySQL backup to a new instance and run
   `alembic upgrade head`.
4. Validate row counts for `tenant`, `dataset_version`, `run`, `audit_log`.
5. Point the application DSNs at the restored instance; run `/readyz`.
6. Replay queued jobs and re-enable writers.
7. Record restore duration, data loss window and verification evidence.

Quarterly: perform this drill against a non-production snapshot and store the
report under `docs/runbooks/evidence/`.
