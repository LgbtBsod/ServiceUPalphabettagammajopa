@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ============================================
echo   ServiceUP Project - EXE Builder
echo ============================================
echo.

REM Переход в директорию скрипта
cd /d "%~dp0"

REM Версия — только из config.APP_VERSION (SSOT), не хардкодить здесь.
REM Раньше было захардкожено "v22.0" и разошлось с реальной версией (23.0),
REM см. AUDIT_REPORT_v25.md.
for /f "delims=" %%v in ('python -c "from config import APP_VERSION; print(APP_VERSION)" 2^>nul') do set APP_VERSION=%%v
if not defined APP_VERSION set APP_VERSION=unknown
echo   Версия: v%APP_VERSION%
echo.

echo [1/5] Обновление pip...
python -m pip install --upgrade pip --quiet
if %errorlevel% neq 0 (
    echo ⚠ Не удалось обновить pip, продолжаем...
)

echo [2/5] Установка PyInstaller...
pip install pyinstaller --quiet
if %errorlevel% neq 0 (
    echo ❌ Ошибка установки PyInstaller
    pause
    exit /b 1
)

echo [3/5] Очистка временных файлов...
for /d %%i in (__pycache__) do rd /s /q "%%i" 2>nul
del /q *.pyc *.pyo 2>nul
echo ✓ Очистка завершена

echo [4/5] Создание EXE файла...
REM Основные параметры:
REM --onefile - один файл
REM --windowed - без консоли
REM --icon - иконка приложения
REM --name - имя выходного файла
REM --add-data - включение данных

set ICON_FILE=gui\assets\icon.ico
if not exist "%ICON_FILE%" set ICON_FILE=

REM Точка входа — main.py в корне проекта (тот же файл, что запускает
REM start.bat). gui/main.py не существует — раньше это было тут указано и
REM ронял сборку на первом же шаге PyInstaller, см. AUDIT_REPORT_v25.md.
REM data;data — ВНИМАНИЕ: упаковывает текущий data/serviceup.db В EXE как
REM есть; если там реальные боевые данные, а не пустой шаблон — перед
REM раздачей EXE стороннему пользователю стоит убедиться, что это не так.
pyinstaller ^
    --onefile ^
    --windowed ^
    --name "ServiceUP" ^
    --icon="%ICON_FILE%" ^
    --add-data "gui/assets;gui/assets" ^
    --add-data "reports/templates;reports/templates" ^
    --add-data "data;data" ^
    --hidden-import=tkinter ^
    --hidden-import=customtkinter ^
    --hidden-import=PIL ^
    --hidden-import=pypdfium2 ^
    --hidden-import=qrcode ^
    --hidden-import=pydantic ^
    --hidden-import=sqlalchemy ^
    main.py

if %errorlevel% neq 0 (
    echo ❌ Ошибка сборки EXE
    echo Проверьте логи выше для деталей
    pause
    exit /b 1
)

echo [5/5] Копирование необходимых файлов...
if exist "dist\ServiceUP.exe" (
    echo ✓ EXE файл успешно создан: dist\ServiceUP.exe
    
    echo.
    echo ============================================
    echo   Сборка завершена успешно!
    echo ============================================
    echo.
    echo Путь к файлу: %cd%\dist\ServiceUP.exe
    echo.
    echo Важно: 
    echo - Папка 'data' должна находиться рядом с EXE
    echo - Папка 'reports/templates' должна быть рядом
    echo.
) else (
    echo ❌ Файл не найден после сборки
    pause
    exit /b 1
)

pause
