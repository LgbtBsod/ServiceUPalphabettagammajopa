@echo off
chcp 65001 >nul
title ServiceUP v15.0 - Сервисный центр

echo ╔══════════════════════════════════════════════╗
echo ║              ServiceUP v15.0                 ║
echo ║         УЧЁТ РЕМОНТА ТЕХНИКИ                 ║
echo ╚══════════════════════════════════════════════╝
echo.

REM Проверка наличия Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python не найден. Установите Python 3.8+
    echo Скачайте с https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Установка зависимостей из requirements.txt
echo 🔍 Проверка зависимостей...
pip install -r "%~dp0requirements.txt" --quiet

echo.
echo 🚀 Запуск приложения...
echo.

python "%~dp0main.py"

if errorlevel 1 (
    echo.
    echo ❌ Произошла ошибка при запуске
    pause
)
