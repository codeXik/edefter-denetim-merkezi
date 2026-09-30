from __future__ import annotations

import os
from pathlib import Path


APP_VENDOR = "SkynonLabs"
APP_NAME = "e-Defter Denetim Merkezi"


def get_user_data_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        base_dir = Path(local_app_data)
    else:
        base_dir = Path.home() / "AppData" / "Local"
    return base_dir / APP_VENDOR / APP_NAME


def get_logs_dir() -> Path:
    return get_user_data_root() / "logs"


def get_reports_dir() -> Path:
    return get_user_data_root() / "reports"


def get_scan_cache_dir() -> Path:
    return get_user_data_root() / "scan_cache"
