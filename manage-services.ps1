$ErrorActionPreference = "Stop"

function Write-Log {
    param([string]$Level, [string]$Message)
    $line = "[{0}] [{1}] {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Level, $Message
    Add-Content -Path $script:LogFile -Value $line -Encoding UTF8
}

function Assert-Admin {
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-Host "[ERROR] Administrator permission is required."
        Write-Host "[HINT] Right-click manage-services.bat and select 'Run as administrator'."
        Write-Log "ERROR" "Admin permission required"
        exit 1
    }
}

function Resolve-Paths {
    $script:ProjectDir = (Resolve-Path $PSScriptRoot).Path
    $script:RepoDir = (Resolve-Path (Join-Path $script:ProjectDir "..")).Path
    $script:Python = Join-Path $script:RepoDir ".venv\Scripts\python.exe"
    $asciiProject = "C:\AGM_BILLING"

    if (-not (Test-Path $asciiProject)) {
        try {
            cmd /c "mklink /J `"$asciiProject`" `"$script:ProjectDir`"" | Out-Null
        } catch {
            # Fallback to original path if junction creation fails.
        }
    }

    $script:ServiceProjectDir = if (Test-Path $asciiProject) { $asciiProject } else { $script:ProjectDir }
    $script:FrontendServerScript = Join-Path $script:ServiceProjectDir "scripts\serve_frontend.py"
    $script:ServiceFrontendDist = Join-Path $script:ServiceProjectDir "web\dist"
    $script:ServiceLogDir = Join-Path $script:ServiceProjectDir "logs"
    if (-not (Test-Path $script:ServiceLogDir)) {
        New-Item -ItemType Directory -Path $script:ServiceLogDir -Force | Out-Null
    }
}

function Ensure-Prerequisites {
    if (-not (Test-Path $script:Nssm)) {
        Write-Host "[ERROR] nssm.exe not found:`n$script:Nssm"
        Write-Log "ERROR" "nssm.exe not found: $script:Nssm"
        exit 1
    }
    if (-not (Test-Path $script:Python)) {
        Write-Host "[ERROR] Python not found: $script:Python"
        Write-Log "ERROR" "Python not found: $script:Python"
        exit 1
    }
    if (-not (Test-Path $script:FrontendServerScript)) {
        Write-Host "[ERROR] Frontend server script not found: $script:FrontendServerScript"
        Write-Log "ERROR" "Frontend server script not found: $script:FrontendServerScript"
        exit 1
    }
    if (-not (Test-Path $script:ServiceFrontendDist)) {
        Write-Host "[ERROR] Frontend build output not found: $script:ServiceFrontendDist"
        Write-Log "ERROR" "Frontend build output not found: $script:ServiceFrontendDist"
        exit 1
    }
}

function Invoke-Nssm {
    param(
        [Parameter(Mandatory = $true)][string]$Action,
        [Parameter(Mandatory = $true)][string]$Service,
        [string]$Extra
    )

    if ([string]::IsNullOrWhiteSpace($Extra)) {
        & $script:Nssm $Action $Service
    } else {
        & $script:Nssm $Action $Service $Extra
    }
    $rc = $LASTEXITCODE
    if ($rc -eq 0) {
        Write-Host "[OK] nssm $Action $Service"
        Write-Log "INFO" "nssm $Action $Service success"
    } else {
        Write-Host "[ERROR] nssm $Action $Service failed (errorlevel=$rc)."
        Write-Log "ERROR" "nssm $Action $Service failed rc=$rc"
    }
    return $rc
}

function Ensure-Service {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$App,
        [Parameter(Mandatory = $true)][string]$Params,
        [Parameter(Mandatory = $true)][string]$AppDir,
        [Parameter(Mandatory = $true)][string]$LogFile
    )

    sc.exe query $Name *> $null
    if ($LASTEXITCODE -ne 0) {
        & $script:Nssm install $Name $App $Params | Out-Null
    }

    & $script:Nssm set $Name Application $App | Out-Null
    & $script:Nssm set $Name AppParameters $Params | Out-Null
    & $script:Nssm set $Name AppDirectory $AppDir | Out-Null
    & $script:Nssm set $Name AppStdout $LogFile | Out-Null
    & $script:Nssm set $Name AppStderr $LogFile | Out-Null
    Write-Log "INFO" "Service $Name config synced"
}

function Sync-ServiceConfigs {
    Ensure-Service -Name "billing-backend" -App $script:Python -Params "-m uvicorn api.main:app --host 0.0.0.0 --port 8000" -AppDir $script:ServiceProjectDir -LogFile (Join-Path $script:ServiceLogDir "backend.log")
    Ensure-Service -Name "billing-frontend" -App $script:Python -Params "scripts\serve_frontend.py --host 0.0.0.0 --port 5173 --dir web\dist" -AppDir $script:ServiceProjectDir -LogFile (Join-Path $script:ServiceLogDir "frontend.log")
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

function Wait-Healthy {
    Write-Host "[INFO] Waiting for backend/frontend health..."
    for ($i = 1; $i -le 30; $i++) {
        $backendOk = Test-HttpOk $script:BackendUrl
        $frontendOk = Test-HttpOk $script:FrontendUrl
        if ($backendOk -and $frontendOk) {
            Write-Host "[OK] Services are ready."
            Write-Log "INFO" "Health check ready"
            return
        }
        Start-Sleep -Seconds 1
    }
    Write-Host "[WARN] Services not fully ready after 30 checks."
    if (-not (Test-HttpOk $script:BackendUrl)) {
        Write-Host "[WARN] Backend check failed: $script:BackendUrl"
    }
    if (-not (Test-HttpOk $script:FrontendUrl)) {
        Write-Host "[WARN] Frontend check failed: $script:FrontendUrl"
    }
    Write-Log "WARN" "Health check timeout"
}

function Show-Menu {
    Clear-Host
    Write-Host "========================================"
    Write-Host "        Billing Service Manager"
    Write-Host "========================================"
    Write-Host " [1] Show service status"
    Write-Host " [2] Start all services"
    Write-Host " [3] Stop all services"
    Write-Host " [4] Restart all services"
    Write-Host " [5] Remove all services"
    Write-Host " [Q] Quit"
    Write-Host "========================================"
}

$script:Nssm = "C:\Users\norah\AppData\Local\Microsoft\WinGet\Packages\NSSM.NSSM_Microsoft.Winget.Source_8wekyb3d8bbwe\nssm-2.24-101-g897c7ad\win64\nssm.exe"
$script:BackendUrl = "http://127.0.0.1:8000/api/health"
$script:FrontendUrl = "http://127.0.0.1:5173"
$logDir = Join-Path $PSScriptRoot "logs"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}
$script:LogFile = Join-Path $logDir "manage-services.log"

Assert-Admin
Resolve-Paths
Ensure-Prerequisites
Write-Log "INFO" "Service project dir=$script:ServiceProjectDir"
Sync-ServiceConfigs

while ($true) {
    Show-Menu
    $choice = (Read-Host "Select action [1-5,Q]").Trim().ToUpperInvariant()
    Write-Log "INFO" "Menu pick=$choice"
    switch ($choice) {
        "1" {
            Write-Host "--- billing-backend ---"
            Invoke-Nssm -Action "status" -Service "billing-backend" | Out-Null
            Write-Host "--- billing-frontend ---"
            Invoke-Nssm -Action "status" -Service "billing-frontend" | Out-Null
            Write-Host "--- health ---"
            if (Test-HttpOk $script:BackendUrl) { Write-Host "[OK] backend health check passed" } else { Write-Host "[WARN] backend health check failed" }
            if (Test-HttpOk $script:FrontendUrl) { Write-Host "[OK] frontend check passed" } else { Write-Host "[WARN] frontend check failed" }
            Pause
        }
        "2" {
            Sync-ServiceConfigs
            Invoke-Nssm -Action "start" -Service "billing-backend" | Out-Null
            Invoke-Nssm -Action "start" -Service "billing-frontend" | Out-Null
            Wait-Healthy
            Pause
        }
        "3" {
            Invoke-Nssm -Action "stop" -Service "billing-backend" | Out-Null
            Invoke-Nssm -Action "stop" -Service "billing-frontend" | Out-Null
            Write-Host "[INFO] Stop command sent."
            Pause
        }
        "4" {
            Write-Host "[INFO] Restarting services (stop -> start)..."
            Write-Log "INFO" "Restart requested"
            Sync-ServiceConfigs
            Invoke-Nssm -Action "stop" -Service "billing-backend" | Out-Null
            Invoke-Nssm -Action "stop" -Service "billing-frontend" | Out-Null
            Start-Sleep -Seconds 2
            Invoke-Nssm -Action "start" -Service "billing-backend" | Out-Null
            Invoke-Nssm -Action "start" -Service "billing-frontend" | Out-Null
            Wait-Healthy
            Pause
        }
        "5" {
            Write-Host "[WARN] Removing services..."
            Invoke-Nssm -Action "stop" -Service "billing-backend" | Out-Null
            Invoke-Nssm -Action "remove" -Service "billing-backend" -Extra "confirm" | Out-Null
            Invoke-Nssm -Action "stop" -Service "billing-frontend" | Out-Null
            Invoke-Nssm -Action "remove" -Service "billing-frontend" -Extra "confirm" | Out-Null
            Write-Host "[INFO] Remove command sent."
            Pause
        }
        "Q" { break }
        default {
            Write-Host "[WARN] Invalid input: $choice"
            Start-Sleep -Seconds 1
        }
    }
}
