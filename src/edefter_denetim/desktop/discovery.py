from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path


VKN_PATTERN = re.compile(r"^\d{10,11}$")
YEAR_PATTERN = re.compile(r"^20\d{2}$")
MONTH_PATTERN = re.compile(r"^(0[1-9]|1[0-2])(?:$|[.\-_ ].*)")
DOCUMENT_PATTERN = re.compile(r"(?:^|-)Y(?:B)?-|(?:^|-)K(?:B)?-|GIB-|(?:^|-)DR-", re.IGNORECASE)
IGNORE_NAMES = {
    ".silinenler",
    "silinenler",
    "__pycache__",
    "xslt",
    "xsd",
    "sch",
    "xsl_2.0",
    "eledgersigner",
    "eledgerutils",
    "malimuhurhelper",
    "webservicehelper",
    "sonuc",
    "_gibonayliedeftersaklama",
}
IGNORE_SUBSTRINGS = {
    "silinen",
    "iptal",
    "beyan",
}


@dataclass(slots=True)
class DiscoveryCandidate:
    root_path: Path
    matched_vkn_dirs: int = 0
    matched_year_dirs: int = 0
    matched_month_dirs: int = 0
    matched_document_files: int = 0
    sample_taxpayer_names: set[str] = field(default_factory=set)

    @property
    def confidence_score(self) -> int:
        score = 10
        score += min(self.matched_vkn_dirs * 18, 36)
        score += min(self.matched_year_dirs * 10, 20)
        score += min(self.matched_month_dirs * 3, 18)
        score += min(self.matched_document_files, 20)
        return min(score, 100)

    @property
    def taxpayer_count(self) -> int:
        return max(self.matched_vkn_dirs, len(self.sample_taxpayer_names))

    def to_dict(self) -> dict[str, object]:
        return {
            "klasorYolu": str(self.root_path),
            "guvenSkoru": self.confidence_score,
            "mukellefSayisi": self.taxpayer_count,
            "yilSayisi": self.matched_year_dirs,
            "aySayisi": self.matched_month_dirs,
            "eslesenDosyaSayisi": self.matched_document_files,
            "ornekler": sorted(self.sample_taxpayer_names)[:4],
            "ozet": build_candidate_summary(self),
        }


def discover_archives(start_path: Path, max_depth: int = 6, progress_callback=None, cancel_callback=None) -> list[dict[str, object]]:
    start_path = start_path.resolve()
    candidates: dict[Path, DiscoveryCandidate] = {}
    start_depth = len(start_path.parts)
    scanned_dirs = 0

    for current_root, dir_names, file_names in os.walk(start_path):
        if cancel_callback and cancel_callback():
            raise RuntimeError("DISCOVERY_CANCELLED")
        current_path = Path(current_root)
        scanned_dirs += 1
        relative_depth = len(current_path.parts) - start_depth
        if is_ignored_name(current_path.name):
            dir_names[:] = []
            continue
        dir_names[:] = [name for name in dir_names if not is_ignored_name(name)]
        if relative_depth > max_depth:
            dir_names[:] = []
            continue

        vkn_dirs = [name for name in dir_names if VKN_PATTERN.fullmatch(name)]
        year_dirs = [name for name in dir_names if YEAR_PATTERN.fullmatch(name)]
        month_dirs = [name for name in dir_names if MONTH_PATTERN.match(name)]
        document_hits = [name for name in file_names if DOCUMENT_PATTERN.search(name)]

        if not (vkn_dirs or year_dirs or month_dirs or document_hits):
            continue

        candidate_root = infer_candidate_root(start_path, current_path, dir_names)
        candidate = candidates.setdefault(candidate_root, DiscoveryCandidate(root_path=candidate_root))
        candidate.matched_vkn_dirs += len(vkn_dirs)
        candidate.matched_year_dirs += len(year_dirs)
        candidate.matched_month_dirs += len(month_dirs)
        candidate.matched_document_files += len(document_hits)
        candidate.sample_taxpayer_names.update(vkn_dirs[:3])

        if not vkn_dirs and current_path.name and not YEAR_PATTERN.fullmatch(current_path.name) and not MONTH_PATTERN.match(current_path.name):
            parent_name = current_path.name.strip()
            if parent_name:
                candidate.sample_taxpayer_names.add(parent_name)

        if progress_callback and scanned_dirs % 8 == 0:
            phase_index = 0
            if candidates:
                phase_index = 1
            if any(candidate.matched_month_dirs for candidate in candidates.values()):
                phase_index = 2
            if any(candidate.matched_document_files for candidate in candidates.values()):
                phase_index = 3
            if len(candidates) >= 2:
                phase_index = 4
            progress_callback(
                {
                    "current_path": str(current_path),
                    "scanned_dirs": scanned_dirs,
                    "candidate_count": len(candidates),
                    "phase_index": phase_index,
                }
            )

    consolidated = consolidate_candidates(start_path, list(candidates.values()))
    filtered = [
        candidate.to_dict()
        for candidate in consolidated
        if is_valid_candidate(start_path, candidate, consolidated)
    ]
    filtered.sort(key=lambda item: (-int(item["guvenSkoru"]), -int(item["mukellefSayisi"]), -int(item["eslesenDosyaSayisi"]), item["klasorYolu"]))
    return filtered[:12]


def infer_candidate_root(start_path: Path, current_path: Path, child_dir_names: list[str]) -> Path:
    if any(VKN_PATTERN.fullmatch(name) for name in child_dir_names):
        return current_path
    if VKN_PATTERN.fullmatch(current_path.name):
        parent = current_path.parent
        return parent if parent != start_path.parent else current_path
    if YEAR_PATTERN.fullmatch(current_path.name) and current_path.parent != current_path:
        grand_parent = current_path.parent
        if VKN_PATTERN.fullmatch(grand_parent.name):
            return grand_parent.parent if grand_parent.parent.exists() else grand_parent
        return grand_parent
    return current_path


def build_candidate_summary(candidate: DiscoveryCandidate) -> str:
    parts: list[str] = []
    if candidate.matched_vkn_dirs:
        parts.append(f"{candidate.matched_vkn_dirs} VKN/TCKN klasörü")
    if candidate.matched_year_dirs:
        parts.append(f"{candidate.matched_year_dirs} yıl klasörü")
    if candidate.matched_month_dirs:
        parts.append(f"{candidate.matched_month_dirs} ay klasörü")
    if candidate.matched_document_files:
        parts.append(f"{candidate.matched_document_files} e-Defter dosya eşleşmesi")
    return ", ".join(parts) if parts else "Yapı işareti bulunamadı."


def consolidate_candidates(start_path: Path, candidates: list[DiscoveryCandidate]) -> list[DiscoveryCandidate]:
    current = {candidate.root_path: clone_candidate(candidate) for candidate in candidates}

    while True:
        children_by_parent: dict[Path, list[DiscoveryCandidate]] = {}
        for candidate in current.values():
            if candidate.root_path == start_path:
                continue
            parent = candidate.root_path.parent
            children_by_parent.setdefault(parent, []).append(candidate)

        merge_targets = {
            parent: children
            for parent, children in children_by_parent.items()
            if should_merge_parent(start_path, parent, children)
        }
        if not merge_targets:
            break

        next_current = dict(current)
        for parent, children in merge_targets.items():
            merged = next_current.get(parent, DiscoveryCandidate(root_path=parent))
            for child in children:
                merged.matched_vkn_dirs += child.matched_vkn_dirs
                merged.matched_year_dirs += child.matched_year_dirs
                merged.matched_month_dirs += child.matched_month_dirs
                merged.matched_document_files += child.matched_document_files
                merged.sample_taxpayer_names.update(child.sample_taxpayer_names)
                next_current.pop(child.root_path, None)
            next_current[parent] = merged
        current = next_current

    return sorted(current.values(), key=lambda item: len(item.root_path.parts))


def should_merge_parent(start_path: Path, parent: Path, children: list[DiscoveryCandidate]) -> bool:
    if is_ignored_name(parent.name):
        return False
    if len(children) < 3:
        return False
    if parent == start_path:
        archive_root_children = sum(1 for child in children if looks_like_archive_root(child.root_path))
        return archive_root_children == 0
    child_names = [child.root_path.name for child in children]
    vkn_like = sum(1 for name in child_names if VKN_PATTERN.fullmatch(name))
    business_like = sum(1 for name in child_names if not YEAR_PATTERN.fullmatch(name) and not MONTH_PATTERN.match(name))
    return vkn_like >= 2 or business_like >= 3


def clone_candidate(candidate: DiscoveryCandidate) -> DiscoveryCandidate:
    return DiscoveryCandidate(
        root_path=candidate.root_path,
        matched_vkn_dirs=candidate.matched_vkn_dirs,
        matched_year_dirs=candidate.matched_year_dirs,
        matched_month_dirs=candidate.matched_month_dirs,
        matched_document_files=candidate.matched_document_files,
        sample_taxpayer_names=set(candidate.sample_taxpayer_names),
    )


def is_ignored_name(name: str) -> bool:
    lowered = canonical_name(name)
    return lowered in IGNORE_NAMES or any(part in lowered for part in IGNORE_SUBSTRINGS)


def is_valid_candidate(start_path: Path, candidate: DiscoveryCandidate, all_candidates: list[DiscoveryCandidate]) -> bool:
    if candidate.confidence_score < 25:
        return False
    if is_ignored_name(candidate.root_path.name):
        return False
    if candidate.matched_vkn_dirs == 0 and candidate.matched_month_dirs == 0 and candidate.matched_document_files == 0:
        return False
    if candidate.root_path == start_path and any(
        other.root_path != candidate.root_path and other.root_path.is_relative_to(candidate.root_path)
        and looks_like_archive_root(other.root_path)
        for other in all_candidates
    ):
        return False
    if any(
        other.root_path != candidate.root_path
        and candidate.root_path.is_relative_to(other.root_path)
        and looks_like_archive_root(other.root_path)
        and other.confidence_score >= candidate.confidence_score
        for other in all_candidates
    ):
        return False
    return True


def looks_like_archive_root(path: Path) -> bool:
    lowered = canonical_name(path.name)
    return "edefter" in lowered or "defter" in lowered or "luca" in lowered


def canonical_name(value: str) -> str:
    translation = str.maketrans({
        "ç": "c",
        "ğ": "g",
        "ı": "i",
        "ö": "o",
        "ş": "s",
        "ü": "u",
        "Ç": "c",
        "Ğ": "g",
        "İ": "i",
        "I": "i",
        "Ö": "o",
        "Ş": "s",
        "Ü": "u",
    })
    return value.translate(translation).casefold()
