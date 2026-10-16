# ==============================================================================
# TRACE Platform - Windows Setup Script
# Automated Log Analysis and Root Cause Detection System using Machine Learning
# ==============================================================================

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host " TRACE Platform: Automated Environment Setup (Windows)" -ForegroundColor Cyan
Write-Host "==============================================================================" -ForegroundColor Cyan

$RootDir = Resolve-Path "$PSScriptRoot\.."
Set-Location $RootDir

# 1. Verify Prerequisites
Write-Host "`n[1/6] Checking system prerequisites..." -ForegroundColor Yellow

# Python
try {
    $pythonVersion = & python --version 2>&1
    Write-Host "  [OK] Python found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "  [ERROR] Python is not installed or not in PATH." -ForegroundColor Red
    Write-Host "  Please install Python 3.11+ from https://www.python.org/downloads/" -ForegroundColor Red
    exit 1
}

# Node.js
try {
    $nodeVersion = & node --version 2>&1
    Write-Host "  [OK] Node.js found: $nodeVersion" -ForegroundColor Green
} catch {
    Write-Host "  [ERROR] Node.js is not installed or not in PATH." -ForegroundColor Red
    Write-Host "  Please install Node.js 18+ from https://nodejs.org/" -ForegroundColor Red
    exit 1
}

# npm
try {
    $npmVersion = & npm --version 2>&1
    Write-Host "  [OK] npm found: $npmVersion" -ForegroundColor Green
} catch {
    Write-Host "  [ERROR] npm is not installed or not in PATH." -ForegroundColor Red
    exit 1
}

# Ollama check (non-blocking)
try {
    $ollamaCheck = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -Method Get -TimeoutSec 2 -ErrorAction SilentlyContinue
    Write-Host "  [OK] Ollama is running at http://localhost:11434" -ForegroundColor Green
} catch {
    Write-Host "  [NOTE] Ollama is not currently running at http://localhost:11434." -ForegroundColor Yellow
    Write-Host "         Stages 1-4 (ML, GNN, RAG) work fully without Ollama." -ForegroundColor Yellow
    Write-Host "         For Stage 5 LLM synthesis, start Ollama and run: ollama pull llama3.2:3b" -ForegroundColor Yellow
}

# 2. Virtual Environment
Write-Host "`n[2/6] Setting up Python virtual environment..." -ForegroundColor Yellow
$venvDir = Join-Path $RootDir ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "  Creating virtual environment at $venvDir ..." -ForegroundColor Gray
    & python -m venv $venvDir
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [ERROR] Failed to create virtual environment (exit code $LASTEXITCODE)." -ForegroundColor Red
        exit $LASTEXITCODE
    }
    Write-Host "  [OK] Virtual environment created." -ForegroundColor Green
} else {
    Write-Host "  [OK] Virtual environment already exists at $venvDir" -ForegroundColor Green
}

# 3. Backend Dependencies
Write-Host "`n[3/6] Installing backend Python dependencies..." -ForegroundColor Yellow
& $venvPython -m pip install --upgrade pip --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [ERROR] Failed to upgrade pip (exit code $LASTEXITCODE)." -ForegroundColor Red
    exit $LASTEXITCODE
}
& $venvPython -m pip install -r (Join-Path $RootDir "backend\requirements.txt")
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [ERROR] Failed to install backend dependencies (exit code $LASTEXITCODE)." -ForegroundColor Red
    exit $LASTEXITCODE
}
Write-Host "  [OK] Backend dependencies installed." -ForegroundColor Green

# 4. Frontend Dependencies
Write-Host "`n[4/6] Installing frontend Node.js dependencies..." -ForegroundColor Yellow
Push-Location (Join-Path $RootDir "frontend")
try {
    & npm install
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [ERROR] Failed to install frontend dependencies (exit code $LASTEXITCODE)." -ForegroundColor Red
        exit $LASTEXITCODE
    }
    Write-Host "  [OK] Frontend dependencies installed." -ForegroundColor Green
} finally {
    Pop-Location
}

# 5. Environment Configuration
Write-Host "`n[5/6] Verifying environment configuration..." -ForegroundColor Yellow
$envFile = Join-Path $RootDir ".env"
$envExample = Join-Path $RootDir ".env.example"
if (-not (Test-Path $envFile) -and (Test-Path $envExample)) {
    Copy-Item $envExample $envFile
    Write-Host "  [OK] Created .env from .env.example" -ForegroundColor Green
} else {
    Write-Host "  [OK] .env configuration present." -ForegroundColor Green
}

# 6. Model & Database Bootstrap
Write-Host "`n[6/6] Bootstrapping database and model artifacts..." -ForegroundColor Yellow
$bootstrapScript = Join-Path $RootDir "scripts\bootstrap_models.py"
& $venvPython $bootstrapScript
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [ERROR] Model & database bootstrap script failed (exit code $LASTEXITCODE)." -ForegroundColor Red
    exit $LASTEXITCODE
}
Write-Host "  [OK] Bootstrap process verified." -ForegroundColor Green

Write-Host "`n==============================================================================" -ForegroundColor Green
Write-Host " TRACE Platform Setup Complete!" -ForegroundColor Green
Write-Host "==============================================================================" -ForegroundColor Green
Write-Host "To launch all services, run:" -ForegroundColor Cyan
Write-Host "  .\scripts\start_trace.ps1" -ForegroundColor White
Write-Host "  OR" -ForegroundColor Cyan
Write-Host "  .\scripts\start_servers.bat" -ForegroundColor White
Write-Host "==============================================================================" -ForegroundColor Green
