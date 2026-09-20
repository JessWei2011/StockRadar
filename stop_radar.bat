@echo off
title Stop StockRadar
cd /d "%~dp0"
echo Stopping StockRadar background service...

if exist "data\radar.pid" (
    for /f "usebackq tokens=*" %%i in ("data\radar.pid") do taskkill /F /PID %%i >nul 2>&1
    del /f /q "data\radar.pid" >nul 2>&1
)

for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8765" ^| findstr "LISTENING"') do taskkill /F /PID %%a >nul 2>&1

echo.
echo ========================================================
echo   [OK] StockRadar service has been stopped.
echo ========================================================
echo.
timeout /t 2 >nul