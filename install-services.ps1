# Billing service installer (run as Administrator)
$ErrorActionPreference = "Stop"

function Assert-Admin {
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-Host "[ERROR] Please run this script as Administrator." -ForegroundColor Red
        pause
        exit 1
    }
}

function Resolve-ProjectPaths {
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $projectDir = (Resolve-Path $scriptDir).Path
    $repoDir = (Resolve-Path (Join-Path $projectDir "..")).Path
    $python = Join-Path $repoDir ".venv\Scripts\python.exe"
    $asciiProject = "C:\AGM_BILLING"

    if (-not (Test-Path $asciiProject)) {
        cmd /c "mklink /J `"$asciiProject`" `"$projectDir`"" | Out-Null
    }

    $serviceProject = if (Test-Path $asciiProject) { $asciiProject } else { $projectDir }
    $serviceFrontend = Join-Path $serviceProject "web"
    $serviceLogs = Join-Path $serviceProject "logs"

    if (-not (Test-Path $serviceLogs)) {
        New-Item -ItemType Directory -Path $serviceLogs -Force | Out-Null
    }

    return @{
        ProjectDir = $projectDir
        ServiceProject = $serviceProject
        ServiceLogs = $serviceLogs
        Python = $python
        FrontendServerScript = (Join-Path $serviceProject "scripts\serve_frontend.py")
        FrontendDist = (Join-Path $serviceProject "web\dist")
    }
}

function Ensure-Service {
    param(
        [string]$Nssm,
        [string]$Name,
        [string]$App,
        [string]$Params,
        [string]$AppDir,
        [string]$LogPath
    )

    sc.exe query $Name *> $null
    if ($LASTEXITCODE -ne 0) {
        & $Nssm install $Name $App $Params | Out-Null
    }

    & $Nssm set $Name Application $App | Out-Null
    & $Nssm set $Name AppParameters $Params | Out-Null
    & $Nssm set $Name AppDirectory $AppDir | Out-Null
    & $Nssm set $Name AppStdout $LogPath | Out-Null
    & $Nssm set $Name AppStderr $LogPath | Out-Null
}

Assert-Admin

$nssm = "C:\Users\norah\AppData\Local\Microsoft\WinGet\Packages\NSSM.NSSM_Microsoft.Winget.Source_8wekyb3d8bbwe\nssm-2.24-101-g897c7ad\win64\nssm.exe"
if (-not (Test-Path $nssm)) {
    Write-Host "[ERROR] nssm.exe not found: $nssm" -ForegroundColor Red
    pause
    exit 1
}

$paths = Resolve-ProjectPaths
if (-not (Test-Path $paths.Python)) {
    Write-Host "[ERROR] Python not found: $($paths.Python)" -ForegroundColor Red
    pause
    exit 1
}
if (-not (Test-Path $paths.FrontendServerScript)) {
    Write-Host "[ERROR] Frontend server script not found: $($paths.FrontendServerScript)" -ForegroundColor Red
    pause
    exit 1
}
if (-not (Test-Path (Join-Path $paths.FrontendDist "index.html"))) {
    Write-Host "[ERROR] Frontend build output not found: $(Join-Path $paths.FrontendDist 'index.html')" -ForegroundColor Red
    pause
    exit 1
}

Write-Host "--- Sync billing-backend service ---" -ForegroundColor Cyan
Ensure-Service -Nssm $nssm -Name "billing-backend" -App $paths.Python -Params "-m uvicorn api.main:app --host 0.0.0.0 --port 8000" -AppDir $paths.ServiceProject -LogPath (Join-Path $paths.ServiceLogs "backend.log")

Write-Host "--- Sync billing-frontend service ---" -ForegroundColor Cyan
Ensure-Service -Nssm $nssm -Name "billing-frontend" -App $paths.Python -Params "scripts\serve_frontend.py --host 0.0.0.0 --port 5173 --dir web\dist" -AppDir $paths.ServiceProject -LogPath (Join-Path $paths.ServiceLogs "frontend.log")

Write-Host "--- Restart services ---" -ForegroundColor Yellow
& $nssm stop billing-backend | Out-Null
& $nssm stop billing-frontend | Out-Null
Start-Sleep -Seconds 2
& $nssm start billing-backend | Out-Null
& $nssm start billing-frontend | Out-Null

Write-Host ""
Write-Host "[OK] Services synced and restarted." -ForegroundColor Green
Write-Host "[INFO] Project path: $($paths.ServiceProject)"
Write-Host "[INFO] Logs:"
Write-Host "  - $(Join-Path $paths.ServiceLogs "backend.log")"
Write-Host "  - $(Join-Path $paths.ServiceLogs "frontend.log")"
pause
