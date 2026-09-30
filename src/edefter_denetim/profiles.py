from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
import re

from .models import VendorProfile


@dataclass(frozen=True, slots=True)
class ArchiveProfile:
    name: VendorProfile
    ignore_dirs: frozenset[str]
    package_dir_names: frozenset[str]
    system_dirs: frozenset[str]


LUCA_PROFILE = ArchiveProfile(
    name=VendorProfile.LUCA,
    ignore_dirs=frozenset({".silinenler"}),
    package_dir_names=frozenset(),
    system_dirs=frozenset(),
)

ZIRVE_PROFILE = ArchiveProfile(
    name=VendorProfile.ZIRVE,
    ignore_dirs=frozenset(
        {
            ".silinenler",
            "silinenler",
            "zrv_tmp",
            "sonuc",
            "_gibonayliedeftersaklama",
            "eledgersigner",
            "eledgerutils",
            "malimuhurhelper",
            "webservicehelper",
            "xsd",
            "xslt",
            "xsl_2.0",
            "sch",
        }
    ),
    package_dir_names=frozenset({"paketler"}),
    system_dirs=frozenset(
        {
            "eledgersigner",
            "eledgerutils",
            "malimuhurhelper",
            "webservicehelper",
            "xsd",
            "xslt",
            "xsl_2.0",
            "sch",
            "sonuc",
            "_gibonayliedeftersaklama",
        }
    ),
)

GENERIC_PROFILE = ArchiveProfile(
    name=VendorProfile.GENERIC,
    ignore_dirs=frozenset({".silinenler", "silinenler", "__pycache__"}),
    package_dir_names=frozenset({"paketler"}),
    system_dirs=frozenset(),
)

YEAR_RANGE_PATTERN = re.compile(r"\d{2}\.\d{2}\.\d{4}-\d{2}\.\d{2}\.\d{4}")
MONTH_DIR_PATTERN = re.compile(r"^(0[1-9]|1[0-2])$")
VKN_PATTERN = re.compile(r"^\d{10,11}$")


def detect_profile(root_path: Path) -> ArchiveProfile:
    signals = inspect_profile_signals(root_path)
    if signals["zirve"] >= signals["luca"] + 2 and signals["zirve"] >= 3:
        return ZIRVE_PROFILE
    if signals["zirve"] >= signals["luca"] and signals["zirve"] >= 4:
        return ZIRVE_PROFILE
    if signals["luca"] >= signals["zirve"] and signals["luca"] >= 2:
        return LUCA_PROFILE
    return GENERIC_PROFILE


def inspect_profile_signals(root_path: Path) -> dict[str, int]:
    scores = {"luca": 0, "zirve": 0}
    direct_dirs = safe_dirs(root_path)
    direct_names = {item.name.lower() for item in direct_dirs}
    root_name = root_path.name.lower()
    direct_vkn_count = sum(1 for item in direct_dirs if VKN_PATTERN.fullmatch(item.name))
    direct_company_count = sum(
        1
        for item in direct_dirs
        if not VKN_PATTERN.fullmatch(item.name)
        and not YEAR_RANGE_PATTERN.fullmatch(item.name)
        and item.name.lower() not in {".silinenler", "silinenler"}
    )

    if "luca" in root_name:
        scores["luca"] += 4
    if "zirve" in root_name:
        scores["zirve"] += 4
    if direct_vkn_count >= 3 and direct_company_count == 0:
        scores["luca"] += 3
    if direct_vkn_count >= 1 and not root_path.name.isdigit():
        scores["zirve"] += 2
    if direct_company_count >= 3:
        scores["zirve"] += 3

    if root_path.name.isdigit() and any(YEAR_RANGE_PATTERN.fullmatch(item.name) for item in direct_dirs):
        scores["luca"] += 3
    if YEAR_RANGE_PATTERN.fullmatch(root_path.name) and any(MONTH_DIR_PATTERN.fullmatch(item.name) for item in direct_dirs):
        scores["luca"] += 3
    if {"eledgersigner", "eledgerutils", "malimuhurhelper"} & direct_names:
        scores["zirve"] += 4
    if "paketler" in direct_names:
        scores["zirve"] += 3
    if any(item.name.isdigit() for item in direct_dirs):
        scores["luca"] += 2

    company_style_dirs = 0
    nested_vkn_dirs = 0
    month_dirs = 0
    package_dir_hits = 0
    helper_hits = 0

    for top_dir in direct_dirs[:80]:
        child_dirs = safe_dirs(top_dir)
        if child_dirs:
            company_style_dirs += 1
        if YEAR_RANGE_PATTERN.fullmatch(top_dir.name):
            scores["luca"] += 2
        if top_dir.name.isdigit():
            scores["luca"] += 1

        for child_dir in child_dirs[:30]:
            child_name = child_dir.name.lower()
            if VKN_PATTERN.fullmatch(child_dir.name):
                nested_vkn_dirs += 1
            if child_name == "paketler":
                package_dir_hits += 1
            if YEAR_RANGE_PATTERN.fullmatch(child_dir.name):
                scores["luca"] += 1
                for month_dir in safe_dirs(child_dir)[:20]:
                    if MONTH_DIR_PATTERN.fullmatch(month_dir.name):
                        month_dirs += 1
                        if any(sub_dir.name.lower() == "paketler" for sub_dir in safe_dirs(month_dir)):
                            package_dir_hits += 1
            if child_name in ZIRVE_PROFILE.system_dirs:
                helper_hits += 1

    if nested_vkn_dirs and package_dir_hits:
        scores["zirve"] += 4
    if direct_vkn_count >= 1 and package_dir_hits and not root_path.name.isdigit():
        scores["zirve"] += 5
    if direct_vkn_count >= 1 and month_dirs >= 2 and not root_path.name.isdigit():
        scores["zirve"] += 3
    if company_style_dirs and nested_vkn_dirs:
        scores["zirve"] += 2
    if direct_company_count >= 3 and nested_vkn_dirs >= 3:
        scores["zirve"] += 4
    if helper_hits:
        scores["zirve"] += min(helper_hits, 3)
    if month_dirs:
        scores["luca"] += min(month_dirs, 3)

    deep_scan_scores = inspect_deep_signals(root_path)
    scores["luca"] += deep_scan_scores["luca"]
    scores["zirve"] += deep_scan_scores["zirve"]

    return scores


def safe_dirs(path: Path) -> list[Path]:
    try:
        return [item for item in path.iterdir() if item.is_dir()]
    except (OSError, PermissionError):
        return []


def inspect_deep_signals(root_path: Path, max_depth: int = 4) -> dict[str, int]:
    scores = {"luca": 0, "zirve": 0}
    start_depth = len(root_path.parts)
    month_hits = 0
    helper_hits = 0
    package_hits = 0
    range_hits = 0
    vkn_hits = 0

    for current_root, dir_names, _ in os.walk(root_path):
        current_path = Path(current_root)
        relative_depth = len(current_path.parts) - start_depth
        if relative_depth > max_depth:
            dir_names[:] = []
            continue

        lowered_dirs = [name.lower() for name in dir_names]
        if VKN_PATTERN.fullmatch(current_path.name):
            vkn_hits += 1
        if YEAR_RANGE_PATTERN.fullmatch(current_path.name):
            range_hits += 1
        if MONTH_DIR_PATTERN.fullmatch(current_path.name):
            month_hits += 1
        if "paketler" in lowered_dirs:
            package_hits += 1
        helper_hits += sum(1 for name in lowered_dirs if name in ZIRVE_PROFILE.system_dirs)

        if range_hits >= 2 and month_hits >= 2:
            break
        if package_hits >= 2 and helper_hits >= 1:
            break

    if vkn_hits and range_hits:
        scores["luca"] += 2
    if month_hits >= 2:
        scores["luca"] += 2
    if package_hits >= 1:
        scores["zirve"] += 2
    if package_hits >= 2:
        scores["zirve"] += 1
    if helper_hits:
        scores["zirve"] += min(helper_hits, 2)
    return scores


def resolve_profile(profile: VendorProfile, root_path: Path) -> ArchiveProfile:
    if profile is VendorProfile.AUTO:
        return detect_profile(root_path)
    if profile is VendorProfile.LUCA:
        return LUCA_PROFILE
    if profile is VendorProfile.ZIRVE:
        return ZIRVE_PROFILE
    return GENERIC_PROFILE
