#requires -Version 5.1
<#
.SYNOPSIS
    Build the backend image and verify the contract file + HTTP health endpoint.
#>
param(
    [switch]$SkipBuild,
    [string]$Image = "pingce-mcp:smoke",
    [int]$Port = 18766
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ContainerName = "pingce-mcp-smoke"

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

try {
    $docker = Invoke-Native { docker info }
    if ($docker.ExitCode -ne 0) {
        throw "Docker daemon is not reachable: $($docker.Output)"
    }

    if (-not $SkipBuild) {
        Write-Host "Building $Image ..." -ForegroundColor Cyan
        $build = Invoke-Native {
            docker build -t $Image -f backend/Dockerfile .
        }
        if ($build.ExitCode -ne 0) {
            throw "docker build failed: $($build.Output)"
        }
    }

    Write-Host "Verifying contract inside the image ..." -ForegroundColor Cyan
    $contract = Invoke-Native {
        docker run --rm $Image python -c "from pathlib import Path; from app.mcp.registry import ToolRegistry; p=Path('/app/contracts/tools.yaml'); r=ToolRegistry.from_contract(p); print(len(r.tool_names))"
    }
    if ($contract.ExitCode -ne 0 -or $contract.Output.Trim() -ne "10") {
        throw "Contract verification failed: $($contract.Output)"
    }

    Write-Host "Starting container ..." -ForegroundColor Cyan
    Invoke-Native { docker rm -f $ContainerName } | Out-Null
    $run = Invoke-Native {
        docker run -d --name $ContainerName -p "${Port}:8765" `
            -e PINGCE_MCP_DNS_REBINDING_PROTECTION=false `
            $Image
    }
    if ($run.ExitCode -ne 0) {
        throw "docker run failed: $($run.Output)"
    }

    Wait-Http "http://127.0.0.1:$Port/healthz"
    Write-Host "PASS: container healthy on port $Port; contract contains 10 tools." -ForegroundColor Green
} finally {
    Invoke-Native { docker rm -f $ContainerName } | Out-Null
}
