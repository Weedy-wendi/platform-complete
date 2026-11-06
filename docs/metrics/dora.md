# DORA Metrics

Track per release/deployment:

| Metric | Definition | Target |
|---|---|---|
| Deployment frequency | successful deployments per week | ≥ 2/week |
| Lead time for changes | commit → production | < 1 day |
| Change failure rate | deployments requiring rollback/hotfix | < 15% |
| Mean time to restore | incident start → service restored | < 1 hour |

Source data: CI runs, deployment records, incident tickets. Keep the raw exports
with release evidence so trends are reproducible.
