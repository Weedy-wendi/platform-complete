-- MCP database accounts.
-- Replace <secret> before running. The MCP process uses two DSNs:
--   MCP_DB_DSN     -> pingce_mcp_ro (read-only business queries, read replica)
--   MCP_AUDIT_DSN  -> pingce_mcp_audit (INSERT-only audit writes, primary)

CREATE USER IF NOT EXISTS 'pingce_mcp_ro'@'%' IDENTIFIED BY '<secret>';
GRANT SELECT ON pingce.* TO 'pingce_mcp_ro'@'%';

CREATE USER IF NOT EXISTS 'pingce_mcp_audit'@'%' IDENTIFIED BY '<secret>';
GRANT INSERT ON pingce.mcp_tool_call TO 'pingce_mcp_audit'@'%';

-- Do not grant UPDATE, DELETE, CREATE, ALTER, DROP to either account.
-- Verification: run the statements below as pingce_mcp_ro; all must fail.
--   INSERT INTO dataset (name) VALUES ('x');
--   UPDATE dataset SET name = 'x' WHERE id = 1;
--   DELETE FROM dataset WHERE id = 1;
--   CREATE TABLE t (id INT);
--   DROP TABLE dataset;
