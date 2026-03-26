param(
    [string]$ApiBase = "http://127.0.0.1:8000",
    [string]$Username = "weason",
    [string]$Password = "weason",
    [string]$ServiceName = "billing-backend",
    [switch]$RestartService
)

$ErrorActionPreference = "Stop"

function Invoke-Api {
    param(
        [Parameter(Mandatory = $true)][string]$Method,
        [Parameter(Mandatory = $true)][string]$Url,
        [hashtable]$Headers,
        [string]$Body,
        [string]$ContentType
    )

    try {
        $params = @{
            Method  = $Method
            Uri     = $Url
            TimeoutSec = 20
            UseBasicParsing = $true
        }
        if ($Headers) { $params.Headers = $Headers }
        if ($PSBoundParameters.ContainsKey("Body")) { $params.Body = $Body }
        if ($ContentType) { $params.ContentType = $ContentType }

        $resp = Invoke-WebRequest @params
        return [pscustomobject]@{
            StatusCode = [int]$resp.StatusCode
            BodyText   = $resp.Content
            ErrorText  = ""
        }
    } catch {
        if ($_.Exception.Response) {
            $status = [int]$_.Exception.Response.StatusCode
            $stream = $_.Exception.Response.GetResponseStream()
            $reader = New-Object IO.StreamReader($stream)
            $content = $reader.ReadToEnd()
            return [pscustomobject]@{
                StatusCode = $status
                BodyText   = $content
                ErrorText  = ""
            }
        }
        return [pscustomobject]@{
            StatusCode = 0
            BodyText   = ""
            ErrorText  = $_.Exception.Message
        }
    }
}

function Invoke-ApiWithRetry {
    param(
        [Parameter(Mandatory = $true)][string]$Method,
        [Parameter(Mandatory = $true)][string]$Url,
        [hashtable]$Headers,
        [string]$Body,
        [string]$ContentType,
        [int]$Attempts = 3,
        [int]$DelaySeconds = 2
    )

    $invokeParams = @{
        Method = $Method
        Url    = $Url
    }
    if ($PSBoundParameters.ContainsKey("Headers")) { $invokeParams.Headers = $Headers }
    if ($PSBoundParameters.ContainsKey("Body")) { $invokeParams.Body = $Body }
    if ($PSBoundParameters.ContainsKey("ContentType")) { $invokeParams.ContentType = $ContentType }

    $last = $null
    for ($i = 1; $i -le $Attempts; $i++) {
        $last = Invoke-Api @invokeParams
        if ($last.StatusCode -ne 0) {
            return $last
        }
        if ($i -lt $Attempts) {
            Start-Sleep -Seconds $DelaySeconds
        }
    }
    return $last
}

function Add-Check {
    param(
        [string]$Name,
        [bool]$Passed,
        [string]$Detail
    )
    $script:Checks += [pscustomobject]@{
        Name   = $Name
        Passed = $Passed
        Detail = $Detail
    }
}

$Checks = @()

Write-Host "=== Day1 Restart + Regression ==="
Write-Host "API Base: $ApiBase"

if ($RestartService) {
    Write-Host "[Step] Restart service: $ServiceName"
    $stop = (& sc.exe stop $ServiceName 2>&1 | Out-String).Trim()
    Start-Sleep -Seconds 2
    $start = (& sc.exe start $ServiceName 2>&1 | Out-String).Trim()
    Start-Sleep -Seconds 3
    $svc = (& sc.exe query $ServiceName 2>&1 | Out-String).Trim()
    $running = $svc -match "RUNNING"
    $permissionDenied = (($stop + "`n" + $start) -match "FAILED 5|Access is denied|OpenService FAILED")
    $restartOk = $running -and (-not $permissionDenied)
    Add-Check "Service restart ($ServiceName)" $restartOk "stop=[$stop] start=[$start] query=[$svc]"
}

Write-Host "[Step] Health check"
$health = Invoke-ApiWithRetry -Method "GET" -Url "$ApiBase/api/health" -Attempts 6 -DelaySeconds 2
$healthOk = ($health.StatusCode -eq 200) -and ($health.BodyText -match '"status"\s*:\s*"ok"')
$healthDetail = "status=$($health.StatusCode)"
if ($health.StatusCode -eq 0 -and $health.ErrorText) { $healthDetail += " error=$($health.ErrorText)" }
Add-Check "GET /api/health" $healthOk $healthDetail

$anonTargets = @(
    "/api/dashboard",
    "/api/clients",
    "/api/latest-result",
    "/api/exchange-rates"
)

Write-Host "[Step] Anonymous access check (should be 401)"
foreach ($path in $anonTargets) {
    $attempts = if ($path -eq "/api/exchange-rates") { 5 } else { 3 }
    $delay = if ($path -eq "/api/exchange-rates") { 3 } else { 2 }
    $resp = Invoke-ApiWithRetry -Method "GET" -Url "$ApiBase$path" -Attempts $attempts -DelaySeconds $delay
    $ok = ($resp.StatusCode -eq 401)
    $detail = "status=$($resp.StatusCode)"
    if ($resp.StatusCode -eq 0 -and $resp.ErrorText) { $detail += " error=$($resp.ErrorText)" }
    Add-Check "Anon $path => 401" $ok $detail
}

Write-Host "[Step] Login"
$loginBody = "username=$Username&password=$Password"
$loginResp = Invoke-ApiWithRetry -Method "POST" -Url "$ApiBase/api/token" -Body $loginBody -ContentType "application/x-www-form-urlencoded"
$token = $null
if ($loginResp.StatusCode -eq 200) {
    try {
        $loginJson = $loginResp.BodyText | ConvertFrom-Json
        $token = $loginJson.access_token
    } catch {
        $token = $null
    }
}
$loginOk = -not [string]::IsNullOrWhiteSpace($token)
$loginDetail = "status=$($loginResp.StatusCode)"
if ($loginResp.StatusCode -eq 0 -and $loginResp.ErrorText) { $loginDetail += " error=$($loginResp.ErrorText)" }
Add-Check "POST /api/token" $loginOk $loginDetail

if ($loginOk) {
    $authHeaders = @{ Authorization = "Bearer $token" }

    Write-Host "[Step] Authenticated access check (should be 200)"
    foreach ($path in $anonTargets) {
        $attempts = if ($path -eq "/api/exchange-rates") { 5 } else { 3 }
        $delay = if ($path -eq "/api/exchange-rates") { 3 } else { 2 }
        $resp = Invoke-ApiWithRetry -Method "GET" -Url "$ApiBase$path" -Headers $authHeaders -Attempts $attempts -DelaySeconds $delay
        $ok = ($resp.StatusCode -eq 200)
        $detail = "status=$($resp.StatusCode)"
        if ($resp.StatusCode -eq 0 -and $resp.ErrorText) { $detail += " error=$($resp.ErrorText)" }
        Add-Check "Auth $path => 200" $ok $detail
    }

    Write-Host "[Step] Latest result data check"
    $latest = Invoke-ApiWithRetry -Method "GET" -Url "$ApiBase/api/latest-result" -Headers $authHeaders
    $latestOk = $false
    $rows = 0
    if ($latest.StatusCode -eq 200) {
        try {
            $latestJson = $latest.BodyText | ConvertFrom-Json
            if ($latestJson.has_result -and $latestJson.data_url) {
                $resultResp = Invoke-ApiWithRetry -Method "GET" -Url "$ApiBase$($latestJson.data_url)" -Headers $authHeaders
                if ($resultResp.StatusCode -eq 200) {
                    $resultJson = $resultResp.BodyText | ConvertFrom-Json
                    $rows = @($resultJson.data).Count
                    $latestOk = $rows -ge 0
                }
            } else {
                $latestOk = $true
            }
        } catch {
            $latestOk = $false
        }
    }
    Add-Check "GET /api/latest-result -> /api/results" $latestOk "rows=$rows"
}

Write-Host ""
Write-Host "=== Summary ==="
$Checks | ForEach-Object {
    $flag = if ($_.Passed) { "[PASS]" } else { "[FAIL]" }
    Write-Host "$flag $($_.Name) | $($_.Detail)"
}

$failed = @($Checks | Where-Object { -not $_.Passed }).Count
if ($failed -gt 0) {
    Write-Host ""
    Write-Host "Result: FAILED ($failed checks failed)" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Result: PASSED" -ForegroundColor Green
exit 0
