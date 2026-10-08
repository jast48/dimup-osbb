@echo off
chcp 65001 > nul
cls
echo ============================================================
echo   DimUp Smart OSBB - Хостинг Сайту та Публічний Тунель
echo ============================================================
echo.
echo [1/2] Запуск локального веб-сервера на порту 8000...
start "DimUp Web Server" .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

timeout /t 3 > nul

echo [2/2] Запуск публічного Cloudflare тунелю...
start "DimUp Cloudflare Tunnel" cloudflared.exe tunnel --url http://127.0.0.1:8000

echo.
echo ============================================================
echo   Хостинг успішно активний!
echo   Локальний сайт: http://localhost:8000/
echo   Публічне посилання формується у вікні тунелю.
echo ============================================================
echo.
pause
