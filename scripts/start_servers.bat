@echo off
echo =========================================================================
echo  TRACE: AI-Powered CI/CD Log Intelligence Platform (Review-1 Demo)
echo  The National Institute of Engineering, Mysore - Department of ISE
echo  Batch B9 - Course Code: BIS785
echo =========================================================================
echo.

set ROOT_DIR=%~dp0..

echo [1/2] Launching FastAPI Backend on http://localhost:8000 ...
start "TRACE - FastAPI Backend" cmd /k "cd /d "%ROOT_DIR%\backend" && "..\.venv\Scripts\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"

echo [2/2] Launching React Frontend Dashboard on http://localhost:3000 ...
start "TRACE - React Frontend" cmd /k "cd /d "%ROOT_DIR%\frontend" && npm run dev"

echo.
echo All services launched!
echo - API Documentation: http://localhost:8000/docs
echo - React Dashboard:   http://localhost:3000
echo =========================================================================
