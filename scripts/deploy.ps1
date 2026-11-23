#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Version,

    [Parameter(Mandatory = $true)]
    [string]$EnvFile,

    [Parameter(Mandatory = $true)]
    [string]$ComposeFile,

    [string]$ProjectName = "multiregistrator",

    [int]$BackupRetention = 14
)

$ErrorActionPreference = "Stop"
$Version = $Version.Trim()
if ($Version -match '^v\d+\.\d+\.\d+$') {
    $Version = $Version.Substring(1)
}
if (-not $Version) {
    throw "Version is required."
}

function Read-DotEnv {
    param([string]$Path)

    $values = @{}
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Env file not found: $Path"
    }
    foreach ($line in Get-Content -LiteralPath $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) {
            continue
        }
        $index = $trimmed.IndexOf("=")
        if ($index -lt 1) {
            continue
        }
        $key = $trimmed.Substring(0, $index).Trim()
        $value = $trimmed.Substring($index + 1).Trim()
        if ($value.Length -ge 2) {
            $quotedDouble = $value.StartsWith('"') -and $value.EndsWith('"')
            $quotedSingle = $value.StartsWith("'") -and $value.EndsWith("'")
            if ($quotedDouble -or $quotedSingle) {
                $value = $value.Substring(1, $value.Length - 2)
            }
        }
        $values[$key] = $value
    }
    return $values
}

function Invoke-Compose {
    param([string[]]$ComposeArgs)

    & docker compose -f $ComposeFile --env-file $EnvFile -p $ProjectName @ComposeArgs
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose $($ComposeArgs -join ' ') failed with exit code $LASTEXITCODE"
    }
}

if (-not (Test-Path -LiteralPath $ComposeFile)) {
    throw "Compose file not found: $ComposeFile"
}
$ComposeFile = (Resolve-Path -LiteralPath $ComposeFile).Path
$EnvFile = (Resolve-Path -LiteralPath $EnvFile).Path
$root = Split-Path -Parent $ComposeFile
$backupDir = Join-Path $root "backups"
$stateFile = Join-Path $root ".deployed-version.$ProjectName"
Set-Location -LiteralPath $root
$envValues = Read-DotEnv -Path $EnvFile

$dbUser = $envValues["POSTGRES_USER"]
$dbName = $envValues["POSTGRES_DB"]
if (-not $dbUser -or -not $dbName) {
    throw "POSTGRES_USER and POSTGRES_DB must be set in $EnvFile"
}

& docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker Desktop is not running. Start it and retry."
}
$osType = (& docker info --format '{{.OSType}}').Trim()
if ($osType -ne "linux") {
    throw "Docker Desktop must use Linux containers (current OSType: $osType)."
}

$previousVersion = if (Test-Path -LiteralPath $stateFile) {
    (Get-Content -LiteralPath $stateFile -Raw).Trim()
} else {
    $null
}

$running = @(& docker compose -f $ComposeFile --env-file $EnvFile -p $ProjectName ps --status running --services)
if (-not ($running -contains "db") -and $previousVersion) {
    throw "Database container is not running but a previous deployment exists; refusing to deploy without a backup."
}
if ($running -contains "db") {
    New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $backupFile = Join-Path $backupDir "db_$stamp.dump"
    $remoteBackup = "/tmp/mrw_backup_$stamp.dump"

    Write-Host "Backing up database to $backupFile"
    Invoke-Compose @("exec", "-T", "db", "pg_dump", "-U", $dbUser, "-Fc", "-f", $remoteBackup, $dbName)
    Invoke-Compose @("cp", "db:$remoteBackup", $backupFile)
    Invoke-Compose @("exec", "-T", "db", "rm", "-f", $remoteBackup)

    Get-ChildItem -LiteralPath $backupDir -Filter "db_*.dump" |
        Sort-Object LastWriteTime -Descending |
        Select-Object -Skip $BackupRetention |
        Remove-Item -Force
} else {
    Write-Host "Database is not running; skipping backup (first deployment)."
}

$env:APP_VERSION = $Version
Write-Host "Pulling images for version $Version"
Invoke-Compose @("pull")

Write-Host "Starting stack (project: $ProjectName)"
Invoke-Compose @("up", "-d", "--remove-orphans")

$webPort = $envValues["WEB_PORT"]
if (-not $webPort) {
    $webPort = "8080"
}
$healthUrl = "http://127.0.0.1:$webPort/api/ready"
$healthy = $false
for ($attempt = 1; $attempt -le 60; $attempt++) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $healthUrl -TimeoutSec 3
        if ($response.StatusCode -eq 200) {
            $healthy = $true
            break
        }
    } catch {
        # The web container is still starting.
    }
    Start-Sleep -Seconds 2
}

$pollerRunning = $false
if ($healthy) {
    for ($attempt = 1; $attempt -le 30; $attempt++) {
        $services = @(& docker compose -f $ComposeFile --env-file $EnvFile -p $ProjectName ps --status running --services)
        if ($services -contains "poller") {
            $pollerRunning = $true
            break
        }
        Start-Sleep -Seconds 2
    }
}

$pollerHealthy = $false
if ($pollerRunning) {
    for ($attempt = 1; $attempt -le 60; $attempt++) {
        & docker compose -f $ComposeFile --env-file $EnvFile -p $ProjectName exec -T poller python manage.py poller_health --max-age 120 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $pollerHealthy = $true
            break
        }
        Start-Sleep -Seconds 2
    }
}

if (-not $healthy -or -not $pollerRunning -or -not $pollerHealthy) {
    Write-Host "Deployment health check failed. Recent logs:"
    & docker compose -f $ComposeFile --env-file $EnvFile -p $ProjectName logs --tail 200 web migrate poller
    if ($previousVersion) {
        Write-Host "Rolling back to $previousVersion"
        $env:APP_VERSION = $previousVersion
        & docker compose -f $ComposeFile --env-file $EnvFile -p $ProjectName up -d --remove-orphans
    }
    throw "Deployment of $Version failed (web healthy: $healthy, poller running: $pollerRunning, poller heartbeat: $pollerHealthy)."
}

Set-Content -LiteralPath $stateFile -Value $Version -Encoding ASCII
Write-Host "Deployed $Version to project $ProjectName."
