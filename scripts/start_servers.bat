@echo off
echo =========================================================================
echo  TRACE: AI-Powered CI/CD Log Intelligence Platform
echo =========================================================================
echo.

set ROOT_DIR=%~dp0..

if not exist "%ROOT_DIR%\.venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found at .venv.
    echo Please run powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
    pause
    exit /b 1
)

if not exist "%ROOT_DIR%\.env" (
    echo [INFO] Copying .env.example to .env ...
    copy "%ROOT_DIR%\.env.example" "%ROOT_DIR%\.env" >nul
)

echo [1/2] Launching FastAPI Backend on http://localhost:8000 ...
start "TRACE - FastAPI Backend" cmd /k "cd /d "%ROOT_DIR%\backend" && "..\.venv\Scripts\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"

echo [2/2] Launching React Frontend Dashboard on http://localhost:3000 ...
start "TRACE - React Frontend" cmd /k "cd /d "%ROOT_DIR%\frontend" && npm run dev"

echo.
echo Verifying service startup...
timeout /t 3 /nobreak >nul
curl -s -f http://localhost:8000/api/v1/health >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [OK] FastAPI backend is live and healthy at http://localhost:8000
) else (
    echo [NOTE] Backend processes initializing; Swagger UI available at http://localhost:8000/docs shortly.
)

echo.
echo =========================================================================
echo  TRACE platform initialized!
echo  - API Documentation: http://localhost:8000/docs
echo  - React Dashboard:   http://localhost:3000
echo =========================================================================
