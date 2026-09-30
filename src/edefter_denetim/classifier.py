from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from pathlib import Path

from .models import DocumentType


PERIOD_PATTERN = re.compile(r"(?<!\d)(?P<year>20\d{2})(?P<month>0[1-9]|1[0-2])(?!\d)")
PERIOD_RANGE_PATTERN = re.compile(r"01[.\-_ ]01[.\-_ ](?P<year>20\d{2})")
VKN_PATTERN = re.compile(r"^\d{10,11}$")


def classify_document(file_name: str) -> DocumentType:
    upper_name = file_name.upper()
    if upper_name in {"YEVMIYELER.ZIP", "KEBIRLER.ZIP", "BERATLAR.ZIP"}:
        return DocumentType.AGGREGATE_PACKAGE
    if upper_name.endswith(".XSLT") or upper_name.endswith(".XSD") or upper_name.endswith(".SCH"):
        return DocumentType.AUXILIARY
    if upper_name.startswith("GIB-") and "-YB-" in upper_name:
        return DocumentType.GIB_APPROVED_JOURNAL_BERAT
    if upper_name.startswith("GIB-") and "-KB-" in upper_name:
        return DocumentType.GIB_APPROVED_LEDGER_BERAT
    if upper_name.startswith("GIB-") and "-EB-" in upper_name:
        return DocumentType.GIB_APPROVED_INVENTORY_BERAT
    if "-DR-" in upper_name:
        return DocumentType.DEFTER_RAPORU
    if "-YB-" in upper_name:
        return DocumentType.JOURNAL_BERAT
    if "-KB-" in upper_name:
        return DocumentType.LEDGER_BERAT
    if "-EB-" in upper_name:
        return DocumentType.INVENTORY_BERAT
    if "-Y-" in upper_name:
        return DocumentType.JOURNAL_BOOK
    if "-K-" in upper_name:
        return DocumentType.LEDGER_BOOK
    if "-E-" in upper_name:
        return DocumentType.INVENTORY_BOOK
    return DocumentType.UNKNOWN


def extract_period(file_name: str) -> tuple[int | None, int | None]:
    match = PERIOD_PATTERN.search(file_name)
    if not match:
        return None, None
    year = int(match.group("year"))
    month = int(match.group("month"))
    return (year, month) if is_valid_period(year, month) else (None, None)


def infer_period_from_path(relative_path: Path) -> tuple[int | None, int | None]:
    path_text = str(relative_path)
    year, month = extract_period(path_text)
    if year and month:
        return year, month

    annual_year = None
    for part in relative_path.parts:
        range_match = PERIOD_RANGE_PATTERN.search(part)
        if range_match:
            candidate_year = int(range_match.group("year"))
            if is_valid_period(candidate_year, 1):
                annual_year = candidate_year
        if part.isdigit() and len(part) == 2:
            month_value = int(part)
            if annual_year and is_valid_period(annual_year, month_value):
                return annual_year, month_value
    return annual_year, None


def is_valid_period(year: int, month: int) -> bool:
    upper_bound = datetime.now().year + 1
    return 2000 <= year <= upper_bound and 1 <= month <= 12


def path_contains_vkn(path_parts: tuple[str, ...]) -> str:
    for part in path_parts:
        if VKN_PATTERN.fullmatch(part):
            return part
    return ""


def normalize_company_name(value: str) -> str:
    return value.replace("_", " ").strip()


def normalize_search_text(value: str) -> str:
    cleaned = normalize_company_name(value)
    if not cleaned:
        return ""
    cleaned = "".join(
        character
        for character in unicodedata.normalize("NFKD", cleaned)
        if not unicodedata.combining(character)
    )
    cleaned = cleaned.casefold()
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def derive_company_name(relative_path: Path) -> str:
    parts = relative_path.parts
    if not parts:
        return ""
    if len(parts) >= 2 and VKN_PATTERN.fullmatch(parts[0]):
        return parts[0]
    if len(parts) >= 3 and VKN_PATTERN.fullmatch(parts[1]):
        return normalize_company_name(parts[0])
    return normalize_company_name(parts[0])
