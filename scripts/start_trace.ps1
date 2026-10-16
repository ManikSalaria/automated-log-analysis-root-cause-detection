# ==============================================================================
# TRACE Platform - Service Launcher (Windows PowerShell)
# Automated Log Analysis and Root Cause Detection System using Machine Learning
# ==============================================================================

[CmdletBinding()]
param()

$RootDir = Resolve-Path "$PSScriptRoot\.."
Set-Location $RootDir

Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host " TRACE Platform: Starting Services" -ForegroundColor Cyan
Write-Host "==============================================================================" -ForegroundColor Cyan

# 1. Check venv
$venvPython = Join-Path $RootDir ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "[ERROR] Virtual environment not found at .venv." -ForegroundColor Red
    Write-Host "Please run .\scripts\setup_windows.ps1 first to prepare the environment." -ForegroundColor Red
    exit 1
}

# 2. Check .env
$envFile = Join-Path $RootDir ".env"
$envExample = Join-Path $RootDir ".env.example"
if (-not (Test-Path $envFile) -and (Test-Path $envExample)) {
    Copy-Item $envExample $envFile
    Write-Host "[INFO] Copied .env.example to .env" -ForegroundColor Gray
}

# 3. Check Ollama Status
Write-Host "`nChecking Ollama service..." -ForegroundColor Yellow
try {
    $ollama = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -Method Get -TimeoutSec 2 -ErrorAction SilentlyContinue
    $models = $ollama.models | ForEach-Object { $_.name }
    Write-Host "  [OK] Ollama is active. Available models: $($models -join ', ')" -ForegroundColor Green
} catch {
    Write-Host "  [NOTICE] Ollama is not running on http://localhost:11434." -ForegroundColor Yellow
    Write-Host "           ML Classifiers (Stages 1-3) and Hybrid RAG (Stage 4) will run normally." -ForegroundColor Yellow
    Write-Host "           Stage 5 synthesis will report 'provider_unavailable' until Ollama is started." -ForegroundColor Yellow
    Write-Host "           To start Ollama: run 'ollama serve' and 'ollama pull llama3.2:3b'" -ForegroundColor Gray
}

# 4. Launch FastAPI Backend
Write-Host "`n[1/2] Launching FastAPI Backend on http://localhost:8000 ..." -ForegroundColor Cyan
$backendDir = Join-Path $RootDir "backend"
$backendCmd = "cd /d `"$backendDir`" && `"$venvPython`" -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
Start-Process -FilePath "cmd.exe" -ArgumentList "/k $backendCmd" -WindowStyle Normal

# 5. Launch React Frontend
Write-Host "[2/2] Launching React Frontend Dashboard on http://localhost:3000 ..." -ForegroundColor Cyan
$frontendDir = Join-Path $RootDir "frontend"
$frontendCmd = "cd /d `"$frontendDir`" && npm run dev"
Start-Process -FilePath "cmd.exe" -ArgumentList "/k $frontendCmd" -WindowStyle Normal

# 6. Verify Service Startup
Write-Host "`n[3/3] Verifying service startup..." -ForegroundColor Yellow

$backendReady = $false
$maxRetries = 15
Write-Host "  Checking FastAPI Backend health (http://localhost:8000/api/v1/health) ..." -NoNewline
for ($i = 1; $i -le $maxRetries; $i++) {
    try {
        $health = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/health" -Method Get -TimeoutSec 2 -ErrorAction Stop
        if ($health.status -in @("ok", "healthy")) {
            $backendReady = $true
            break
        }
    } catch {
        Start-Sleep -Seconds 1
    }
}
if ($backendReady) {
    Write-Host " [READY]" -ForegroundColor Green
} else {
    Write-Host " [INITIALIZING]" -ForegroundColor Yellow
    Write-Host "  [NOTE] Backend process started in console; it may take a few moments to finish loading PyTorch and Sentence-BERT." -ForegroundColor Gray
}

$frontendReady = $false
Write-Host "  Checking React Frontend dashboard (http://localhost:3000) ..." -NoNewline
for ($i = 1; $i -le 10; $i++) {
    try {
        $res = Invoke-WebRequest -Uri "http://localhost:3000" -Method Get -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
        if ($res.StatusCode -eq 200) {
            $frontendReady = $true
            break
        }
    } catch {
        Start-Sleep -Seconds 1
    }
}
if ($frontendReady) {
    Write-Host " [READY]" -ForegroundColor Green
} else {
    Write-Host " [INITIALIZING]" -ForegroundColor Yellow
    Write-Host "  [NOTE] Vite dev server started in console; it will be accessible at http://localhost:3000 shortly." -ForegroundColor Gray
}

# 7. Summary
Write-Host "`n==============================================================================" -ForegroundColor Green
Write-Host " All TRACE services initialized!" -ForegroundColor Green
Write-Host "==============================================================================" -ForegroundColor Green
Write-Host "  - React Dashboard:     http://localhost:3000" -ForegroundColor White
Write-Host "  - FastAPI Swagger UI:  http://localhost:8000/docs" -ForegroundColor White
Write-Host "  - System Health API:   http://localhost:8000/api/v1/health" -ForegroundColor White
Write-Host "==============================================================================" -ForegroundColor Green
