# 文书网日批采集（Windows 服务机）
# 用法: powershell -File scripts\run_daily.ps1
# 可选: $env:PROXY = "http://127.0.0.1:10808"  或  $env:PROXY = ""
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$proxy = if ($null -ne $env:PROXY) { $env:PROXY } else { "http://127.0.0.1:10808" }
$logDir = if ($env:LOG_DIR) { $env:LOG_DIR } else { ".\logs" }
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = Join-Path $logDir "daily_$stamp.log"

function Log($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-ddTHH:mm:ss"), $msg
    $line | Tee-Object -FilePath $logFile -Append
}

Log "start daily crawl proxy=$(if ($proxy) { $proxy } else { 'direct' })"
if ($proxy -eq "") {
    python crawler_wenshu.py --proxy "" 2>&1 | Tee-Object -FilePath $logFile -Append
} else {
    python crawler_wenshu.py --proxy $proxy 2>&1 | Tee-Object -FilePath $logFile -Append
}
$code = $LASTEXITCODE
Log "exit=$code"
exit $code
