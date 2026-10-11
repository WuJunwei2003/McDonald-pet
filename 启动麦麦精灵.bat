@echo off
chcp 65001 >nul
title McPet
cd /d "%~dp0"

rem -- check if server is already running --
curl -s -o nul -m 2 http://127.0.0.1:8765/api/state
if not errorlevel 1 (
    echo McPet server is already running. Opening browser...
    start "" http://127.0.0.1:8765/
    timeout /t 2 >nul
    exit /b
)

echo.
echo  ==================================================
echo   McPet server starting...
echo   Browser will open automatically.
echo   KEEP THIS WINDOW OPEN while playing.
echo   Close this window to stop the server.
echo  ==================================================
echo.
py app.py
if errorlevel 1 python app.py
echo.
echo [server stopped]
pause
