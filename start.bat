@echo off
chcp 65001 >nul

REM Предпочитаем локальный .venv (уже готовое, проверенное окружение),
REM если он есть — иначе системный "python" из PATH может указывать на
REM несовместимую версию (например pre-release 3.15.0rcN без готовых
REM wheel-пакетов для pydantic-core/watchfiles/pyyaml, чья сборка из
REM исходников требует Visual C++ Build Tools + Rust, которых обычно нет)
REM — тогда pip install из requirements.txt падает и main.py не
REM запускается вообще (живой репорт: "gui не работают" на машине с
REM системным Python 3.15.0rc2).
set "PYTHON_EXE=python"
if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"

REM Проверка наличия Python
"%PYTHON_EXE%" --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python не найден. Установите Python 3.12+
    echo Скачайте с https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Переход в директорию скрипта
cd /d "%~dp0"

REM Версия — только из config.APP_VERSION (SSOT), не хардкодить здесь.
REM Раньше было захардкожено "v22.0" и разошлось с реальной версией (23.0),
REM см. AUDIT_REPORT_v25.md.
for /f "delims=" %%v in ('"%PYTHON_EXE%" -c "from config import APP_VERSION; print(APP_VERSION)" 2^>nul') do set APP_VERSION=%%v
if not defined APP_VERSION set APP_VERSION=?

title ServiceUP v%APP_VERSION% - Сервисный центр

echo ╔══════════════════════════════════════════════╗
echo ║              ServiceUP v%APP_VERSION%                 ║
echo ║         УЧЁТ РЕМОНТА ТЕХНИКИ                 ║
echo ╚══════════════════════════════════════════════╝
echo.

REM Обновление pip
echo 🔄 Обновление pip...
"%PYTHON_EXE%" -m pip install --upgrade pip --quiet

REM Очистка временных файлов
echo 🧹 Очистка временных файлов...
if exist "__pycache__" rmdir /s /q "__pycache__" 2>nul
for /d /r . %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d" 2>nul
del /q /s "*.pyc" 2>nul
del /q /s "*.pyo" 2>nul

REM Установка зависимостей из requirements.txt
echo 🔍 Проверка зависимостей...
"%PYTHON_EXE%" -m pip install -r "%~dp0requirements.txt" --quiet
if errorlevel 1 (
    echo.
    echo ⚠️  Не удалось установить часть зависимостей ^(см. вывод выше^).
    echo    Частая причина — системный Python слишком новая pre-release
    echo    версия ^(например 3.15.0rcN^), для которой ещё нет готовых
    echo    wheel-пакетов, а сборка из исходников требует Visual C++
    echo    Build Tools/Rust. Установите стабильный Python 3.12-3.14 с
    echo    https://www.python.org/downloads/ и запустите start.bat заново.
    echo.
)

echo.
echo 🚀 Запуск приложения...
echo.

"%PYTHON_EXE%" "%~dp0main.py"

if errorlevel 1 (
    echo.
    echo ❌ Произошла ошибка при запуске
    pause
)
