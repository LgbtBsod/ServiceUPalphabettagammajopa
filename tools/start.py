#!/usr/bin/env python3
"""ServiceUP Startup Script

Cross-platform replacement for start.bat
Handles Python version check, dependency installation, cleanup, and application launch.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def get_script_dir() -> Path:
    """Get the directory where this script is located."""
    return Path(__file__).parent.parent.resolve()


def check_python_version() -> bool:
    """Check if Python 3.8+ is installed."""
    try:
        result = subprocess.run(
            [sys.executable, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        print(f"✓ Python found: {result.stdout.strip()}")

        # Parse version
        version_str = result.stdout.strip().split()[1]
        major, minor = map(int, version_str.split(".")[:2])

        if major < 3 or (major == 3 and minor < 8):
            print(f"❌ Python 3.8+ required, found {major}.{minor}")
            print("Download from https://www.python.org/downloads/")
            return False

        return True
    except Exception as e:
        print(f"❌ Python not found or error: {e}")
        print("Download from https://www.python.org/downloads/")
        return False


def cleanup_cache_files(base_dir: Path) -> None:
    """Remove temporary and cache files."""
    print("🧹 Cleaning temporary files...")

    # Remove __pycache__ directories
    for pycache in base_dir.rglob("__pycache__"):
        if pycache.is_dir():
            shutil.rmtree(pycache, ignore_errors=True)

    # Remove .pyc and .pyo files
    for pattern in ["*.pyc", "*.pyo"]:
        for file in base_dir.glob(f"**/{pattern}"):
            file.unlink(missing_ok=True)

    print("✓ Cleanup completed")


def update_pip() -> bool:
    """Update pip to the latest version."""
    print("🔄 Updating pip...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "pip"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            print("✓ pip updated successfully")
            return True
        else:
            print(f"⚠ Warning: pip update failed: {result.stderr}")
            return True  # Continue anyway
    except Exception as e:
        print(f"⚠ Warning: pip update error: {e}")
        return True  # Continue anyway


def install_dependencies(base_dir: Path) -> bool:
    """Install dependencies from requirements.txt."""
    print("🔍 Checking dependencies...")
    requirements_file = base_dir / "requirements.txt"

    if not requirements_file.exists():
        print("⚠ requirements.txt not found, skipping dependency installation")
        return True

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(requirements_file)],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0:
            print("✓ Dependencies installed/verified")
            return True
        else:
            print(f"⚠ Warning: Some dependencies may have issues: {result.stderr}")
            return True  # Continue anyway
    except Exception as e:
        print(f"⚠ Warning: Dependency installation error: {e}")
        return True  # Continue anyway


def get_app_version() -> str:
    """Get application version from config."""
    try:
        sys.path.insert(0, str(get_script_dir()))
        from config import APP_VERSION
        return APP_VERSION
    except Exception:
        return "?"


def launch_application(base_dir: Path) -> int:
    """Launch the main application."""
    print("\n🚀 Launching application...\n")

    main_py = base_dir / "main.py"
    if not main_py.exists():
        print(f"❌ main.py not found at {main_py}")
        return 1

    try:
        # Use exec to replace current process (cleaner than subprocess)
        os.execv(sys.executable, [sys.executable, str(main_py)])
    except Exception as e:
        print(f"❌ Error launching application: {e}")
        # Fallback to subprocess
        result = subprocess.run([sys.executable, str(main_py)])
        return result.returncode

    return 0


def main() -> int:
    """Main entry point."""
    base_dir = get_script_dir()

    # Change to script directory
    os.chdir(base_dir)

    # Get version for title
    app_version = get_app_version()
    print("╔══════════════════════════════════════════════╗")
    print(f"║              ServiceUP v{app_version:<10}          ║")
    print("║         УЧЁТ РЕМОНТА ТЕХНИКИ                 ║")
    print("╚══════════════════════════════════════════════╝")
    print()

    # Check Python version
    if not check_python_version():
        if sys.platform == "win32":
            input("Press Enter to exit...")
        return 1

    # Update pip
    update_pip()

    # Cleanup cache
    cleanup_cache_files(base_dir)

    # Install dependencies
    install_dependencies(base_dir)

    # Launch application
    return launch_application(base_dir)


if __name__ == "__main__":
    sys.exit(main())
