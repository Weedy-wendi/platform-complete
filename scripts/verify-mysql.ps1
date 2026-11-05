#requires -Version 5.1
<#
.SYNOPSIS
    Verify MySQL migrations, restricted grants, and the MCP server end-to-end.

.DESCRIPTION
    - Stores MySQL data on a non-C: bind mount (default: <repo>\.local\mysql-verify).
    - Starts a disposable MySQL 8.0 container on a non-default port.
    - Runs alembic upgrade -> downgrade -> upgrade.
    - Creates pingce_mcp_ro / pingce_mcp_audit and verifies SELECT/INSERT-only behavior.
    - Issues an API key via the root account, starts the MCP server with restricted DSNs,
      calls list_projects, and verifies an audit row was written.

.PARAMETER DataRoot
    Host directory for MySQL data. Must not be on C:.

.PARAMETER Port
    Host port for MySQL. Default 13306.

.PARAMETER KeepContainer
    Leave the MySQL container running for inspection.

.PARAMETER CleanData
    Remove the data directory after the run.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/verify-mysql.ps1
#>
param(
    [string]$DataRoot = "",
    [int]$Port = 13306,
    [string]$ContainerName = "pingce-mysql-verify",
    [switch]$KeepContainer,
    [switch]$CleanData
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Backend = Join-Path $RepoRoot "backend"
$Contract = Join-Path $RepoRoot "specs\001-mcp-server\contracts\tools.yaml"

if ([string]::IsNullOrWhiteSpace($DataRoot)) {
    $DataRoot = Join-Path $RepoRoot ".local\mysql-verify"
}
$DataRoot = [System.IO.Path]::GetFullPath($DataRoot)
if ($DataRoot -match '^[Cc]:') {
    throw "Refusing to store MySQL data on C:. Choose a path such as E:\PingceData\mysql-verify."
}
if ($KeepContainer -and $CleanData) {
    throw "Cannot combine -KeepContainer with -CleanData; keep the data if the container is kept."
}

$RootPassword = "verify-root-pass"
$RoPassword = "verify-ro-pass"
$AuditPassword = "verify-audit-pass"
$McpPort = 18765
$McpBase = "http://127.0.0.1:$McpPort"

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Invoke-Native {
    param([Parameter(Mandatory = $true)][scriptblock]$Command)
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & $Command 2>&1
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $old
    }
    return [pscustomobject]@{
        Output = (($output | Out-String).Trim())
        ExitCode = $code
    }
}

function Assert-Docker {
    $result = Invoke-Native { docker info }
    if ($result.ExitCode -ne 0) {
        throw "Docker daemon is not reachable. Start Docker Desktop and retry. $($result.Output)"
    }
}

function Wait-MySql {
    param([int]$Attempts = 60)
    for ($i = 1; $i -le $Attempts; $i++) {
        $result = Invoke-Native {
            docker exec $ContainerName mysqladmin ping -h 127.0.0.1 -uroot "-p$RootPassword"
        }
        if ($result.ExitCode -eq 0) { return }
        Start-Sleep -Seconds 2
    }
    $logs = Invoke-Native { docker logs $ContainerName }
    throw "MySQL did not become ready in time. Last logs:`n$($logs.Output)"
}

function Invoke-MySql {
    param(
        [Parameter(Mandatory = $true)][string]$Sql,
        [string]$User = "root",
        [string]$Password = $RootPassword,
        [string]$Database = "pingce"
    )
    $result = Invoke-Native {
        $Sql | docker exec -i $ContainerName mysql -N -B "-u$User" "-p$Password" $Database 2>$null
    }
    if ($result.ExitCode -ne 0) {
        throw "MySQL command failed for ${User}: $($result.Output)"
    }
    return $result.Output
}

function Assert-MySqlDenied {
    param(
        [Parameter(Mandatory = $true)][string]$Sql,
        [Parameter(Mandatory = $true)][string]$User,
        [Parameter(Mandatory = $true)][string]$Password,
        [string]$Database = "pingce"
    )
    $result = Invoke-Native {
        $Sql | docker exec -i $ContainerName mysql "-u$User" "-p$Password" $Database
    }
    if ($result.ExitCode -eq 0) {
        throw "Expected access denial for ${User}, but the statement succeeded: $Sql"
    }
    if ($result.Output -notmatch "denied|Access denied") {
        throw "Expected access denial for ${User}, got: $($result.Output)"
    }
}

function Wait-Http {
    param([string]$Url, [int]$Attempts = 40)
    for ($i = 1; $i -le $Attempts; $i++) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) { return }
        } catch {
            # keep waiting
        }
        Start-Sleep -Milliseconds 500
    }
    throw "HTTP endpoint did not become ready: $Url"
}

$oldEnv = @{
    PINGCE_MCP_DB_DSN = $env:PINGCE_MCP_DB_DSN
    PINGCE_MCP_AUDIT_DSN = $env:PINGCE_MCP_AUDIT_DSN
    PINGCE_MCP_REDIS_URL = $env:PINGCE_MCP_REDIS_URL
    PINGCE_MCP_DNS_REBINDING_PROTECTION = $env:PINGCE_MCP_DNS_REBINDING_PROTECTION
    PINGCE_MCP_API_KEY_PEPPER = $env:PINGCE_MCP_API_KEY_PEPPER
    PINGCE_MCP_CURSOR_SECRET = $env:PINGCE_MCP_CURSOR_SECRET
    PINGCE_MCP_CONTRACTS_PATH = $env:PINGCE_MCP_CONTRACTS_PATH
    PINGCE_ENV = $env:PINGCE_ENV
}
$serverProcess = $null

try {
    Assert-Docker
    Write-Step "Data directory: $DataRoot"
    New-Item -ItemType Directory -Path $DataRoot -Force | Out-Null

    Write-Step "Removing old container (if any)"
    Invoke-Native { docker rm -f $ContainerName } | Out-Null

    if ($CleanData -and (Test-Path $DataRoot)) {
        Get-ChildItem -LiteralPath $DataRoot -Force | Remove-Item -Recurse -Force
    }

    Write-Step "Pulling mysql:8.0 (if needed)"
    $image = Invoke-Native { docker image ls -q mysql:8.0 }
    if (-not $image.Output) {
        $pull = Invoke-Native { docker pull mysql:8.0 }
        if ($pull.ExitCode -ne 0) { throw "docker pull failed: $($pull.Output)" }
    }

    Write-Step "Starting MySQL on host port $Port with bind mount on non-C:"
    $mount = "type=bind,source=$DataRoot,target=/var/lib/mysql"
    $run = Invoke-Native {
        docker run -d --name $ContainerName `
            --mount $mount `
            -p "${Port}:3306" `
            -e "MYSQL_ROOT_PASSWORD=$RootPassword" `
            -e "MYSQL_DATABASE=pingce" `
            mysql:8.0 `
            --character-set-server=utf8mb4 `
            --collation-server=utf8mb4_0900_ai_ci `
            --default-time-zone=+00:00 `
            --transaction-isolation=READ-COMMITTED
    }
    if ($run.ExitCode -ne 0) { throw "docker run failed: $($run.Output)" }

    Wait-MySql

    $rootDsn = "mysql+pymysql://root:$RootPassword@127.0.0.1:$Port/pingce?charset=utf8mb4"
    $env:PINGCE_MCP_DB_DSN = $rootDsn
    $env:PINGCE_ENV = "verify"
    $env:PINGCE_MCP_API_KEY_PEPPER = "verify-pepper"
    $env:PINGCE_MCP_CURSOR_SECRET = "verify-cursor"
    $env:PINGCE_MCP_CONTRACTS_PATH = $Contract

    Write-Step "Alembic upgrade head"
    Push-Location $Backend
    try {
        $up = Invoke-Native { python -m alembic upgrade head }
        if ($up.ExitCode -ne 0) { throw "alembic upgrade failed: $($up.Output)" }

        Write-Step "Alembic downgrade -1"
        $down = Invoke-Native { python -m alembic downgrade -1 }
        if ($down.ExitCode -ne 0) { throw "alembic downgrade failed: $($down.Output)" }

        Write-Step "Alembic upgrade head (round trip)"
        $up2 = Invoke-Native { python -m alembic upgrade head }
        if ($up2.ExitCode -ne 0) { throw "alembic re-upgrade failed: $($up2.Output)" }
    } finally {
        Pop-Location
    }

    Write-Step "Verifying tables and partitions"
    $tables = Invoke-MySql "SHOW TABLES;"
    if ($tables -notmatch "api_key" -or $tables -notmatch "mcp_tool_call") {
        throw "Expected tables are missing: $tables"
    }
    $partitions = Invoke-MySql "SELECT PARTITION_NAME FROM INFORMATION_SCHEMA.PARTITIONS WHERE TABLE_SCHEMA='pingce' AND TABLE_NAME='mcp_tool_call' ORDER BY PARTITION_NAME;"
    if ($partitions -notmatch "p202611" -or $partitions -notmatch "pmax") {
        throw "Expected partitions are missing: $partitions"
    }

    Write-Step "Creating restricted accounts"
    $grantSql = @"
DROP USER IF EXISTS 'pingce_mcp_ro'@'%';
DROP USER IF EXISTS 'pingce_mcp_audit'@'%';
CREATE USER 'pingce_mcp_ro'@'%' IDENTIFIED BY '$RoPassword';
GRANT SELECT ON pingce.* TO 'pingce_mcp_ro'@'%';
CREATE USER 'pingce_mcp_audit'@'%' IDENTIFIED BY '$AuditPassword';
GRANT INSERT ON pingce.mcp_tool_call TO 'pingce_mcp_audit'@'%';
FLUSH PRIVILEGES;
"@
    Invoke-MySql $grantSql | Out-Null

    Write-Step "Verifying read-only account"
    Invoke-MySql "SELECT COUNT(*) FROM api_key;" -User "pingce_mcp_ro" -Password $RoPassword | Out-Null
    Assert-MySqlDenied "UPDATE api_key SET name='x' WHERE id=1;" -User "pingce_mcp_ro" -Password $RoPassword
    Assert-MySqlDenied "DELETE FROM api_key WHERE id=1;" -User "pingce_mcp_ro" -Password $RoPassword
    Assert-MySqlDenied "CREATE TABLE verify_ro_should_fail (id INT);" -User "pingce_mcp_ro" -Password $RoPassword
    Assert-MySqlDenied "DROP TABLE api_key;" -User "pingce_mcp_ro" -Password $RoPassword

    Write-Step "Verifying audit account"
    Invoke-MySql @"
INSERT INTO mcp_tool_call
  (tenant_id, api_key_id, tool_name, tool_version, status, latency_ms, result_bytes, trace_id, created_at)
VALUES
  ('tenant-verify', 1, 'verify', '1.0.0', 'ok', 1, 1, 'verify-trace', UTC_TIMESTAMP(6));
"@ -User "pingce_mcp_audit" -Password $AuditPassword | Out-Null
    Assert-MySqlDenied "SELECT COUNT(*) FROM mcp_tool_call;" -User "pingce_mcp_audit" -Password $AuditPassword
    Assert-MySqlDenied "UPDATE mcp_tool_call SET status='x';" -User "pingce_mcp_audit" -Password $AuditPassword
    Assert-MySqlDenied "DELETE FROM mcp_tool_call;" -User "pingce_mcp_audit" -Password $AuditPassword

    Write-Step "Issuing an API key through the real database"
    $issueScript = Join-Path $DataRoot "issue_key.py"
    @'
from app.core.config import Settings
from app.core.db import create_engine_from_dsn, make_session_factory
from app.modules.identity.public import ALLOWED_SCOPES, ApiKeyService, SqlApiKeyStore

settings = Settings()
engine = create_engine_from_dsn(settings.mcp_db_dsn)
service = ApiKeyService(
    SqlApiKeyStore(make_session_factory(engine)),
    pepper=settings.mcp_api_key_pepper.get_secret_value(),
    key_env=settings.env,
)
key = service.issue(tenant_id="tenant-verify", name="verify", scopes=ALLOWED_SCOPES)
print(key.raw_key)
'@ | Set-Content -LiteralPath $issueScript -Encoding UTF8
    $issue = Invoke-Native { python $issueScript }
    if ($issue.ExitCode -ne 0) { throw "API key issue failed: $($issue.Output)" }
    $rawKey = $issue.Output.Trim()
    if (-not $rawKey.StartsWith("pk_")) {
        throw "Failed to issue an API key: $rawKey"
    }

    Write-Step "Starting MCP server with restricted DSNs"
    $env:PINGCE_MCP_DB_DSN = "mysql+pymysql://pingce_mcp_ro:$RoPassword@127.0.0.1:$Port/pingce?charset=utf8mb4"
    $env:PINGCE_MCP_AUDIT_DSN = "mysql+pymysql://pingce_mcp_audit:$AuditPassword@127.0.0.1:$Port/pingce?charset=utf8mb4"
    $env:PINGCE_MCP_REDIS_URL = "redis://127.0.0.1:6399/0"
    $env:PINGCE_MCP_DNS_REBINDING_PROTECTION = "false"

    $logPath = Join-Path $DataRoot "mcp-server.log"
    $errPath = Join-Path $DataRoot "mcp-server.err.log"
    $serverProcess = Start-Process -FilePath "python" `
        -ArgumentList "-m", "app.cli.main", "mcp", "serve", "--http", "--host", "127.0.0.1", "--port", "$McpPort" `
        -WorkingDirectory $Backend `
        -PassThru `
        -RedirectStandardOutput $logPath `
        -RedirectStandardError $errPath

    Wait-Http "$McpBase/healthz"

    $headers = @{
        Authorization = "Bearer $rawKey"
        Accept = "application/json, text/event-stream"
        "Content-Type" = "application/json"
    }
    $initBody = @{
        jsonrpc = "2.0"
        id = 1
        method = "initialize"
        params = @{
            protocolVersion = "2025-06-18"
            capabilities = @{}
            clientInfo = @{ name = "verify-mysql"; version = "0" }
        }
    } | ConvertTo-Json -Depth 10
    $init = Invoke-RestMethod -Method Post -Uri "$McpBase/mcp" -Headers $headers -Body $initBody
    if ($init.result.protocolVersion -ne "2025-06-18") {
        throw "Unexpected initialize response: $($init | ConvertTo-Json -Depth 10)"
    }

    $listBody = @{ jsonrpc = "2.0"; id = 2; method = "tools/list"; params = @{} } | ConvertTo-Json -Depth 10
    $tools = Invoke-RestMethod -Method Post -Uri "$McpBase/mcp" -Headers $headers -Body $listBody
    if ($tools.result.tools.Count -ne 10) {
        throw "Expected 10 tools, got $($tools.result.tools.Count)"
    }

    $callBody = @{
        jsonrpc = "2.0"
        id = 3
        method = "tools/call"
        params = @{ name = "list_projects"; arguments = @{} }
    } | ConvertTo-Json -Depth 10
    $call = Invoke-RestMethod -Method Post -Uri "$McpBase/mcp" -Headers $headers -Body $callBody
    if ($call.result.isError) {
        throw "list_projects returned an error: $($call | ConvertTo-Json -Depth 10)"
    }

    Write-Step "Verifying audit row written by the MCP server"
    $auditCountText = (Invoke-MySql "SELECT COUNT(*) FROM mcp_tool_call WHERE tenant_id='tenant-verify' AND tool_name='list_projects';").Trim()
    if ($auditCountText -notmatch '^\d+$') {
        throw "Unexpected audit count output: $auditCountText"
    }
    $auditCount = [int]$auditCountText
    if ($auditCount -lt 1) {
        throw "Expected an audit row for list_projects, got count=$auditCount"
    }

    Write-Step "PASS"
    Write-Host "MySQL data: $DataRoot"
    Write-Host "MySQL port: $Port"
    Write-Host "MCP port:   $McpPort"
    Write-Host "Tables:     api_key, mcp_tool_call"
    Write-Host "Accounts:   pingce_mcp_ro (SELECT), pingce_mcp_audit (INSERT)"
    Write-Host "Audit rows: $auditCount"
} finally {
    if ($serverProcess -and -not $serverProcess.HasExited) {
        Stop-Process -Id $serverProcess.Id -Force -ErrorAction SilentlyContinue
    }
    if (-not $KeepContainer) {
        Invoke-Native { docker rm -f $ContainerName } | Out-Null
    }
    if ($CleanData -and (Test-Path $DataRoot)) {
        Remove-Item -LiteralPath $DataRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
    foreach ($name in $oldEnv.Keys) {
        if ($null -eq $oldEnv[$name]) {
            Remove-Item "Env:$name" -ErrorAction SilentlyContinue
        } else {
            Set-Item "Env:$name" $oldEnv[$name]
        }
    }
}
