#!/usr/bin/env python3
"""ServiceUP Cross-Platform Build Script

Cross-platform replacement for build_exe.bat
Supports building executables for Windows, macOS, and Linux.
Uses PyInstaller with platform-specific configurations.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional


def get_script_dir() -> Path:
    """Get the directory where this script is located."""
    return Path(__file__).parent.parent.resolve()


def get_app_version() -> str:
    """Get application version from config."""
    try:
        sys.path.insert(0, str(get_script_dir()))
        from config import APP_VERSION
        return APP_VERSION
    except Exception:
        return "unknown"


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
        return True
    except Exception as e:
        print(f"❌ Python not found: {e}")
        return False


def update_pip() -> bool:
    """Update pip to the latest version."""
    print("[1/6] Updating pip...")
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
            print(f"⚠ Warning: pip update failed")
            return True
    except Exception as e:
        print(f"⚠ Warning: pip update error: {e}")
        return True


def install_pyinstaller() -> bool:
    """Install PyInstaller and platform-specific dependencies."""
    print("[2/6] Installing PyInstaller...")
    
    packages = ["pyinstaller>=6.0.0"]
    
    # Platform-specific packages
    if sys.platform == "darwin":  # macOS
        packages.append("pyinstaller-hooks-contrib")
    elif sys.platform == "linux":
        packages.append("pyinstaller-hooks-contrib")
    
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install"] + packages,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0:
            print("✓ PyInstaller installed successfully")
            return True
        else:
            print(f"❌ Failed to install PyInstaller: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Error installing PyInstaller: {e}")
        return False


def cleanup_cache_files(base_dir: Path) -> None:
    """Remove temporary and cache files."""
    print("[3/6] Cleaning temporary files...")
    
    # Remove __pycache__ directories
    for pycache in base_dir.rglob("__pycache__"):
        if pycache.is_dir():
            shutil.rmtree(pycache, ignore_errors=True)
    
    # Remove .pyc and .pyo files
    for pattern in ["*.pyc", "*.pyo"]:
        for file in base_dir.glob(f"**/{pattern}"):
            file.unlink(missing_ok=True)
    
    print("✓ Cleanup completed")


def get_platform_name() -> str:
    """Get platform name for executable."""
    if sys.platform == "win32":
        return "windows"
    elif sys.platform == "darwin":
        return "macos"
    else:
        return "linux"


def get_icon_path(base_dir: Path) -> Optional[Path]:
    """Get icon file path for current platform."""
    icon_paths = [
        base_dir / "gui" / "assets" / "icon.ico",  # Windows
        base_dir / "gui" / "assets" / "icon.icns",  # macOS
        base_dir / "gui" / "assets" / "icon.png",   # Linux/fallback
    ]
    
    for path in icon_paths:
        if path.exists():
            return path
    
    return None


def build_executable(base_dir: Path, output_name: str, target_platform: Optional[str] = None) -> bool:
    """Build executable using PyInstaller.
    
    Args:
        base_dir: Base directory of the project
        output_name: Name of the output executable
        target_platform: Target platform (None for current platform)
    
    Returns:
        bool: True if build successful, False otherwise
    """
    print("[4/6] Creating executable...")
    
    # Determine platform
    platform = target_platform or get_platform_name()
    
    # Icon path
    icon_path = get_icon_path(base_dir)
    
    # Build command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", output_name,
    ]
    
    # Add icon if available
    if icon_path:
        cmd.extend(["--icon", str(icon_path)])
    
    # Platform-specific options
    if platform == "windows":
        cmd.append("--windowed")  # No console window
    elif platform == "macos":
        cmd.extend(["--windowed", "--osx-bundle-identifier", "com.serviceup.app"])
    # Linux: keep console for debugging
    
    # Data files
    data_dirs = [
        ("gui/assets", "gui/assets"),
        ("reports/templates", "reports/templates"),
    ]
    
    for src, dst in data_dirs:
        src_path = base_dir / src
        if src_path.exists():
            separator = ";" if sys.platform == "win32" else ":"
            cmd.extend(["--add-data", f"{src_path}{separator}{dst}"])
    
    # Hidden imports
    hidden_imports = [
        "tkinter",
        "customtkinter",
        "PIL",
        "pypdfium2",
        "qrcode",
        "pydantic",
        "sqlalchemy",
        "flask",
        "reportlab",
    ]
    
    for imp in hidden_imports:
        cmd.extend(["--hidden-import", imp])
    
    # Entry point
    main_py = base_dir / "main.py"
    cmd.append(str(main_py))
    
    # Print command for debugging
    print(f"Running: {' '.join(cmd)}")
    
    # Execute build
    try:
        result = subprocess.run(
            cmd,
            cwd=str(base_dir),
            capture_output=True,
            text=True,
            timeout=600,  # 10 minutes timeout
        )
        
        if result.returncode != 0:
            print(f"❌ Build failed:")
            print(result.stderr)
            return False
        
        print("✓ Build completed successfully")
        return True
        
    except subprocess.TimeoutExpired:
        print("❌ Build timed out (10 minutes)")
        return False
    except Exception as e:
        print(f"❌ Build error: {e}")
        return False


def copy_additional_files(base_dir: Path, dist_dir: Path) -> None:
    """Copy additional files needed at runtime."""
    print("[5/6] Copying additional files...")
    
    # Files/directories to copy
    items_to_copy = [
        "requirements.txt",
        "version.txt",
        "service_center.config",
    ]
    
    for item in items_to_copy:
        src = base_dir / item
        dst = dist_dir / item
        if src.exists() and not dst.exists():
            shutil.copy2(src, dst)
            print(f"  ✓ Copied {item}")
    
    # Create data directory if it doesn't exist
    data_dir = dist_dir / "data"
    data_dir.mkdir(exist_ok=True)
    print("  ✓ Created data directory")
    
    print("✓ Additional files copied")


def create_build_info(dist_dir: Path, platform: str, version: str) -> None:
    """Create build information file."""
    info_file = dist_dir / "BUILD_INFO.txt"
    
    with open(info_file, "w", encoding="utf-8") as f:
        f.write(f"ServiceUP Build Information\n")
        f.write(f"===========================\n\n")
        f.write(f"Version: {version}\n")
        f.write(f"Platform: {platform}\n")
        f.write(f"Python: {sys.version}\n")
        f.write(f"Build Date: {Path.ctime(info_file) if info_file.exists() else 'N/A'}\n\n")
        f.write("Important Notes:\n")
        f.write("- The 'data' folder must be located next to the executable\n")
        f.write("- The 'reports/templates' folder must be present\n")
        f.write("- Ensure all dependencies are installed if running from source\n")


def main(target_platform: Optional[str] = None) -> int:
    """Main entry point.
    
    Args:
        target_platform: Target platform (None for current platform)
                        Supported: 'windows', 'macos', 'linux'
    """
    base_dir = get_script_dir()
    app_version = get_app_version()
    platform_name = target_platform or get_platform_name()
    
    print("=" * 60)
    print("  ServiceUP Project - Cross-Platform Builder")
    print("=" * 60)
    print(f"  Version: v{app_version}")
    print(f"  Target Platform: {platform_name}")
    print(f"  Python: {sys.version.split()[0]}")
    print()
    
    # Check Python version
    if not check_python_version():
        if sys.platform == "win32":
            input("Press Enter to exit...")
        return 1
    
    # Update pip
    if not update_pip():
        return 1
    
    # Install PyInstaller
    if not install_pyinstaller():
        return 1
    
    # Cleanup cache
    cleanup_cache_files(base_dir)
    
    # Determine output name based on platform
    if target_platform == "windows" or (not target_platform and sys.platform == "win32"):
        output_name = "ServiceUP"
        exe_ext = ".exe"
    elif target_platform == "macos" or (not target_platform and sys.platform == "darwin"):
        output_name = "ServiceUP"
        exe_ext = ""
    else:  # linux
        output_name = "ServiceUP"
        exe_ext = ""
    
    # Build executable
    if not build_executable(base_dir, output_name, target_platform):
        print("❌ EXE build error")
        if sys.platform == "win32":
            input("Press Enter to exit...")
        return 1
    
    # Find dist directory
    dist_dir = base_dir / "dist"
    if not dist_dir.exists():
        print("❌ Dist directory not found after build")
        return 1
    
    # Copy additional files
    copy_additional_files(base_dir, dist_dir)
    
    # Create build info
    create_build_info(dist_dir, platform_name, app_version)
    
    # Success message
    exe_path = dist_dir / output_name / output_name
    if sys.platform == "win32":
        exe_path = exe_path.with_suffix(".exe")
    
    print()
    print("=" * 60)
    print("  Build completed successfully!")
    print("=" * 60)
    print()
    print(f"Output: {exe_path}")
    print()
    print("Important:")
    print("- The 'data' folder must be located next to the EXE")
    print("- The 'reports/templates' folder must be present")
    print()
    
    if sys.platform == "win32" and not target_platform:
        input("Press Enter to exit...")
    
    return 0


if __name__ == "__main__":
    # Parse command line arguments
    target = None
    if len(sys.argv) > 1:
        target = sys.argv[1].lower()
        if target not in ["windows", "macos", "linux"]:
            print(f"❌ Unknown platform: {target}")
            print("Usage: python build.py [windows|macos|linux]")
            sys.exit(1)
    
    sys.exit(main(target))
