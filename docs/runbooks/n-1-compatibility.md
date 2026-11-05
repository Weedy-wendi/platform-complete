# N-1 Application Compatibility Matrix

Every schema change must keep the previous application version runnable during
a rolling deploy (expand → migrate → contract).

| Migration | N-1 safe? | Notes |
|---|---|---|
| 0001 api_key | yes | new table |
| 0002 mcp_tool_call | yes | new partitioned table |
| 0003 identity | yes | new tables only |
| 0004 audit_log | yes | new table |
| 0005 audit partitions | yes | PK widened; old app inserts id/created_at |
| 0006 artifact | yes | new table |
| 0007 catalog | yes | new tables + immutability trigger |
| 0008 jobs | yes | new tables + append-only trigger |
| 0009 model_gateway | yes | new tables |
| 0010 ingestion | yes | new tables |
| 0011 functional | yes | new tables |
| 0012 evaluation | yes | new tables |
| 0013 gate | yes | new tables |
| 0014 reporting | yes | new tables |
| 0015 ingestion_dlq | yes | new dead-letter table |
| 0016 convergence_gaps | yes | additive JSON/VARCHAR/FLOAT/INTEGER columns + dead-letter table |

Rule: destructive changes (drop/rename/narrow) need an explicit
`# destructive-approved` marker and a previous-version compatibility test.
