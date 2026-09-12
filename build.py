#!/usr/bin/env python3
"""ServiceUP — сборка standalone-исполняемого файла через PyInstaller.

    python build.py                # onefile-сборка под текущую ОС
    python build.py --onedir       # сборка папкой (быстрее холодный старт)
    python build.py --clean        # сначала стереть build/ и dist/
    python build.py --no-deps      # пропустить установку зависимостей

Вывод:
    Windows : dist/ServiceUP.exe
    Linux   : dist/ServiceUP
    macOS   : dist/ServiceUP

Заменяет tools/build.py и build_exe.bat (оба удалены — build_exe.bat не знал
про APP_VERSION из version.txt, а tools/build.py дублировал ту же логику
отдельным, чуть другим списком hidden-imports; один источник вместо двух,
которые могли разойтись). Имя ассета (ServiceUP-<platform>[.exe]) совпадает с
тем, что ждёт utils/update_manager.py::AutoUpdater._platform_asset() и
.github/workflows/build.yml — если меняешь одно, поменяй оба остальных места.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

# CI Windows-раннеры дают cp1252-консоль -> любой не-ASCII print роняет скрипт
# UnicodeEncodeError. Держим вывод ASCII и на всякий случай переключаем поток.
for _stream in (sys.stdout, sys.stderr):
    with contextlib.suppress(AttributeError, ValueError):
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

APP_DIR = Path(__file__).resolve().parent
NAME = "ServiceUP"

# Рантайм-зависимости — единым списком в requirements.txt (SSOT). Здесь
# только то, что нужно исключительно для сборки.
BUILD_ONLY_DEPS = ["pyinstaller>=6.10,<7"]

HIDDEN_IMPORTS = [
    "tkinter",
    "customtkinter",
    "PIL",
    "pypdfium2",
    "qrcode",
    "pydantic",
    "pydantic_settings",
    "sqlalchemy",
    "flask",
    "reportlab",
    "phonenumbers",
]


def info(m):
    print(f"[INFO] {m}")


def err(m):
    print(f"[ERROR] {m}")


def get_version() -> str:
    try:
        return (APP_DIR / "version.txt").read_text(encoding="utf-8").strip().lstrip("vV")
    except OSError:
        return "unknown"


def install_deps() -> None:
    info("Installing / verifying build dependencies...")
    r = subprocess.run(
        [sys.executable, "-m", "pip", "install",
         "-r", str(APP_DIR / "requirements.txt"), *BUILD_ONLY_DEPS],
        timeout=1200,
    )
    if r.returncode != 0:
        err("Dependency install failed.")
        sys.exit(1)
    probe = subprocess.run(
        [sys.executable, "-c",
         "import customtkinter, flask, pydantic_settings, sqlalchemy, reportlab, PyInstaller"],
        capture_output=True, text=True,
    )
    if probe.returncode != 0:
        err(f"Post-install import check failed:\n{probe.stderr}")
        sys.exit(1)


def main() -> None:
    os.chdir(APP_DIR)
    args = sys.argv[1:]
    onedir = "--onedir" in args

    print("=" * 60)
    print(f"  {NAME} v{get_version()} — PyInstaller "
          f"({sys.platform}, py{sys.version_info.major}.{sys.version_info.minor})")
    print("=" * 60)

    if "--no-deps" not in args:
        install_deps()

    if "--clean" in args:
        for d in ("build", "dist"):
            shutil.rmtree(APP_DIR / d, ignore_errors=True)
        info("Cleaned build/ and dist/")

    sep = os.pathsep
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--name", NAME,
        "--onedir" if onedir else "--onefile",
        "--add-data", f"version.txt{sep}.",
        "--add-data", f"reports/templates{sep}reports/templates",
        "--collect-submodules", "gui",
        "--collect-submodules", "core",
        "--collect-submodules", "database",
        "--collect-submodules", "managers",
        "--collect-submodules", "plugins",
        "--collect-submodules", "reports",
        "--collect-submodules", "domain",
        "--collect-submodules", "pwa",
        "--exclude-module", "matplotlib",
        "--noupx",
    ]
    for imp in HIDDEN_IMPORTS:
        cmd += ["--hidden-import", imp]
    if sys.platform == "win32":
        cmd += ["--windowed"]
    elif sys.platform == "darwin":
        cmd += ["--windowed", "--osx-bundle-identifier", "com.serviceup.app"]
    # Linux: консоль оставляем — там же выводятся сообщения об ошибке
    # лицензии/апдейтера, если что-то пойдёт не так на первом запуске.
    cmd.append("main.py")

    info("Running PyInstaller...")
    print("  " + " ".join(cmd))
    r = subprocess.run(cmd, timeout=2400)
    if r.returncode != 0:
        err("PyInstaller failed.")
        sys.exit(1)

    dist = APP_DIR / "dist"
    try:
        dst = (dist / NAME / "version.txt") if onedir else (dist / "version.txt")
        shutil.copy2(APP_DIR / "version.txt", dst)
    except OSError:
        pass

    ext = ".exe" if sys.platform == "win32" else ""
    exe = (dist / NAME / (NAME + ext)) if onedir else (dist / (NAME + ext))
    print("=" * 60)
    if exe.exists():
        print(f"  BUILD OK -> {exe}   ({exe.stat().st_size / 1e6:.0f} MB)")
    else:
        err("Build finished but no executable found in dist/.")
        sys.exit(1)
    print("  User data (data/, backups/, service_center.config, .license) lives")
    print("  next to the exe / in %LOCALAPPDATA%\\ServiceUP and survives updates.")
    print("=" * 60)


if __name__ == "__main__":
    main()
