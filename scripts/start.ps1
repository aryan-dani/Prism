# Prism Unified Launcher (Windows PowerShell)
# Automatically frees ports 8000 & 5173 if already in use,
# then launches Backend API and Frontend UI in two separate terminal windows.
# Usage: .\start.ps1  or  powershell -ExecutionPolicy Bypass -File scripts/start.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

function Free-Port([int]$port, [string]$serviceName) {
    $connections = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
    if ($connections) {
        $pids = $connections | Select-Object -ExpandProperty OwningProcess -Unique | Where-Object { $_ -gt 4 }
        foreach ($pidToKill in $pids) {
            $proc = Get-Process -Id $pidToKill -ErrorAction SilentlyContinue
            $procName = if ($proc) { $proc.ProcessName } else { "Unknown" }
            Write-Host "==> Port $port ($serviceName) is occupied by $procName (PID $pidToKill). Terminating..." -ForegroundColor Yellow
            Stop-Process -Id $pidToKill -Force -ErrorAction SilentlyContinue
        }
        for ($i = 0; $i -lt 6; $i++) {
            Start-Sleep -Milliseconds 500
            $stillInUse = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
            if (-not $stillInUse) { break }
        }
    }
}

# 1. Clean up existing processes if already running
Free-Port 8000 "Backend API"
Free-Port 5173 "Frontend UI"

# 2. Launch Backend API in a new terminal window
Write-Host "==> Launching Prism Backend API on http://127.0.0.1:8000 ..." -ForegroundColor Cyan
$backendCmd = "& { Set-Location '$root\backend'; `$host.UI.RawUI.WindowTitle = 'Prism Backend API (:8000)'; Write-Host '=== Prism Backend API ===' -ForegroundColor Cyan; uv run uvicorn prism.api.main:app --reload --port 8000 }"
Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", $backendCmd

# 3. Launch Frontend UI in a new terminal window
Write-Host "==> Launching Prism Frontend UI on http://localhost:5173 ..." -ForegroundColor Cyan
$frontendCmd = "& { Set-Location '$root\frontend'; `$host.UI.RawUI.WindowTitle = 'Prism Frontend UI (:5173)'; Write-Host '=== Prism Frontend UI ===' -ForegroundColor Green; npm run dev }"
Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", $frontendCmd

Write-Host ""
Write-Host "Prism launched successfully in 2 separate terminals!" -ForegroundColor Green
Write-Host "  • Frontend UI: http://localhost:5173" -ForegroundColor White
Write-Host "  • Backend API: http://127.0.0.1:8000" -ForegroundColor White
Write-Host "  • API Docs:    http://127.0.0.1:8000/docs" -ForegroundColor White
