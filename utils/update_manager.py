"""utils/update_manager.py — авто-обновление ServiceUP через GitHub Releases.

Портировано с того же подхода, что в проекте-эталоне (finance_calculator,
utils/update_manager.py -> updater.py там): раньше здесь была наивная
реализация — GitHub API (лимит 60 запросов/час на IP), скачивание zipball
исходников, замена файлов простым copytree и перезапуск через отдельный
процесс apply_update.py — без проверки целостности, без бэкапа, без поддержки
frozen-бинарника (сборка through PyInstaller не имела сценария
самообновления вообще).

Отвечает за:
- запрос к GitHub за более новой версией (releases.atom — без лимита API,
  api.github.com — фолбэк);
- скачивание ZIP (исходники) или бинарника (frozen) обновления с прогрессом;
- проверку целостности по SHA256 (сверка с <asset>.sha256 из релиза);
- применение обновления — copytree поверх (из исходников) или подмена .exe +
  перезапуск (frozen, main.py подхватывает после);
- откат при ошибке (бэкап БД + конфига перед установкой);
- перезапуск приложения после установки.

Зависимости: packaging>=23.0 (сравнение версий по PEP 440), certifi (CA-бандл
для HTTPS из frozen-сборки, если системный стор недоступен).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

REPO_OWNER = "LgbtBsod"
REPO_NAME = "ServiceUPalphabettagammajopa"
APP_NAME = "ServiceUP"


def _build_ssl_context() -> ssl.SSLContext | None:
    """TLS-контекст на CA-бандле certifi, либо None (дефолт urlopen).

    Frozen PyInstaller .exe не всегда видит системное хранилище доверия так,
    как это делает дефолтный контекст интерпретатора — устаревший Windows-
    стор или машина без доверенных якорей всплывают тут как
    SSLCertVerificationError внутри обычного URLError, неотличимого от «нет
    интернета». certifi — стандартное решение для frozen-Python."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return None


# Что не переносить при обновлении из исходников — пользовательские данные и
# рантайм-мусор, а не код приложения.
SKIP_PATTERNS = {
    "venv", ".venv", ".git", "__pycache__", "data", "backups",
    "service_center.db", "service_center.config", ".license", ".env",
}
SKIP_EXTENSIONS = {".pyc", ".pyo", ".tmp"}

_EXE_MAGIC: dict[str, tuple[bytes, ...]] = {
    "win32": (b"MZ",),
    "linux": (b"\x7fELF",),
    "darwin": (
        b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf",
        b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe",
        b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca",
    ),
}


def normalize_version(raw: str) -> str:
    """Срезать префикс тега (v/v./V.) и пунктуацию: v.1.0.0.b -> 1.0.0.b."""
    return str(raw).strip().lstrip("vV").strip(". \t\r\n")


def get_current_version() -> str:
    """Текущая версия — читает через config.settings (SSOT: version.txt,
    см. config/settings.py::_read_version_file)."""
    try:
        from config.settings import get_version

        return get_version()
    except Exception:
        return "0.0.0"


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _app_dir() -> Path:
    """Каталог, ГДЕ ЛЕЖАТ ДАННЫЕ — то же самое место, что и
    config.settings._writable_root() (data/, backups/, service_center.config).

    Раньше здесь ошибочно был "рядом с исполняемым .exe"
    (Path(sys.executable).parent) — для frozen-сборки это НЕ то же место,
    что config._writable_root() (%LOCALAPPDATA%\\ServiceUP): пользователь
    может распаковать .exe куда угодно (Рабочий стол, Program Files),
    а данные всё равно идут в LOCALAPPDATA. С багом бэкап перед
    обновлением (_create_backup) смотрел в пустую папку рядом с .exe и
    ничего не находил — окажись после этого обновление битым, откатывать
    было бы нечего. Найдено живым прогоном собранного .exe (build.py
    --onedir): data/.last_update_check создавался в dist/ServiceUP/data/
    вместо %LOCALAPPDATA%\\ServiceUP\\data\\, где реально лежит БД.

    Файл .exe для swap/relaunch — отдельно, self.current_exe
    (Path(sys.executable) в AutoUpdater.__init__), НЕ этот каталог."""
    if _is_frozen():
        from config import get_data_dir

        return get_data_dir().parent
    return Path(__file__).resolve().parent.parent


@dataclass
class DownloadProgress:
    """Снимок текущей загрузки — передаётся в progress-callback."""

    bytes_downloaded: int = 0
    total_bytes: int = 0
    speed_bps: float = 0.0

    @property
    def percent(self) -> float:
        return self.bytes_downloaded / self.total_bytes * 100 if self.total_bytes else 0.0

    @property
    def is_complete(self) -> bool:
        return self.total_bytes > 0 and self.bytes_downloaded >= self.total_bytes

    @property
    def speed_mbps(self) -> float:
        return self.speed_bps / (1024 * 1024)

    @property
    def formatted_speed(self) -> str:
        if self.speed_bps < 1024:
            return f"{max(self.speed_bps, 0):.0f} Б/с"
        if self.speed_bps < 1024 * 1024:
            return f"{self.speed_bps / 1024:.1f} КБ/с"
        return f"{self.speed_mbps:.2f} МБ/с"


class UpdateError(Exception):
    """Ошибка процесса обновления."""

    def __init__(self, message: str, recoverable: bool = True):
        super().__init__(message)
        self.recoverable = recoverable


class AutoUpdater:
    """Проверяет и применяет обновления приложения."""

    TIMEOUT_API = 5
    TIMEOUT_DOWNLOAD = 120
    CHUNK_SIZE = 8192
    MIN_UPDATE_SIZE = 1024
    MAX_UPDATE_SIZE = 500 * 1024 * 1024

    def __init__(
        self,
        repo_owner: str = REPO_OWNER,
        repo_name: str = REPO_NAME,
        current_version: str | None = None,
    ):
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.current_version = current_version or get_current_version()

        # Discovery — через github.com (releases.atom + прямые download URL),
        # НЕ подпадает под лимит 60 запросов/час api.github.com. API — фолбэк.
        # Обе базы переопределяются env-переменными для тестов/зеркала.
        api_override = os.environ.get("SERVICEUP_UPDATE_API", "").rstrip("/")
        web_override = os.environ.get("SERVICEUP_UPDATE_WEB", "").rstrip("/")
        self.api_url = api_override or f"https://api.github.com/repos/{repo_owner}/{repo_name}"
        self.web_url = web_override or f"https://github.com/{repo_owner}/{repo_name}"

        self.is_frozen = _is_frozen()
        self.app_dir = _app_dir()
        self.current_exe = Path(sys.executable).resolve() if self.is_frozen else None
        self.backup_dir: Path | None = None
        self.progress_callback: Callable[[DownloadProgress], None] | None = None
        self._network_reachable: bool = True
        self._rate_limited: bool = False
        self._last_error: str | None = None
        self._ssl_context = _build_ssl_context()

    # ── HTTP ─────────────────────────────────────────────────────

    def _create_request(self, url: str) -> Request:
        # url всегда строится этим же классом из releases.atom/api.github.com
        # (github.com/api.github.com, releases/download/...), никогда не
        # приходит от пользователя как есть — тот же bandit-аудит, что и на
        # _urlopen() ниже.
        req = Request(url)  # noqa: S310
        req.add_header("User-Agent", f"{APP_NAME}/{self.current_version}")
        return req

    def _urlopen(self, req: Request, timeout: float):
        return urlopen(req, timeout=timeout, context=self._ssl_context)  # noqa: S310 — GitHub URLs only

    def _api_get(self, url: str) -> Any | None:
        try:
            with self._urlopen(self._create_request(url), self.TIMEOUT_API) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code in (403, 429) and exc.headers.get("X-RateLimit-Remaining") == "0":
                self._rate_limited = True
                logger.warning("GitHub API rate limit — проверка обновлений пропущена")
            else:
                logger.debug("API request failed: %s", exc)
            return None
        except (URLError, TimeoutError) as exc:
            self._last_error = str(getattr(exc, "reason", exc))
            logger.debug("Network unreachable: %s", exc)
            self._network_reachable = False
            return None
        except Exception as exc:
            self._last_error = str(exc)
            logger.debug("Unexpected API error: %s", exc)
            self._network_reachable = False
            return None

    def _http_text(self, url: str) -> str | None:
        try:
            with self._urlopen(self._create_request(url), self.TIMEOUT_API) as resp:
                return resp.read().decode("utf-8", "replace")
        except HTTPError as exc:
            if exc.code in (403, 429):
                self._rate_limited = True
            logger.debug("web GET %s failed: %s", url, exc)
        except (URLError, TimeoutError) as exc:
            self._last_error = str(getattr(exc, "reason", exc))
            logger.debug("web GET %s unreachable: %s", url, exc)
            self._network_reachable = False
        except Exception as exc:
            self._last_error = str(exc)
            logger.debug("web GET %s error: %s", url, exc)
        return None

    # ── сравнение версий / ассеты ────────────────────────────────

    @staticmethod
    def _is_newer_version(latest: str, current: str) -> bool:
        """Сравнение по PEP 440 через packaging."""
        from packaging.version import InvalidVersion, Version

        try:
            return Version(normalize_version(latest)) > Version(normalize_version(current))
        except InvalidVersion:
            a, b = latest.strip(), current.strip()
            return a != b and a > b

    def _platform_asset(self) -> str | None:
        """Имя релиз-ассета для этой ОС (совпадает с .github/workflows/build.yml)."""
        if not self.is_frozen:
            return None
        return {
            "win32": f"{APP_NAME}-windows.exe",
            "darwin": f"{APP_NAME}-macos",
        }.get(sys.platform, f"{APP_NAME}-linux")

    def _asset_keywords(self) -> list[str]:
        """Подстроки, опознающие релиз-ассет для этой ОС, лучшая первой."""
        if not self.is_frozen:
            return [".zip"]
        if sys.platform == "win32":
            return ["windows", ".exe"]
        if sys.platform == "darwin":
            return ["macos", "mac", "darwin"]
        return ["linux"]

    # ── Discovery через github.com (без лимита API) ──────────────

    def _atom_tags(self) -> list[str]:
        """Теги релизов из <web>/releases.atom, новейший первым. [] при сбое."""
        xml = self._http_text(f"{self.web_url}/releases.atom")
        if not xml:
            return []
        return list(dict.fromkeys(re.findall(r"/releases/tag/([^\"'<>\s]+)", xml)))

    def _web_asset_url(self, tag: str) -> str | None:
        asset = self._platform_asset()
        return f"{self.web_url}/releases/download/{tag}/{asset}" if asset else None

    def _asset_available(self, url: str) -> bool:
        """True если URL ассета отдаёт реальный файл (а не 404, пока CI грузит)."""
        try:
            req = self._create_request(url)
            req.add_header("Range", "bytes=0-0")
            with self._urlopen(req, self.TIMEOUT_API) as resp:
                return resp.status in (200, 206)
        except HTTPError as exc:
            return exc.code in (200, 206, 416)
        except Exception:
            return False

    def _check_via_web(self) -> tuple[bool, str | None, str | None] | None:
        """Discovery по atom-фиду. None — уйти в API-фолбэк."""
        tags = self._atom_tags()
        if not tags:
            return None
        newer = [t for t in tags if self._is_newer_version(t, self.current_version)]
        if not newer:
            logger.info("Установлена последняя версия (тег: %s)", tags[0])
            return False, tags[0], None
        newest = newer[0]
        url = self._web_asset_url(newest)
        if url and self._asset_available(url):
            logger.info("Доступна новая версия: %s (releases.atom)", newest)
            return True, newest, url
        if not self.is_frozen:
            zipball = f"{self.api_url}/zipball/{newest}"
            logger.info("Доступна новая версия: %s (zipball исходников)", newest)
            return True, newest, zipball
        logger.info("Релиз %s опубликован, но ассет ещё не готов", newest)
        return False, newest, None

    def _resolve_download_url(self, release_info: dict[str, Any]) -> str | None:
        assets = release_info.get("assets") or []
        for keyword in self._asset_keywords():
            for asset in assets:
                name = str(asset.get("name") or "").lower()
                if keyword in name:
                    return asset.get("browser_download_url")
        if not self.is_frozen:
            return release_info.get("zipball_url")
        return None

    def _pick_release(self, releases: list) -> dict[str, Any] | None:
        """Новейший релиз, который бьёт текущую версию И имеет ассет для этой ОС."""
        best: dict[str, Any] | None = None
        best_tag: str | None = None
        for rel in releases:
            if rel.get("draft"):
                continue
            tag = str(rel.get("tag_name") or "").strip()
            if not tag or not self._is_newer_version(tag, self.current_version):
                continue
            if not self._resolve_download_url(rel):
                continue
            if best is None or self._is_newer_version(tag, best_tag or ""):
                best, best_tag = rel, tag
        return best

    def check_for_updates(self) -> tuple[bool, str | None, str | None]:
        """(has_update, latest_version, download_url)."""
        web = self._check_via_web()
        if web is not None:
            return web

        releases = self._api_get(f"{self.api_url}/releases?per_page=20")
        if isinstance(releases, list) and releases:
            chosen = self._pick_release(releases)
            if chosen:
                tag = str(chosen.get("tag_name") or "").strip()
                url = self._resolve_download_url(chosen)
                logger.info("Доступна новая версия: %s", tag)
                return True, tag, url
            newest = str(releases[0].get("tag_name") or "unknown").strip()
            return False, newest, None

        release_info = self._api_get(f"{self.api_url}/releases/latest")
        if release_info:
            latest_version = str(release_info.get("tag_name") or "unknown").strip()
            zip_url = self._resolve_download_url(release_info)
            if zip_url and self._is_newer_version(latest_version, self.current_version):
                return True, latest_version, zip_url
            return False, latest_version, None

        return False, None, None

    # ── скачивание ──────────────────────────────────────────────

    def _download_with_progress(
        self, url: str, dest_path: Path,
        progress_callback: Callable[[DownloadProgress], None] | None = None,
    ) -> tuple[bool, str]:
        try:
            req = self._create_request(url)
            req.add_header("Accept", "application/octet-stream")

            with self._urlopen(req, self.TIMEOUT_DOWNLOAD) as resp:
                total_size = int(resp.getheader("Content-Length", 0))
                downloaded = 0
                start_time = time.monotonic()
                progress = DownloadProgress(total_bytes=total_size)
                last_update_time = start_time

                with open(dest_path, "wb") as dest_file:
                    while chunk := resp.read(self.CHUNK_SIZE):
                        dest_file.write(chunk)
                        downloaded += len(chunk)
                        progress.bytes_downloaded = downloaded

                        now = time.monotonic()
                        if now - last_update_time >= 0.5:
                            elapsed = now - start_time
                            if elapsed > 0:
                                progress.speed_bps = downloaded / elapsed
                            last_update_time = now
                        if progress_callback:
                            progress_callback(progress)

                total_elapsed = time.monotonic() - start_time
                if total_elapsed > 0:
                    progress.speed_bps = downloaded / total_elapsed

                if total_size > 0:
                    if total_size < self.MIN_UPDATE_SIZE:
                        return False, f"Файл обновления слишком мал: {total_size} байт"
                    if total_size > self.MAX_UPDATE_SIZE:
                        return False, f"Файл обновления слишком велик: {total_size} байт"
                    if downloaded != total_size:
                        return False, f"Загрузка не завершена: {downloaded}/{total_size} байт"
                elif downloaded < self.MIN_UPDATE_SIZE:
                    return False, f"Загруженный файл слишком мал: {downloaded} байт"

                logger.info(
                    "Загрузка завершена: %s (%.0f КБ за %s, %.2f МБ/с)",
                    dest_path.name, downloaded / 1024,
                    timedelta(seconds=round(total_elapsed)), progress.speed_mbps,
                )
                return True, ""
        except HTTPError as exc:
            return False, f"HTTP ошибка {exc.code}: {exc.reason}"
        except URLError as exc:
            return False, f"Сетевая ошибка: {exc.reason}"
        except Exception as exc:
            return False, f"Ошибка загрузки: {exc}"

    # ── бэкап / откат ───────────────────────────────────────────

    def _create_backup(self) -> Path | None:
        """Снимок критичных файлов + пользовательской БД перед обновлением."""
        try:
            backup_base = self.app_dir / ".update_backup"
            backup_base.mkdir(parents=True, exist_ok=True)

            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            self.backup_dir = backup_base / f"backup_{stamp}"
            self.backup_dir.mkdir(parents=True, exist_ok=True)

            for fname in ("version.txt", "service_center.config"):
                src = self.app_dir / fname
                if src.exists():
                    shutil.copy2(src, self.backup_dir / fname)

            data_src = self.app_dir / "data"
            if data_src.is_dir():
                shutil.copytree(data_src, self.backup_dir / "data", dirs_exist_ok=True)

            old_backups = sorted(
                (d for d in backup_base.glob("backup_*") if d.is_dir()), key=lambda d: d.name,
            )
            for old in old_backups[:-5]:
                shutil.rmtree(old, ignore_errors=True)

            logger.info("Бэкап перед обновлением создан: %s", self.backup_dir)
            return self.backup_dir
        except Exception as exc:
            logger.warning("Не удалось создать бэкап перед обновлением: %s", exc)
            return None

    def _restore_from_backup(self) -> bool:
        if not self.backup_dir or not self.backup_dir.exists():
            logger.warning("Бэкап для отката недоступен")
            return False
        try:
            for item in self.backup_dir.iterdir():
                if item.is_file():
                    shutil.copy2(item, self.app_dir / item.name)
            data_backup = self.backup_dir / "data"
            if data_backup.is_dir():
                shutil.copytree(data_backup, self.app_dir / "data", dirs_exist_ok=True)
            logger.info("Откат из бэкапа выполнен успешно")
            return True
        except Exception as exc:
            logger.exception("Не удалось выполнить откат из бэкапа: %s", exc)
            return False

    def _cleanup_backup(self) -> None:
        if self.backup_dir and self.backup_dir.exists():
            with contextlib.suppress(Exception):
                shutil.rmtree(self.backup_dir, ignore_errors=True)

    def _calculate_checksum(self, file_path: Path, algorithm: str = "sha256") -> str:
        with open(file_path, "rb") as f:
            return hashlib.file_digest(f, algorithm).hexdigest()

    def _verify_sha256(self, file_path: Path, download_url: str) -> tuple[bool, str]:
        """Сверяет SHA256 скачанного файла с <asset>.sha256 из того же релиза.

        Fail-closed, если файл сумм есть, но хеш не совпал. Отсутствие файла
        сумм НЕ блокирует — исходники (zipball) считать нечем, а старые
        релизы могли не публиковать суммы."""
        base = download_url.split("?", 1)[0]
        if "/releases/download/" not in base:
            return True, "unversioned-source (пропущено)"
        raw = self._http_text(base + ".sha256")
        if not raw:
            return True, "файл сумм недоступен (пропущено)"
        want = raw.split()[0].strip().lower() if raw.split() else ""
        if len(want) != 64:
            return True, "файл сумм повреждён (пропущено)"
        got = self._calculate_checksum(file_path).lower()
        if got != want:
            logger.error("Несовпадение SHA256: получено %s… ожидалось %s…", got[:16], want[:16])
            return False, f"получено {got[:12]} != ожидалось {want[:12]}"
        return True, f"проверено {got[:16]}…"

    # ── установка (из исходников) ──────────────────────────────

    def _find_source_root(self, extracted_dir: Path) -> Path:
        for candidate in sorted(extracted_dir.iterdir(), key=lambda p: p.name.lower()):
            if candidate.is_dir():
                return candidate
        return extracted_dir

    def _copy_update_files(self, source_folder: Path) -> int:
        files_copied = 0
        for item in source_folder.rglob("*"):
            if not item.is_file():
                continue
            rel = item.relative_to(source_folder)
            parts = rel.parts
            if any(p.startswith(".") for p in parts):
                continue
            if any(p in SKIP_PATTERNS for p in parts):
                continue
            if item.suffix.lower() in SKIP_EXTENSIONS:
                continue
            dest = self.app_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(item, dest)
                files_copied += 1
            except PermissionError:
                logger.warning("Пропущен заблокированный файл: %s", rel)
        return files_copied

    def _update_version_file(self, new_version: str) -> None:
        version_file = self.app_dir / "version.txt"
        clean = normalize_version(new_version)
        try:
            version_file.write_text(clean + "\n", encoding="utf-8")
            logger.info("Версия обновлена до %s", clean)
        except Exception as exc:
            logger.warning("Не удалось обновить version.txt: %s", exc)

    # ── установка (frozen: подмена бинарника + перезапуск) ─────

    def _relaunch_after_update(self) -> None:
        if not self.current_exe:
            return
        target = self.current_exe
        staged = target.with_name(target.name + ".updated")
        if not staged.exists():
            return
        if sys.platform == "win32":
            self._relaunch_windows(target, staged)
        else:
            self._relaunch_posix(target, staged)

    def _swap_windows_binary(self, target: Path, staged: Path) -> bool:
        old = target.with_name(target.name + ".old")
        with contextlib.suppress(OSError):
            if old.exists():
                old.unlink()

        renamed = False
        for _ in range(60):
            try:
                target.rename(old)
                renamed = True
                break
            except OSError:
                time.sleep(0.5)
        logger.info("Подмена обновления: переименован запущенный .exe -> .old: %s", renamed)
        if not renamed:
            logger.error("Подмена обновления: не удалось переименовать запущенный .exe")
            return False

        try:
            staged.replace(target)
            logger.info("Подмена обновления: staged-файл перемещён на место")
        except OSError as exc:
            logger.warning("Подмена обновления: move не удался (%s), пробуем copy", exc)
            with contextlib.suppress(OSError):
                shutil.copy2(staged, target)

        if not target.exists():
            try:
                shutil.copy2(old, target)
                logger.error("Подмена НЕ УДАЛАСЬ — восстановлен предыдущий .exe")
                return False
            except OSError as exc:
                logger.critical("Подмена НЕ УДАЛАСЬ, восстановление тоже: %s", exc)
                return False

        with contextlib.suppress(OSError):
            staged.unlink(missing_ok=True)
        return True

    def _relaunch_windows(self, target: Path, staged: Path) -> None:
        if not self._swap_windows_binary(target, staged):
            return
        DETACHED = 0x00000008 | 0x01000000
        for how, argv, flags in (
            ("direct", [str(target), "--no-update"], DETACHED),
            ("explorer", ["explorer.exe", str(target)], 0),
        ):
            try:
                subprocess.Popen(argv, creationflags=flags, close_fds=True)
                logger.info("Перезапуск через %s; выходим.", how)
                return
            except OSError as exc:
                logger.warning("Перезапуск через %s не удался (%s)", how, exc)
        logger.error("Обновление установлено, но перезапуск не удался — запустите вручную.")

    def _relaunch_posix(self, target: Path, staged: Path) -> None:
        try:
            os.replace(staged, target)
            target.chmod(0o755)
            subprocess.Popen(
                [str(target), "--no-update"],
                start_new_session=True, cwd=str(self.app_dir),
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            logger.info("Обновление подменено, новый процесс запущен.")
        except OSError as exc:
            logger.exception("Обновление установлено, но перезапуск не удался (%s)", exc)

    def _stage_and_relaunch(self, new_exe: Path) -> bool:
        try:
            with open(new_exe, "rb") as f:
                head = f.read(4)
        except OSError:
            return False
        magics = _EXE_MAGIC.get(sys.platform)
        if magics and not any(head.startswith(m) for m in magics):
            logger.error("Скачанное обновление — не исполняемый файл %s (начало %r)", sys.platform, head)
            return False

        staged_exe = self.current_exe.with_name(self.current_exe.name + ".updated")
        try:
            shutil.copy2(new_exe, staged_exe)
        except OSError as exc:
            logger.exception("Не удалось подготовить обновление: %s", exc)
            return False
        if not staged_exe.exists() or staged_exe.stat().st_size < self.MIN_UPDATE_SIZE:
            return False
        self._relaunch_after_update()
        return True

    # ── оркестровка ────────────────────────────────────────────

    def download_update(self, download_url: str, latest_version: str) -> bool:
        if not download_url:
            return False

        temp_dir = None
        try:
            self._create_backup()

            temp_base = Path(tempfile.gettempdir()) / "serviceup_update"
            temp_base.mkdir(parents=True, exist_ok=True)
            temp_dir = temp_base / f"update_{normalize_version(latest_version).replace('.', '_')}_{os.getpid()}"
            temp_dir.mkdir(parents=True, exist_ok=True)

            url_path = download_url.lower().split("?", 1)[0]
            is_raw_binary = self.is_frozen and not url_path.endswith((".zip", ".tar.gz", ".tgz"))

            dest_name = "update.exe" if is_raw_binary else "update.zip"
            dest_path = temp_dir / dest_name
            logger.info("Загрузка обновления из %s", download_url)

            success, error_msg = self._download_with_progress(
                download_url, dest_path, self.progress_callback
            )
            if not success:
                raise UpdateError(f"Загрузка не удалась: {error_msg}", recoverable=True)
            if not dest_path.exists() or dest_path.stat().st_size < self.MIN_UPDATE_SIZE:
                raise UpdateError("Загруженный файл пуст или отсутствует", recoverable=True)

            ok, detail = self._verify_sha256(dest_path, download_url)
            if not ok:
                self._restore_from_backup()
                raise UpdateError(f"Проверка контрольной суммы не прошла ({detail})", recoverable=False)
            logger.info("Проверка SHA256: %s", detail)

            if is_raw_binary:
                result = self._stage_and_relaunch(dest_path)
                if result:
                    logger.info("Обновление исполняемого файла подготовлено: %s", latest_version)
                    self._cleanup_backup()
                else:
                    self._restore_from_backup()
                return result

            extracted_dir = temp_dir / "extracted"
            extracted_dir.mkdir(parents=True, exist_ok=True)
            try:
                with zipfile.ZipFile(dest_path, "r") as zf:
                    bad_file = zf.testzip()
                    if bad_file is not None:
                        raise UpdateError(f"Повреждённый элемент ZIP: {bad_file}", recoverable=False)
                    zf.extractall(extracted_dir)
            except zipfile.BadZipFile as exc:
                raise UpdateError(f"Некорректный ZIP-архив: {exc}", recoverable=False) from exc

            source_folder = self._find_source_root(extracted_dir)
            result = self._copy_update_files(source_folder) > 0
            self._update_version_file(latest_version)

            if result:
                logger.info("Обновление установлено: %s", latest_version)
                self._cleanup_backup()
            else:
                logger.warning("Установка обновления не внесла изменений")
                self._restore_from_backup()
            return result

        except UpdateError as exc:
            logger.exception("Ошибка обновления: %s", exc)
            if exc.recoverable:
                self._restore_from_backup()
            return False
        except Exception as exc:
            logger.exception("Непредвиденная ошибка обновления: %s", exc)
            self._restore_from_backup()
            return False
        finally:
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

    def run_update_check(self, auto: bool = False) -> bool:
        logger.info("Проверка обновлений (текущая версия: %s)", self.current_version)
        has_update, latest_version, download_url = self.check_for_updates()

        if not has_update:
            if not self._rate_limited and self._network_reachable:
                logger.info("Установлена последняя версия (текущая: %s)", self.current_version)
            return False

        if auto and download_url:
            logger.info("Новая версия %s — загрузка...", latest_version)
            return self.download_update(download_url, latest_version)

        logger.info(
            "Версия %s доступна (текущая: %s). Требуется перезапуск для установки.",
            latest_version, self.current_version,
        )
        return False


# ── публичный API для startup / GUI ─────────────────────────────

_CHECK_INTERVAL_SECONDS = 30 * 60


def _check_stamp_path() -> Path:
    return _app_dir() / "data" / ".last_update_check"


def _recently_checked() -> bool:
    """True если проверка уже была за последние 30 минут (защита от
    исчерпания лимита GitHub API — 60 запросов/час на IP)."""
    try:
        age = time.time() - _check_stamp_path().stat().st_mtime
        return 0 <= age < _CHECK_INTERVAL_SECONDS
    except OSError:
        return False


def _mark_checked() -> None:
    try:
        p = _check_stamp_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("", encoding="utf-8")
    except OSError:
        pass


def check_updates_at_startup() -> dict[str, Any]:
    """Проверка обновлений при старте приложения — используется main.py.

    Возвращает dict в форме, которую ждёт gui/dialogs/update_dialog.py:
    has_update, current_version, latest_version, release_notes, download_url,
    error. Не чаще раза в 30 минут. Показ диалога — забота main.py, не этой
    функции (раньше был мёртвый параметр show_dialog, ничего не менявший)."""
    result: dict[str, Any] = {
        "has_update": False,
        "current_version": get_current_version(),
        "latest_version": get_current_version(),
        "release_notes": "",
        "download_url": "",
        "error": None,
    }

    if _recently_checked():
        return result

    updater = AutoUpdater(current_version=result["current_version"])
    has_update, latest_version, url = updater.check_for_updates()

    if not updater._rate_limited and updater._network_reachable:
        _mark_checked()

    if updater._rate_limited:
        result["error"] = "GitHub временно ограничивает запросы — попробуйте позже."
        return result
    if not updater._network_reachable:
        result["error"] = f"Сервер обновлений недоступен ({updater._last_error or 'нет сети'})."
        return result

    if has_update and url:
        result["has_update"] = True
        result["latest_version"] = normalize_version(latest_version or "")
        result["download_url"] = url

    return result


__all__ = [
    "REPO_NAME",
    "REPO_OWNER",
    "AutoUpdater",
    "DownloadProgress",
    "UpdateError",
    "check_updates_at_startup",
    "get_current_version",
    "normalize_version",
]
