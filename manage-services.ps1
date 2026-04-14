param(
    [ValidateSet(
        "menu",
        "status",
        "dev-start",
        "dev-stop",
        "dev-restart",
        "publish",
        "prod-start",
        "prod-stop",
        "prod-restart",
        "backend-start",
        "backend-restart",
        "logs"
    )]
    [string]$Action = "menu",
    [int]$DevPort = 5174,
    [int]$ProdPort = 5173,
    [int]$BackendPort = 8000
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

function Ensure-Directory {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Assert-Admin {
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "This action requires an elevated PowerShell session."
    }
}

function Resolve-CommandPath {
    param([string[]]$Candidates)
    foreach ($candidate in $Candidates) {
        if (-not [string]::IsNullOrWhiteSpace($candidate) -and (Test-Path -LiteralPath $candidate)) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($cmd) {
            return $cmd.Source
        }
    }
    return $null
}

function Service-Exists {
    param([string]$Name)
    try {
        Get-Service -Name $Name -ErrorAction Stop | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Get-ServiceAppFromRegistry {
    param([string]$Name)
    $regPath = "HKLM:\SYSTEM\CurrentControlSet\Services\$Name\Parameters"
    try {
        $item = Get-ItemProperty -Path $regPath -ErrorAction Stop
        if ($item.Application -and ($item.Application -is [string])) {
            return $item.Application.Trim()
        }
    } catch {}
    return $null
}

function Get-ServiceStatusText {
    param([string]$Name)
    try {
        return (Get-Service -Name $Name -ErrorAction Stop).Status.ToString()
    } catch {
        return "NotFound"
    }
}

function Get-ListenerPids {
    param([int]$Port)
    $result = @()
    $pattern = "^\s*TCP\s+\S+:$Port\s+\S+\s+(LISTENING|侦听)\s+(\d+)\s*$"
    $lines = netstat -ano -p TCP 2>$null
    foreach ($line in $lines) {
        if ($line -match $pattern) {
            $result += [int]$matches[2]
        }
    }
    if ($result.Count -eq 0) {
        return @()
    }
    return @($result | Select-Object -Unique)
}

function Wait-PortReady {
    param(
        [int]$Port,
        [int]$TimeoutSec = 30
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if ((Get-ListenerPids -Port $Port).Count -gt 0) {
            return $true
        }
        Start-Sleep -Milliseconds 400
    }
    return $false
}

function Stop-PidTree {
    param(
        [int]$ProcessId,
        [string]$Reason = ""
    )
    if ($ProcessId -le 0) {
        return
    }
    $proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $proc) {
        return
    }
    if ($Reason) {
        Write-Info "Stopping PID $ProcessId ($Reason)"
    } else {
        Write-Info "Stopping PID $ProcessId"
    }
    cmd /c "taskkill /PID $ProcessId /T /F" *> $null
}

function Stop-PortListeners {
    param([int]$Port)
    $pids = Get-ListenerPids -Port $Port
    foreach ($pid in $pids) {
        Stop-PidTree -ProcessId ([int]$pid) -Reason "port $Port"
    }
}

function Load-State {
    param([string]$StateFile)
    if (-not (Test-Path -LiteralPath $StateFile)) {
        return $null
    }
    try {
        return (Get-Content -LiteralPath $StateFile -Raw | ConvertFrom-Json)
    } catch {
        return $null
    }
}

function Save-State {
    param(
        [string]$StateFile,
        [int]$DevPid,
        [int]$DevPort
    )
    $payload = @{
        dev_pid    = $DevPid
        dev_port   = $DevPort
        updated_at = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    } | ConvertTo-Json -Depth 3
    Set-Content -LiteralPath $StateFile -Value $payload -Encoding UTF8
}

function Clear-State {
    param([string]$StateFile)
    if (Test-Path -LiteralPath $StateFile) {
        Remove-Item -LiteralPath $StateFile -Force -ErrorAction SilentlyContinue
    }
}

function Resolve-NssmPath {
    param([string]$ProjectDir)

    $candidates = @(
        "C:\Users\norah\AppData\Local\Microsoft\WinGet\Packages\NSSM.NSSM_Microsoft.Winget.Source_8wekyb3d8bbwe\nssm-2.24-101-g897c7ad\win64\nssm.exe",
        (Join-Path $ProjectDir "bin\nssm.exe"),
        "nssm.exe"
    )

    $path = Resolve-CommandPath -Candidates $candidates
    if ($path) {
        return $path
    }

    if (Service-Exists -Name "billing-backend") {
        $qc = sc.exe qc billing-backend 2>$null
        foreach ($line in $qc) {
            if ($line -match "BINARY_PATH_NAME\s*:\s*(.+)$") {
                $bin = $matches[1].Trim().Trim('"')
                if ($bin) {
                    return $bin
                }
            }
        }
    }
    return $null
}

function Resolve-ServicePythonPath {
    param(
        [string]$NssmPath,
        [string]$ProjectDir,
        [string]$ServiceProjectDir
)

    $backendApp = Get-ServiceAppFromRegistry -Name "billing-backend"
    if (-not [string]::IsNullOrWhiteSpace($backendApp)) {
        return $backendApp
    }

    if (Service-Exists -Name "billing-backend" -and $NssmPath) {
        try {
            $app = (& $NssmPath get billing-backend Application).Trim()
            if ($app -and (Test-Path -LiteralPath $app)) {
                return $app
            }
        } catch {}
    }

    $candidates = @(
        (Join-Path (Split-Path -Parent $ProjectDir) ".venv\Scripts\python.exe"),
        (Join-Path $ProjectDir ".venv\Scripts\python.exe"),
        (Join-Path $ServiceProjectDir ".venv\Scripts\python.exe"),
        "python.exe"
    )
    return (Resolve-CommandPath -Candidates $candidates)
}

function Start-DevFrontend {
    param(
        [string]$WebDir,
        [string]$StateFile,
        [int]$DevPort,
        [int]$BackendPort
    )
    $npm = Resolve-CommandPath -Candidates @("npm.cmd", "npm")
    if (-not $npm) {
        throw "npm was not found."
    }
    if (-not (Test-Path -LiteralPath (Join-Path $WebDir "package.json"))) {
        throw "web\\package.json was not found."
    }

    Stop-DevFrontend -StateFile $StateFile -DevPort $DevPort | Out-Null

    $previousProxy = $env:VITE_API_PROXY_TARGET
    $env:VITE_API_PROXY_TARGET = "http://127.0.0.1:$BackendPort"
    try {
        $args = @(
            "run", "dev", "--",
            "--host", "0.0.0.0",
            "--port", "$DevPort",
            "--strictPort"
        )
        Write-Info "Starting dev frontend at http://127.0.0.1:$DevPort"
        $proc = Start-Process -FilePath $npm -ArgumentList $args -WorkingDirectory $WebDir -PassThru
    } finally {
        if ([string]::IsNullOrWhiteSpace($previousProxy)) {
            Remove-Item Env:VITE_API_PROXY_TARGET -ErrorAction SilentlyContinue
        } else {
            $env:VITE_API_PROXY_TARGET = $previousProxy
        }
    }

    if (-not (Wait-PortReady -Port $DevPort -TimeoutSec 25)) {
        Stop-PidTree -ProcessId $proc.Id -Reason "dev startup timeout"
        throw "Dev frontend failed to listen on port $DevPort."
    }

    Save-State -StateFile $StateFile -DevPid $proc.Id -DevPort $DevPort
    Write-Ok "Dev frontend started, PID=$($proc.Id), port=$DevPort"
}

function Stop-DevFrontend {
    param(
        [string]$StateFile,
        [int]$DevPort
    )
    $state = Load-State -StateFile $StateFile
    if ($state -and [int]$state.dev_pid -gt 0) {
        Stop-PidTree -ProcessId ([int]$state.dev_pid) -Reason "dev state"
    }
    Stop-PortListeners -Port $DevPort
    Clear-State -StateFile $StateFile
    Write-Ok "Dev frontend stopped."
}

function Ensure-ProdFrontendService {
    param(
        [string]$NssmPath,
        [string]$PythonPath,
        [string]$ServiceProjectDir,
        [string]$ServiceLogDir,
        [int]$ProdPort
    )
    Assert-Admin
    Ensure-Directory -Path $ServiceLogDir

    $params = "scripts\serve_frontend.py --host 0.0.0.0 --port $ProdPort --dir web\dist"
    if (-not (Service-Exists -Name "billing-frontend")) {
        Write-Info "Creating service billing-frontend"
        & $NssmPath install billing-frontend $PythonPath $params | Out-Null
    }

    & $NssmPath set billing-frontend Application $PythonPath | Out-Null
    & $NssmPath set billing-frontend AppParameters $params | Out-Null
    & $NssmPath set billing-frontend AppDirectory $ServiceProjectDir | Out-Null
    & $NssmPath set billing-frontend AppStdout (Join-Path $ServiceLogDir "frontend.log") | Out-Null
    & $NssmPath set billing-frontend AppStderr (Join-Path $ServiceLogDir "frontend.err.log") | Out-Null
    & $NssmPath set billing-frontend Start SERVICE_AUTO_START | Out-Null
}

function Restart-ProdFrontendService {
    param(
        [string]$NssmPath,
        [int]$ProdPort
    )
    Assert-Admin
    if (-not (Service-Exists -Name "billing-frontend")) {
        throw "Service billing-frontend does not exist."
    }

    Write-Info "Restarting billing-frontend"
    & $NssmPath stop billing-frontend | Out-Null
    Start-Sleep -Seconds 1
    Stop-PortListeners -Port $ProdPort
    & $NssmPath start billing-frontend | Out-Null

    if (-not (Wait-PortReady -Port $ProdPort -TimeoutSec 25)) {
        throw "Prod frontend port $ProdPort is not ready."
    }
    Write-Ok "Prod frontend is running on port $ProdPort."
}

function Build-Frontend {
    param([string]$WebDir)
    $npm = Resolve-CommandPath -Candidates @("npm.cmd", "npm")
    if (-not $npm) {
        throw "npm was not found."
    }
    Write-Info "Building frontend dist..."
    & $npm --prefix $WebDir run build
    if ($LASTEXITCODE -ne 0) {
        throw "Build failed."
    }
    Write-Ok "Build completed."
}

function Start-BackendService {
    param([int]$BackendPort)
    Assert-Admin
    if (-not (Service-Exists -Name "billing-backend")) {
        throw "Service billing-backend does not exist."
    }
    if ((Get-ServiceStatusText -Name "billing-backend") -ne "Running") {
        sc.exe start billing-backend | Out-Null
    }
    if (-not (Wait-PortReady -Port $BackendPort -TimeoutSec 30)) {
        throw "Backend port $BackendPort is not ready."
    }
    Write-Ok "Backend service is running."
}

function Restart-BackendService {
    param([int]$BackendPort)
    Assert-Admin
    if (-not (Service-Exists -Name "billing-backend")) {
        throw "Service billing-backend does not exist."
    }
    sc.exe stop billing-backend | Out-Null
    Start-Sleep -Seconds 1
    sc.exe start billing-backend | Out-Null
    if (-not (Wait-PortReady -Port $BackendPort -TimeoutSec 30)) {
        throw "Backend port $BackendPort is not ready."
    }
    Write-Ok "Backend service restarted."
}

function Publish-DevToProd {
    param(
        [string]$ProjectDir,
        [string]$WebDir,
        [string]$ServiceProjectDir,
        [string]$ServiceLogDir,
        [int]$ProdPort
    )
    Build-Frontend -WebDir $WebDir

    $nssm = Resolve-NssmPath -ProjectDir $ProjectDir
    if (-not $nssm) {
        throw "nssm.exe was not found."
    }

    $python = Resolve-ServicePythonPath -NssmPath $nssm -ProjectDir $ProjectDir -ServiceProjectDir $ServiceProjectDir
    if (-not $python) {
        throw "Python for service was not found."
    }

    Ensure-ProdFrontendService -NssmPath $nssm -PythonPath $python -ServiceProjectDir $ServiceProjectDir -ServiceLogDir $ServiceLogDir -ProdPort $ProdPort
    Restart-ProdFrontendService -NssmPath $nssm -ProdPort $ProdPort
    Write-Ok "Publish done. Port $ProdPort now serves latest dist."
}

function Show-Status {
    param(
        [string]$StateFile,
        [int]$DevPort,
        [int]$ProdPort,
        [int]$BackendPort
    )
    $state = Load-State -StateFile $StateFile
    $backendPids = Get-ListenerPids -Port $BackendPort
    $prodPids = Get-ListenerPids -Port $ProdPort
    $devPids = Get-ListenerPids -Port $DevPort

    Write-Host "============ Status ============"
    Write-Host "backend service : $(Get-ServiceStatusText -Name 'billing-backend')"
    Write-Host "frontend service: $(Get-ServiceStatusText -Name 'billing-frontend')"
    Write-Host "backend port $BackendPort : $(if ($backendPids.Count -gt 0) { $backendPids -join ', ' } else { 'free' })"
    Write-Host "prod port $ProdPort    : $(if ($prodPids.Count -gt 0) { $prodPids -join ', ' } else { 'free' })"
    Write-Host "dev  port $DevPort     : $(if ($devPids.Count -gt 0) { $devPids -join ', ' } else { 'free' })"
    if ($state) {
        Write-Host "dev state pid       : $($state.dev_pid)"
        Write-Host "dev state updated   : $($state.updated_at)"
    } else {
        Write-Host "dev state           : none"
    }
}

function Show-Logs {
    param([string]$ServiceLogDir)
    $backendLog = Join-Path $ServiceLogDir "backend.log"
    $frontendLog = Join-Path $ServiceLogDir "frontend.log"
    $frontendErr = Join-Path $ServiceLogDir "frontend.err.log"

    Write-Host "------ backend.log (tail 30) ------" -ForegroundColor DarkYellow
    if (Test-Path -LiteralPath $backendLog) { Get-Content -LiteralPath $backendLog -Tail 30 } else { Write-Host "(no file)" }
    Write-Host ""
    Write-Host "------ frontend.log (tail 30) ------" -ForegroundColor DarkYellow
    if (Test-Path -LiteralPath $frontendLog) { Get-Content -LiteralPath $frontendLog -Tail 30 } else { Write-Host "(no file)" }
    Write-Host ""
    Write-Host "---- frontend.err.log (tail 30) ----" -ForegroundColor DarkYellow
    if (Test-Path -LiteralPath $frontendErr) { Get-Content -LiteralPath $frontendErr -Tail 30 } else { Write-Host "(no file)" }
}

function Show-Menu {
    Clear-Host
    Write-Host "=============================================="
    Write-Host " Billing Manager (prod:5173, dev:5174)"
    Write-Host "=============================================="
    Write-Host " [1] status"
    Write-Host " [2] dev-start  (start vite on 5174)"
    Write-Host " [3] dev-stop   (stop vite on 5174)"
    Write-Host " [4] publish    (build + restart prod 5173)"
    Write-Host " [5] prod-start"
    Write-Host " [6] prod-restart"
    Write-Host " [7] backend-restart"
    Write-Host " [8] logs"
    Write-Host " [Q] quit"
    Write-Host "=============================================="
}

$ProjectDir = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$WebDir = Join-Path $ProjectDir "web"
$LogDir = Join-Path $ProjectDir "logs"
$StateFile = Join-Path $LogDir "manage-services.state.json"
$ServiceProjectDir = if (Test-Path -LiteralPath "C:\AGM_BILLING") { "C:\AGM_BILLING" } else { $ProjectDir }
$ServiceLogDir = Join-Path $ServiceProjectDir "logs"

Ensure-Directory -Path $LogDir
Ensure-Directory -Path $ServiceLogDir

try {
    switch ($Action) {
        "status" {
            Show-Status -StateFile $StateFile -DevPort $DevPort -ProdPort $ProdPort -BackendPort $BackendPort
            exit 0
        }
        "dev-start" {
            Start-DevFrontend -WebDir $WebDir -StateFile $StateFile -DevPort $DevPort -BackendPort $BackendPort
            exit 0
        }
        "dev-stop" {
            Stop-DevFrontend -StateFile $StateFile -DevPort $DevPort
            exit 0
        }
        "dev-restart" {
            Stop-DevFrontend -StateFile $StateFile -DevPort $DevPort
            Start-Sleep -Milliseconds 500
            Start-DevFrontend -WebDir $WebDir -StateFile $StateFile -DevPort $DevPort -BackendPort $BackendPort
            exit 0
        }
        "publish" {
            Publish-DevToProd -ProjectDir $ProjectDir -WebDir $WebDir -ServiceProjectDir $ServiceProjectDir -ServiceLogDir $ServiceLogDir -ProdPort $ProdPort
            exit 0
        }
        "prod-start" {
            Assert-Admin
            $nssm = Resolve-NssmPath -ProjectDir $ProjectDir
            if (-not $nssm) { throw "nssm.exe was not found." }
            if ((Get-ServiceStatusText -Name "billing-frontend") -ne "Running") {
                & $nssm start billing-frontend | Out-Null
            }
            if (-not (Wait-PortReady -Port $ProdPort -TimeoutSec 20)) { throw "Prod port $ProdPort is not ready." }
            Write-Ok "Prod frontend started."
            exit 0
        }
        "prod-stop" {
            Assert-Admin
            $nssm = Resolve-NssmPath -ProjectDir $ProjectDir
            if (-not $nssm) { throw "nssm.exe was not found." }
            if (Service-Exists -Name "billing-frontend") {
                & $nssm stop billing-frontend | Out-Null
            }
            Write-Ok "Prod frontend stopped."
            exit 0
        }
        "prod-restart" {
            Assert-Admin
            $nssm = Resolve-NssmPath -ProjectDir $ProjectDir
            if (-not $nssm) { throw "nssm.exe was not found." }
            Restart-ProdFrontendService -NssmPath $nssm -ProdPort $ProdPort
            exit 0
        }
        "backend-start" {
            Start-BackendService -BackendPort $BackendPort
            exit 0
        }
        "backend-restart" {
            Restart-BackendService -BackendPort $BackendPort
            exit 0
        }
        "logs" {
            Show-Logs -ServiceLogDir $ServiceLogDir
            exit 0
        }
        "menu" {
            while ($true) {
                Show-Menu
                $choice = (Read-Host "Choose [1-8,Q]").Trim().ToUpperInvariant()
                switch ($choice) {
                    "1" { Show-Status -StateFile $StateFile -DevPort $DevPort -ProdPort $ProdPort -BackendPort $BackendPort; Pause }
                    "2" { Start-DevFrontend -WebDir $WebDir -StateFile $StateFile -DevPort $DevPort -BackendPort $BackendPort; Pause }
                    "3" { Stop-DevFrontend -StateFile $StateFile -DevPort $DevPort; Pause }
                    "4" { Publish-DevToProd -ProjectDir $ProjectDir -WebDir $WebDir -ServiceProjectDir $ServiceProjectDir -ServiceLogDir $ServiceLogDir -ProdPort $ProdPort; Pause }
                    "5" {
                        Assert-Admin
                        $nssm = Resolve-NssmPath -ProjectDir $ProjectDir
                        if (-not $nssm) { throw "nssm.exe was not found." }
                        & $nssm start billing-frontend | Out-Null
                        Write-Ok "Prod frontend start command sent."
                        Pause
                    }
                    "6" {
                        Assert-Admin
                        $nssm = Resolve-NssmPath -ProjectDir $ProjectDir
                        if (-not $nssm) { throw "nssm.exe was not found." }
                        Restart-ProdFrontendService -NssmPath $nssm -ProdPort $ProdPort
                        Pause
                    }
                    "7" { Restart-BackendService -BackendPort $BackendPort; Pause }
                    "8" { Show-Logs -ServiceLogDir $ServiceLogDir; Pause }
                    "Q" { break }
                    default { Write-Warn "Invalid input: $choice"; Start-Sleep -Milliseconds 500 }
                }
            }
            exit 0
        }
    }
} catch {
    Write-Err $_.Exception.Message
    exit 1
}
