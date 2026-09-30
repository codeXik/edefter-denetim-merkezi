from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import shutil
import winreg
from datetime import datetime
from pathlib import Path
from typing import Any

from .app_paths import get_logs_dir, get_user_data_root


LICENSE_FILENAME = "edefter_license.json"
DEMO_USAGE_FILENAME = "edefter_demo_usage.json"
DEMO_LIMIT = 4

_SECRET_PARTS = ("free-edition",)


def _secret_key() -> bytes:
    return "|".join(_SECRET_PARTS).encode("utf-8")


def get_license_path(base_dir: Path) -> Path:
    return get_user_data_root() / LICENSE_FILENAME


def get_demo_usage_path(base_dir: Path) -> Path:
    return get_user_data_root() / DEMO_USAGE_FILENAME


def get_machine_guid() -> str:
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(value).strip()
    except OSError:
        return ""


def build_device_code(base_dir: Path) -> str:
    payload = "|".join(
        [
            get_machine_guid(),
            os.environ.get("COMPUTERNAME", "").strip().upper(),
            str(base_dir).strip().upper(),
        ]
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest().upper()
    return "-".join(digest[index : index + 4] for index in range(0, 20, 4))


def load_license_file(base_dir: Path) -> dict[str, Any] | None:
    target = get_license_path(base_dir)
    if not target.exists():
        return None
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_license_payload(data: dict[str, Any], target_path: Path) -> Path:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return target_path


def save_license_file(base_dir: Path, data: dict[str, Any]) -> Path:
    return save_license_payload(data, get_license_path(base_dir))


def install_license_file(base_dir: Path, source_path: Path) -> dict[str, Any]:
    data = json.loads(source_path.read_text(encoding="utf-8"))
    save_license_file(base_dir, data)
    return data


def _canonical_license_payload(data: dict[str, Any]) -> bytes:
    payload = {
        "licensee": str(data.get("licensee", "")).strip(),
        "mode": str(data.get("mode", "demo")).strip().lower(),
        "device_code": str(data.get("device_code", "")).strip().upper(),
        "issued_at": str(data.get("issued_at", "")).strip(),
        "license_id": str(data.get("license_id", "")).strip(),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_license_payload(data: dict[str, Any]) -> str:
    signature = hmac.new(_secret_key(), _canonical_license_payload(data), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")


def create_license_payload(*, licensee: str, device_code: str, mode: str = "full") -> dict[str, Any]:
    payload = {
        "licensee": licensee.strip(),
        "mode": mode.strip().lower(),
        "device_code": device_code.strip().upper(),
        "issued_at": datetime.now().isoformat(timespec="seconds"),
        "license_id": secrets.token_hex(8).upper(),
    }
    payload["signature"] = sign_license_payload(payload)
    return payload


def verify_license_payload(data: dict[str, Any]) -> bool:
    expected = sign_license_payload(data)
    actual = str(data.get("signature", "")).strip()
    return bool(actual) and hmac.compare_digest(actual, expected)


def _normalize_firm_key(value: str) -> str:
    return str(value or "").strip().upper()


def load_demo_usage(base_dir: Path) -> dict[str, Any]:
    target = get_demo_usage_path(base_dir)
    if not target.exists():
        return {"device_code": "", "firms": []}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return {"device_code": "", "firms": []}
    if not isinstance(data, dict):
        return {"device_code": "", "firms": []}

    firms: list[dict[str, str]] = []
    raw_firms = data.get("firms", [])
    if isinstance(raw_firms, list):
        for item in raw_firms:
            if isinstance(item, dict):
                key = _normalize_firm_key(str(item.get("key") or item.get("firm_key") or ""))
                if not key:
                    continue
                firms.append(
                    {
                        "key": key,
                        "label": str(item.get("label") or item.get("name") or key).strip(),
                        "registered_at": str(item.get("registered_at") or "").strip(),
                    }
                )
            else:
                key = _normalize_firm_key(str(item))
                if key:
                    firms.append({"key": key, "label": key, "registered_at": ""})

    deduped: list[dict[str, str]] = []
    seen_keys: set[str] = set()
    for item in firms:
        key = item["key"]
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(item)

    return {
        "device_code": str(data.get("device_code") or "").strip().upper(),
        "firms": deduped,
    }


def save_demo_usage(base_dir: Path, data: dict[str, Any]) -> Path:
    target = get_demo_usage_path(base_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    firms = []
    for item in data.get("firms", []):
        if not isinstance(item, dict):
            continue
        key = _normalize_firm_key(str(item.get("key") or ""))
        if not key:
            continue
        firms.append(
            {
                "key": key,
                "label": str(item.get("label") or key).strip(),
                "registered_at": str(item.get("registered_at") or "").strip(),
            }
        )
    payload = {
        "device_code": str(data.get("device_code") or "").strip().upper(),
        "firms": firms,
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def register_demo_firms(base_dir: Path, device_code: str, firms: list[tuple[str, str]]) -> dict[str, Any]:
    normalized_device_code = str(device_code or "").strip().upper()
    usage = load_demo_usage(base_dir)
    if normalized_device_code and usage.get("device_code") not in {"", normalized_device_code}:
        usage = {"device_code": normalized_device_code, "firms": []}
    usage["device_code"] = normalized_device_code

    stored_firms = list(usage.get("firms", []))
    known_keys = {_normalize_firm_key(str(item.get("key") or "")) for item in stored_firms if isinstance(item, dict)}
    changed = False

    for firm_key, firm_label in firms:
        key = _normalize_firm_key(firm_key)
        if not key or key in known_keys:
            continue
        if len(stored_firms) >= DEMO_LIMIT:
            break
        stored_firms.append(
            {
                "key": key,
                "label": str(firm_label or key).strip(),
                "registered_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        known_keys.add(key)
        changed = True

    usage["firms"] = stored_firms
    if changed:
        save_demo_usage(base_dir, usage)

    return get_demo_usage_status(
        base_dir,
        normalized_device_code,
        [_normalize_firm_key(firm_key) for firm_key, _ in firms],
    )


def get_demo_usage_status(base_dir: Path, device_code: str = "", current_firm_keys: list[str] | None = None) -> dict[str, Any]:
    usage = load_demo_usage(base_dir)
    normalized_device_code = str(device_code or "").strip().upper()
    if normalized_device_code and usage.get("device_code") not in {"", normalized_device_code}:
        usage = {"device_code": normalized_device_code, "firms": []}

    firms = [item for item in usage.get("firms", []) if isinstance(item, dict)]
    registered_keys = [_normalize_firm_key(str(item.get("key") or "")) for item in firms]
    current_keys = [
        _normalize_firm_key(item)
        for item in (current_firm_keys or [])
        if _normalize_firm_key(item)
    ]
    current_registered = [key for key in current_keys if key in registered_keys]
    used_count = len(registered_keys)
    remaining = max(DEMO_LIMIT - used_count, 0)

    return {
        "device_code": normalized_device_code or str(usage.get("device_code") or "").strip().upper(),
        "limit": DEMO_LIMIT,
        "used_count": used_count,
        "remaining": remaining,
        "archives": registered_keys,
        "firms": firms,
        "registered_keys": registered_keys,
        "current_registered": bool(current_registered),
        "current_registered_count": len(current_registered),
        "is_full": used_count >= DEMO_LIMIT,
        "can_add_current": used_count < DEMO_LIMIT,
    }


def can_scan_archive(base_dir: Path, archive_key: str) -> tuple[bool, dict[str, Any], str]:
    license_state = evaluate_license(base_dir)
    license_state["demo"] = get_demo_usage_status(base_dir, license_state["device_code"])
    return True, license_state, ""


def evaluate_license(base_dir: Path) -> dict[str, Any]:
    device_code = build_device_code(base_dir)
    license_data = load_license_file(base_dir)
    result = {
        "mode": "demo",
        "label": "Demo Modu",
        "valid": False,
        "licensee": "",
        "license_id": "",
        "issued_at": "",
        "device_code": device_code,
        "message": "Demo modu aktif. 4 firma erişim hakkı bulunuyor.",
        "license_path": str(get_license_path(base_dir)),
        "demo": get_demo_usage_status(base_dir, device_code),
    }
    # Ücretsiz sürüm: lisans kontrolü devre dışı, tüm firmalar açık.
    result.update({"mode": "full", "label": "Ücretsiz Sürüm", "valid": True, "licensee": "Ücretsiz Sürüm",
                   "message": "Ücretsiz sürüm. Tüm özellikler açık."})
    return result
    if not verify_license_payload(license_data):
        result["message"] = "Lisans doğrulanamadı."
        return result
    if str(license_data.get("device_code", "")).strip().upper() != device_code:
        result["message"] = "Bu lisans bu bilgisayar için geçerli değildir."
        return result
    if str(license_data.get("mode", "")).strip().lower() != "full":
        result["message"] = "Lisans demo modunda."
        return result
    result.update(
        {
            "mode": "full",
            "label": "Pro Modu",
            "valid": True,
            "licensee": str(license_data.get("licensee", "")).strip(),
            "license_id": str(license_data.get("license_id", "")).strip(),
            "issued_at": str(license_data.get("issued_at", "")).strip(),
            "message": f"Pro Modu aktif. Lisans sahibi: {license_data.get('licensee', '-')}",
            "demo": get_demo_usage_status(base_dir, device_code),
        }
    )
    return result


def copy_license_template(base_dir: Path, target_path: Path) -> Path:
    payload = create_license_payload(licensee="Örnek Kullanıcı", device_code=build_device_code(base_dir))
    target_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target_path


def copy_log_bundle(base_dir: Path, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    for file_name in ("app.log", "debug.log", "error.log"):
        source = get_logs_dir() / file_name
        if source.exists():
            shutil.copy2(source, target_dir / file_name)
    return target_dir
