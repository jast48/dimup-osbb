@echo off
chcp 65001 > nul
cls
echo ===================================================
echo   DimUp Smart OSBB - Starting Bot and WebApp
echo ===================================================
echo.

call .venv\Scripts\activate.bat
python -m app.main
pause
