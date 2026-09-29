# Prism launcher (Windows)
# Starts Docker Desktop, host Ollama, and the Compose stack, then opens the UI.
# Usage: .\start.ps1
#    or: powershell -ExecutionPolicy Bypass -File scripts/start.ps1

$ErrorActionPreference = "Stop"
# docker.exe writes the "daemon is not running" message to stderr. Windows
# PowerShell treats that as a terminating NativeCommandError when Stop is set,
# so the launcher never reached Start-Process for Docker Desktop.
if (Test-Path variable:PSNativeCommandUseErrorActionPreference) {
    $PSNativeCommandUseErrorActionPreference = $false
}
$root = Split-Path -Parent $PSScriptRoot
$uiUrl = "http://localhost:8080"
$apiUrl = "http://127.0.0.1:8000"
$healthUrl = "$apiUrl/api/health"
$composeFile = Join-Path $root "docker-compose.yml"

function Write-Step([string]$message, [string]$color = "Cyan") {
    Write-Host "==> $message" -ForegroundColor $color
}

function Test-DockerEngine {
    param([string]$DockerExe)
    $pipe = "\\.\pipe\dockerDesktopLinuxEngine"
    if (-not (Test-Path $pipe)) { return $false }

    $prev = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    try {
        $null = & $DockerExe info --format "{{.ServerVersion}}" 2>&1
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    } finally {
        $ErrorActionPreference = $prev
    }
}

function Resolve-DockerCli {
    $cmd = Get-Command docker -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $fallback = Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe"
    if (Test-Path $fallback) { return $fallback }
    return $null
}

function Get-DockerDesktopPath {
    @(
        (Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Docker\Docker\Docker Desktop.exe"),
        (Join-Path $env:LOCALAPPDATA "Docker\Docker Desktop.exe")
    ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
}

function Ensure-Docker {
    param([string]$DockerExe)
    if (Test-DockerEngine -DockerExe $DockerExe) {
        Write-Step "Docker is already running" "Green"
        return
    }

    $desktop = Get-DockerDesktopPath
    if (-not $desktop) {
        throw "Docker Desktop is not installed. Install it from https://www.docker.com/products/docker-desktop/ and run .\start.ps1 again."
    }

    Write-Step "Starting Docker Desktop (first boot can take a couple of minutes) ..."
    Start-Process -FilePath $desktop | Out-Null

    for ($i = 1; $i -le 90; $i++) {
        Start-Sleep -Seconds 2
        if (Test-DockerEngine -DockerExe $DockerExe) {
            Write-Step "Docker is up" "Green"
            return
        }
        if ($i -eq 1 -or $i % 5 -eq 0) {
            Write-Host "    waiting for the Docker engine ($i/90) ..." -ForegroundColor DarkGray
        }
    }

    throw "Docker Desktop did not become ready. Open it from the system tray, wait until it says Running, then run .\start.ps1 again."
}

function Test-Ollama {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/tags" -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Ensure-Ollama {
    if (Test-Ollama) {
        Write-Step "Ollama is already running on :11434" "Green"
        return
    }

    $ollama = Get-Command ollama -ErrorAction SilentlyContinue
    $app = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
    if (-not $ollama -and (Test-Path $app)) {
        $ollama = @{ Source = $app }
    }

    if (-not $ollama) {
        Write-Step "Ollama is not installed. The UI will open, but chat stays degraded until you install it from https://ollama.com" "Yellow"
        return
    }

    Write-Step "Starting Ollama on :11434 ..."
    Start-Process -FilePath $ollama.Source -ArgumentList "serve" -WindowStyle Hidden | Out-Null

    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Milliseconds 500
        if (Test-Ollama) {
            Write-Step "Ollama is up" "Green"
            return
        }
    }

    Write-Step "Ollama did not answer on :11434 yet. The API will keep retrying for a few seconds." "Yellow"
}

function Test-DockerOwnedProcess {
    param($Process)
    if (-not $Process) { return $false }
    if ($Process.ProcessName -match '^(com\.docker|docker|dockerd|vpnkit|wslrelay)$') { return $true }
    try {
        if ($Process.Path -and $Process.Path -match '\\Docker\\') { return $true }
    } catch {
        return $false
    }
    return $false
}

function Clear-NonDockerPort {
    param([int]$Port, [string]$ServiceName)
    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $connections) { return }

    $pids = $connections | Select-Object -ExpandProperty OwningProcess -Unique | Where-Object { $_ -gt 4 }
    foreach ($pidToStop in $pids) {
        $proc = Get-Process -Id $pidToStop -ErrorAction SilentlyContinue
        $procName = if ($proc) { $proc.ProcessName } else { "Unknown" }
        if (Test-DockerOwnedProcess -Process $proc) {
            Write-Step "Port $Port ($ServiceName) is already published by Docker ($procName). Leaving it." "DarkGray"
            continue
        }
        Write-Step "Port $Port ($ServiceName) is occupied by $procName (PID $pidToStop). Stopping it so Compose can bind." "Yellow"
        Stop-Process -Id $pidToStop -Force -ErrorAction SilentlyContinue
    }
}

function Wait-Http {
    param([string]$Url, [int]$Tries = 40, [int]$DelayMs = 500)
    for ($i = 0; $i -lt $Tries; $i++) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) { return $true }
        } catch {
            Start-Sleep -Milliseconds $DelayMs
        }
    }
    return $false
}

function Wait-Health {
    param([int]$Tries = 90)
    for ($i = 1; $i -le $Tries; $i++) {
        try {
            $response = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -eq 200) {
                return $response.Content | ConvertFrom-Json
            }
        } catch {
            if ($i -eq 1 -or $i % 5 -eq 0) {
                Write-Host "    waiting for the API ($i/$Tries) ..." -ForegroundColor DarkGray
            }
            Start-Sleep -Seconds 2
        }
    }
    return $null
}

function Open-PrismUi {
    if (-not (Wait-Http -Url $uiUrl -Tries 30 -DelayMs 500)) {
        Write-Step "UI did not answer on :8080 yet. Open $uiUrl once the web container is up." "Yellow"
        return
    }

    Write-Step "Opening the UI maximized ..."
    $chrome = @(
        (Join-Path $env:ProgramFiles "Google\Chrome\Application\chrome.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Google\Chrome\Application\chrome.exe"),
        (Join-Path $env:LOCALAPPDATA "Google\Chrome\Application\chrome.exe")
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1

    if ($chrome) {
        Start-Process -FilePath $chrome -ArgumentList "--start-maximized", "--window-position=0,0", $uiUrl | Out-Null
    } else {
        Start-Process $uiUrl | Out-Null
    }
}

if (-not (Test-Path $composeFile)) {
    throw "docker-compose.yml was not found at $composeFile"
}

Write-Host ""
Write-Host "Prism" -ForegroundColor Cyan
Write-Host "Starting Docker, Ollama, and the UI + API containers." -ForegroundColor Cyan
Write-Host ""

$docker = Resolve-DockerCli
if (-not $docker) {
    throw "The Docker CLI is not installed. Install Docker Desktop from https://www.docker.com/products/docker-desktop/ and run .\start.ps1 again."
}

Ensure-Docker -DockerExe $docker
Ensure-Ollama

Clear-NonDockerPort -Port 8000 -ServiceName "API"
Clear-NonDockerPort -Port 8080 -ServiceName "UI"
Clear-NonDockerPort -Port 5173 -ServiceName "old Vite dev server"

function Test-PrismImages {
    $names = @("prism-api", "prism-web")
    foreach ($name in $names) {
        $id = & $docker images -q $name 2>$null
        if (-not $id) { return $false }
    }
    return $true
}

Write-Step "Building and starting containers (this reuses cached image layers) ..."
& $docker compose --project-directory $root up -d --build --remove-orphans
if ($LASTEXITCODE -ne 0) {
    if (Test-PrismImages) {
        Write-Step "Registry unreachable during rebuild. Starting existing local images instead ..." "Yellow"
        & $docker compose --project-directory $root up -d --no-build --remove-orphans
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Step "docker compose failed. Recent API logs:" "Red"
        & $docker compose --project-directory $root logs --tail 60 api
        Write-Host "    If the error mentions registry-1.docker.io / no such host, Docker Desktop lost DNS." -ForegroundColor Yellow
        Write-Host "    Fix: check Wi‑Fi/VPN, restart Docker Desktop, then rerun .\start.ps1." -ForegroundColor Yellow
        Write-Host "    Cached images are enough for demos: docker compose up -d --no-build" -ForegroundColor Yellow
        throw "Prism containers did not start."
    }
}

Write-Step "Waiting for API health ..."
$health = Wait-Health
if (-not $health) {
    Write-Step "API did not become healthy. Recent logs:" "Red"
    & $docker compose --project-directory $root logs --tail 80 api
    throw "Timed out waiting for $healthUrl"
}

Open-PrismUi

Write-Host ""
if ($health.status -eq "ok") {
    Write-Step "Prism is up" "Green"
} else {
    Write-Step "Prism UI is up, but API health is '$($health.status)'" "Yellow"
    if ($health.ollama -and -not $health.ollama.reachable) {
        Write-Host "    Ollama is not reachable from the container." -ForegroundColor Yellow
        Write-Host "    Set user env OLLAMA_HOST=0.0.0.0:11434, fully quit Ollama, then run .\start.ps1 again." -ForegroundColor Yellow
    }
    if ($health.ollama.models_missing -and $health.ollama.models_missing.Count -gt 0) {
        Write-Host "    Missing models: $($health.ollama.models_missing -join ', ')" -ForegroundColor Yellow
        Write-Host "    Run: ollama pull nomic-embed-text; ollama pull qwen2.5:7b-instruct; ollama pull qwen2.5:3b-instruct" -ForegroundColor Yellow
    }
}

Write-Host "  - UI:        $uiUrl" -ForegroundColor White
Write-Host "  - API:       $apiUrl" -ForegroundColor White
Write-Host "  - API docs:  $apiUrl/docs" -ForegroundColor White
Write-Host "  - Health:    $($health.status), $($health.chunks_indexed) chunks, Ollama $($health.ollama.host)" -ForegroundColor White
Write-Host "  - Login:     alex.employee@prism.local / Prism2026!" -ForegroundColor White
Write-Host "  - Logs:      docker compose logs -f" -ForegroundColor White
Write-Host "  - Stop:      docker compose down" -ForegroundColor White
Write-Host ""
