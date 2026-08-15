#!/bin/bash

# ===================================================
# 🏢 Скрипт запуску системи DimUp OSBB для macOS / Linux
# ===================================================

echo "==================================================="
echo "🏢 Запуск системи DimUp OSBB (Бот + WebApp + AI)"
echo "==================================================="
echo ""

# Перевіряємо чи є віртуальне оточення .venv
if [ ! -d ".venv" ]; then
    echo "📦 Створення віртуального оточення .venv..."
    python3 -m venv .venv
    echo "⬇️ Встановлення необхідних бібліотек..."
    source .venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
else
    source .venv/bin/activate
fi

echo "🚀 Запуск сервера DimUp (FastAPI + Telegram Polling)..."
echo "🌐 WebApp буде доступний локально за адресою: http://localhost:8000/webapp"
echo ""

python3 -m app.main
