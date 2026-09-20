# Prism Unified Launcher (Windows PowerShell)
# Automatically frees ports 8000 & 5173 if already in use,
# then launches Backend API and Frontend UI in two separate terminal windows.
# Usage: .\start.ps1  or  powershell -ExecutionPolicy Bypass -File scripts/start.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

function Clear-Port([int]$port, [string]$serviceName) {
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

function Test-Ollama {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/tags" -UseBasicParsing -TimeoutSec 2
        return $r.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Ensure-Ollama {
    if (Test-Ollama) {
        Write-Host "==> Ollama is already running on :11434" -ForegroundColor Green
        return
    }

    $ollama = Get-Command ollama -ErrorAction SilentlyContinue
    $app = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
    if (-not $ollama -and (Test-Path $app)) {
        $ollama = @{ Source = $app }
    }

    if (-not $ollama) {
        Write-Host "==> Ollama is not installed (or not on PATH). Chat will show API degraded until you install it from https://ollama.com" -ForegroundColor Yellow
        return
    }

    Write-Host "==> Starting Ollama on :11434 ..." -ForegroundColor Cyan
    Start-Process -FilePath $ollama.Source -ArgumentList "serve" -WindowStyle Hidden

    $ready = $false
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Milliseconds 500
        if (Test-Ollama) {
            $ready = $true
            break
        }
    }

    if ($ready) {
        Write-Host "==> Ollama is up" -ForegroundColor Green
    } else {
        Write-Host "==> Ollama did not answer on :11434 yet. The UI may show API degraded until it finishes starting." -ForegroundColor Yellow
    }
}

# 1. Clean up existing processes if already running
Clear-Port 8000 "Backend API"
Clear-Port 5173 "Frontend UI"

# 1b. Ollama must be up or /api/health reports degraded
Ensure-Ollama

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
Write-Host "  • Ollama:      http://127.0.0.1:11434" -ForegroundColor White

function Wait-Http([string]$url, [int]$tries = 40) {
    for ($i = 0; $i -lt $tries; $i++) {
        try {
            $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
            if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) { return $true }
        } catch {
            Start-Sleep -Milliseconds 400
        }
    }
    return $false
}

Write-Host "==> Opening the UI maximized ..." -ForegroundColor Cyan
if (Wait-Http "http://localhost:5173") {
    $chrome = @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    if ($chrome) {
        Start-Process -FilePath $chrome -ArgumentList "--start-maximized", "--window-position=0,0", "http://localhost:5173"
    } else {
        Start-Process "http://localhost:5173"
    }
} else {
    Write-Host "==> UI did not answer on :5173 yet. Open http://localhost:5173 and maximize the window." -ForegroundColor Yellow
}
