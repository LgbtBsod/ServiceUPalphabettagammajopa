@echo off
chcp 65001 >nul

REM Предпочитаем локальный .venv (уже готовое, проверенное окружение),
REM если он есть - иначе системный "python" из PATH может указывать на
REM несовместимую версию (например pre-release 3.15.0rcN без готовых
REM wheel-пакетов для pydantic-core/watchfiles/pyyaml, чья сборка из
REM исходников требует Visual C++ Build Tools + Rust, которых обычно нет)
REM - тогда pip install из requirements.txt падает и main.py не
REM запускается вообще (живой репорт: "gui не работают" на машине с
REM системным Python 3.15.0rc2).
set "PYTHON_EXE=python"
if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"

REM Проверка наличия Python
"%PYTHON_EXE%" --version >nul 2>&1
if errorlevel 1 goto no_python

REM Переход в директорию скрипта
cd /d "%~dp0"

REM Версия - только из config.APP_VERSION (SSOT), не хардкодить здесь.
REM Раньше было захардкожено "v22.0" и разошлось с реальной версией (23.0),
REM см. AUDIT_REPORT_v25.md.
for /f "delims=" %%v in ('"%PYTHON_EXE%" -c "from config import APP_VERSION; print(APP_VERSION)" 2^>nul') do set APP_VERSION=%%v
if not defined APP_VERSION set APP_VERSION=?

title ServiceUP v%APP_VERSION%

REM ВАЖНО: echo/title здесь намеренно на английском, не на русском —
REM живой репорт пользователя показал, что cmd.exe под "chcp 65001"
REM ломает разбор МНОГОБАЙТНЫХ (кириллица) строк в echo — фрагменты
REM строки начинают восприниматься как отдельные "команды" ("...is not
REM recognized..."), даже без скобочных блоков и даже с BOM в файле;
REM с чистым ASCII та же логика отрабатывает без единой ошибки
REM (проверено локально). Все пользовательские сообщения самого
REM приложения (main.py) при этом остаются на русском как обычно —
REM это ограничение касается только echo/title ЭТОГО bat-файла.
echo ================================================
echo   ServiceUP v%APP_VERSION%
echo ================================================
echo.

REM Обновление pip
echo Updating pip...
"%PYTHON_EXE%" -m pip install --upgrade pip --quiet

REM Очистка временных файлов
echo Cleaning up temp files...
if exist "__pycache__" rmdir /s /q "__pycache__" 2>nul
for /d /r . %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d" 2>nul
del /q /s "*.pyc" 2>nul
del /q /s "*.pyo" 2>nul

REM Установка зависимостей из requirements.txt
echo Checking dependencies...
"%PYTHON_EXE%" -m pip install -r "%~dp0requirements.txt" --quiet
if errorlevel 1 goto pip_fail
goto pip_ok

:pip_fail
echo.
echo Warning: failed to install some dependencies, see output above.
echo Common cause: the system Python is a pre-release version too new
echo for prebuilt wheel packages, and building from source needs
echo Visual C++ Build Tools and Rust.
echo Install a stable Python (3.12 or 3.13) from
echo https://www.python.org/downloads/ and run start.bat again.
echo.

:pip_ok
echo.
echo Starting the application...
echo.

"%PYTHON_EXE%" "%~dp0main.py"
if errorlevel 1 goto run_fail
goto :eof

:run_fail
echo.
echo An error occurred while starting the application.
pause
goto :eof

:no_python
echo Python not found. Install Python 3.12+
echo Download from https://www.python.org/downloads/
pause
exit /b 1
