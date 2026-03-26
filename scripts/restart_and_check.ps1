# One-command restart + health check for billing services.
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\restart_and_check.ps1

param(
    [string]$BackendService = "billing-backend",
    [string]$FrontendService = "billing-frontend",
    [string]$BackendHealthUrl = "http://127.0.0.1:8000/api/health",
    [string]$FrontendHealthUrl = "http://127.0.0.1:5173",
    [int]$TimeoutSec = 45,
    [switch]$SkipAdminCheck,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Write-Err {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Assert-Admin {
    if ($SkipAdminCheck) {
        Write-Warn "Skip admin check enabled."
        return
    }
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Please run this script as Administrator."
    }
}

function Service-Exists {
    param([string]$Name)
    sc.exe query $Name *> $null
    return ($LASTEXITCODE -eq 0)
}

function Get-ServiceStatusText {
    param([string]$Name)
    try {
        return (Get-Service -Name $Name -ErrorAction Stop).Status.ToString()
    } catch {
        return "Unknown"
    }
}

function Stop-ServiceSafe {
    param([string]$Name)
    if ($DryRun) {
        Write-Info "DRY RUN: stop $Name"
        return
    }

    $status = Get-ServiceStatusText -Name $Name
    if ($status -eq "Stopped") {
        Write-Info "$Name is already Stopped."
        return
    }
    Write-Info "Stopping service: $Name"
    sc.exe stop $Name | Out-Null

    $deadline = (Get-Date).AddSeconds(20)
    while ((Get-Date) -lt $deadline) {
        if ((Get-ServiceStatusText -Name $Name) -eq "Stopped") {
            Write-Ok "$Name stopped."
            return
        }
        Start-Sleep -Seconds 1
    }
    Write-Warn "$Name stop timeout. Continue."
}

function Start-ServiceSafe {
    param([string]$Name)
    if ($DryRun) {
        Write-Info "DRY RUN: start $Name"
        return
    }

    Write-Info "Starting service: $Name"
    sc.exe start $Name | Out-Null

    $deadline = (Get-Date).AddSeconds(20)
    while ((Get-Date) -lt $deadline) {
        if ((Get-ServiceStatusText -Name $Name) -eq "Running") {
            Write-Ok "$Name started."
            return
        }
        Start-Sleep -Seconds 1
    }
    throw "$Name start timeout."
}

function Test-HttpOk {
    param([string]$Url)
    try {
        $resp = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2
        return ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 400)
    } catch {
        return $false
    }
}

function Wait-HealthReady {
    param(
        [string]$BackendUrl,
        [string]$FrontendUrl,
        [int]$Timeout
    )
    if ($DryRun) {
        Write-Info "DRY RUN: health check backend=$BackendUrl frontend=$FrontendUrl"
        return $true
    }

    Write-Info "Running health checks (timeout ${Timeout}s)..."
    $deadline = (Get-Date).AddSeconds($Timeout)
    $backendOk = $false
    $frontendOk = $false

    while ((Get-Date) -lt $deadline) {
        if (-not $backendOk) {
            $backendOk = Test-HttpOk -Url $BackendUrl
        }
        if (-not $frontendOk) {
            $frontendOk = Test-HttpOk -Url $FrontendUrl
        }
        if ($backendOk -and $frontendOk) {
            Write-Ok "Health checks passed: backend and frontend are reachable."
            return $true
        }
        Start-Sleep -Seconds 1
    }
    Write-Warn "Health check timeout. backend_ok=$backendOk frontend_ok=$frontendOk"
    return $false
}

function Resolve-LogPath {
    param([string]$FileName)
    $candidates = @(
        "C:\AGM_BILLING\logs\$FileName",
        (Join-Path (Join-Path $PSScriptRoot "..") "logs\$FileName")
    )
    foreach ($path in $candidates) {
        if (Test-Path $path) {
            return (Resolve-Path $path).Path
        }
    }
    return $null
}

function Show-LogTail {
    param(
        [string]$Title,
        [string]$Path
    )
    if (-not $Path) {
        Write-Warn "$Title log not found."
        return
    }
    Write-Host ""
    Write-Host "----- $Title (tail 40) -----" -ForegroundColor DarkYellow
    try {
        Get-Content -Path $Path -Tail 40
    } catch {
        Write-Warn "Failed to read log: $Path"
    }
}

try {
    Assert-Admin
    Write-Info "Restarting services: $BackendService / $FrontendService"

    foreach ($svc in @($BackendService, $FrontendService)) {
        if (-not (Service-Exists -Name $svc)) {
            throw "Service $svc does not exist. Run .\install-services.bat first."
        }
    }

    Stop-ServiceSafe -Name $BackendService
    Stop-ServiceSafe -Name $FrontendService
    Start-Sleep -Seconds 2

    Start-ServiceSafe -Name $BackendService
    Start-ServiceSafe -Name $FrontendService

    if (-not (Wait-HealthReady -BackendUrl $BackendHealthUrl -FrontendUrl $FrontendHealthUrl -Timeout $TimeoutSec)) {
        $backendLog = Resolve-LogPath -FileName "backend.log"
        $frontendLog = Resolve-LogPath -FileName "frontend.log"
        Show-LogTail -Title "backend.log" -Path $backendLog
        Show-LogTail -Title "frontend.log" -Path $frontendLog
        exit 1
    }

    Write-Host ""
    Write-Ok "Restart completed."
    Write-Host "Frontend: $FrontendHealthUrl"
    Write-Host "Backend health: $BackendHealthUrl"
    exit 0
} catch {
    Write-Err $_.Exception.Message
    exit 1
}
