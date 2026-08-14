@echo off
chcp 65001 >nul
title ServiceUP v22.0 - Сервисный центр

echo ╔══════════════════════════════════════════════╗
echo ║              ServiceUP v22.0                 ║
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

REM Переход в директорию скрипта
cd /d "%~dp0"

REM Обновление pip
echo 🔄 Обновление pip...
python -m pip install --upgrade pip --quiet

REM Очистка временных файлов
echo 🧹 Очистка временных файлов...
if exist "__pycache__" rmdir /s /q "__pycache__" 2>nul
for /d /r . %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d" 2>nul
del /q /s "*.pyc" 2>nul
del /q /s "*.pyo" 2>nul

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
