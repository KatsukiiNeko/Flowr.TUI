"""Versioned JSON persistence with atomic writes.

The config lives in the platform's usual per-user directory.  A damaged file
never stops the app: the loader returns defaults plus a warning, and the next
explicit save replaces it atomically (temporary file + ``os.replace``).
"""

from __future__ import annotations

import json
import os
import platform
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from .settings import Settings

APP_DIR = "bouquet"
FILENAME = "config.json"


def default_config_dir() -> Path:
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "Bouquet"
        return Path.home() / "AppData" / "Roaming" / "Bouquet"
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Bouquet"
    base = os.environ.get("XDG_CONFIG_HOME")
    if base:
        return Path(base) / APP_DIR
    return Path.home() / ".config" / APP_DIR


def default_config_path() -> Path:
    return default_config_dir() / FILENAME


def load_settings(path: Optional[Path] = None) -> Tuple[Settings, List[str]]:
    target = Path(path) if path is not None else default_config_path()
    try:
        text = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return Settings(), []
    except OSError as exc:
        return Settings(), ["could not read %s: %s" % (target, exc)]
    settings, warnings = Settings.from_json_text(text)
    return settings, warnings


def save_settings(settings: Settings, path: Optional[Path] = None) -> Optional[str]:
    """Write settings atomically.  Returns an error string or None."""
    target = Path(path) if path is not None else default_config_path()
    payload = json.dumps(settings.to_dict(), indent=2, sort_keys=True) + "\n"
    directory = target.parent
    temp_name = None
    try:
        directory.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=str(directory), prefix=".config-", suffix=".tmp",
            delete=False,
        )
        temp_name = handle.name
        with handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
        temp_name = None
        try:
            dir_fd = os.open(str(directory), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass
        return None
    except OSError as exc:
        return "could not save %s: %s" % (target, exc)
    finally:
        if temp_name:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
