from __future__ import annotations

import sys
import ctypes
from pathlib import Path

import webview

from edefter_denetim.app_paths import get_user_data_root
from edefter_denetim.desktop.bridge import DesktopApi
from edefter_denetim.log_utils import install_exception_hooks, setup_logging


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]


def frontend_dist_index(root: Path) -> Path:
    frozen_path = root / "_internal" / "frontend_dist" / "index.html"
    if frozen_path.exists():
        return frozen_path
    return root / "frontend" / "dist" / "index.html"


def has_dev_server() -> bool:
    try:
        import urllib.request

        with urllib.request.urlopen("http://127.0.0.1:5173", timeout=0.4) as response:
            return response.status == 200
    except Exception:
        return False


def resolve_start_url(root: Path) -> str:
    if has_dev_server():
        return "http://127.0.0.1:5173"
    dist_index = frontend_dist_index(root)
    if dist_index.exists():
        return dist_index.as_uri()
    return "data:text/html,<h1>Frontend derlenmedi</h1><p>frontend klasorunde npm install ve npm run build calistirin.</p>"


def resolve_launch_xml_path() -> Path | None:
    if len(sys.argv) < 2:
        return None
    candidate = Path(sys.argv[1]).expanduser()
    if not candidate.exists():
        return None
    if candidate.suffix.lower() != ".xml":
        return None
    return candidate.resolve()


def main() -> int:
    root = project_root()
    data_root = get_user_data_root()
    data_root.mkdir(parents=True, exist_ok=True)
    logger = setup_logging(data_root)
    install_exception_hooks(logger)
    logger.info("Masaustu uygulamasi baslatildi.")
    start_url = resolve_start_url(root)
    logger.info("Arayuz kaynagi: %s", start_url)
    launch_xml_path = resolve_launch_xml_path()
    if launch_xml_path:
        logger.info("Acilista XML dosyasi algilandi: %s", launch_xml_path)
    api = DesktopApi(data_root, launch_xml_path=launch_xml_path)
    user32 = ctypes.windll.user32
    screen_width = max(int(user32.GetSystemMetrics(0)) - 80, 1280)
    screen_height = max(int(user32.GetSystemMetrics(1)) - 100, 760)
    webview.create_window(
        title="e-Defter Denetim Merkezi",
        url=start_url,
        js_api=api,
        min_size=(820, 640),
        width=screen_width,
        height=screen_height,
    )
    webview.start(
        debug=not getattr(sys, "frozen", False),
        http_server=not start_url.startswith("http://127.0.0.1:5173"),
        private_mode=False,
    )
    logger.info("Masaustu uygulamasi kapandi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
