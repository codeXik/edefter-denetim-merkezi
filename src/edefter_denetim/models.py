from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class VendorProfile(str, Enum):
    AUTO = "auto"
    GENERIC = "generic"
    LUCA = "luca"
    ZIRVE = "zirve"


class SourceType(str, Enum):
    XML = "xml"
    ZIP = "zip"


class DocumentType(str, Enum):
    JOURNAL_BOOK = "JOURNAL_BOOK"
    LEDGER_BOOK = "LEDGER_BOOK"
    INVENTORY_BOOK = "INVENTORY_BOOK"
    JOURNAL_BERAT = "JOURNAL_BERAT"
    LEDGER_BERAT = "LEDGER_BERAT"
    INVENTORY_BERAT = "INVENTORY_BERAT"
    GIB_APPROVED_JOURNAL_BERAT = "GIB_APPROVED_JOURNAL_BERAT"
    GIB_APPROVED_LEDGER_BERAT = "GIB_APPROVED_LEDGER_BERAT"
    GIB_APPROVED_INVENTORY_BERAT = "GIB_APPROVED_INVENTORY_BERAT"
    DEFTER_RAPORU = "DEFTER_RAPORU"
    AGGREGATE_PACKAGE = "AGGREGATE_PACKAGE"
    AUXILIARY = "AUXILIARY"
    UNKNOWN = "UNKNOWN"


@dataclass(slots=True)
class XmlMetadata:
    company_name: str = ""
    identifier: str = ""
    accountant_name: str = ""
    creator: str = ""
    creation_date: str = ""
    signing_time: str = ""
    period_start: str = ""
    period_end: str = ""


@dataclass(slots=True)
class FileRecord:
    file_path: Path
    relative_path: Path
    vendor_profile: VendorProfile
    source_type: SourceType
    document_type: DocumentType
    file_name: str
    extension: str
    size: int
    sha256: str
    company_name_from_path: str = ""
    vkn_from_path: str = ""
    period_label: str = ""
    period_year: int | None = None
    period_month: int | None = None
    is_in_packages_folder: bool = False
    is_in_deleted_folder: bool = False
    is_system_artifact: bool = False
    xml_root_name: str = ""
    parse_status: str = "ok"
    parse_error: str = ""
    package_entries: tuple[str, ...] = ()
    xml_metadata: XmlMetadata = field(default_factory=XmlMetadata)
    canonical_taxpayer_key: str = ""
    canonical_display_name: str = ""
    canonical_official_name: str = ""
    canonical_vkn: str = ""
    canonical_group_kind: str = ""
    canonical_group_label: str = ""
    search_text: str = ""


@dataclass(slots=True)
class PeriodBucket:
    company_key: str
    period_year: int | None
    period_month: int | None
    documents: dict[DocumentType, list[FileRecord]] = field(default_factory=dict)


@dataclass(slots=True)
class TaxpayerSummary:
    taxpayer_key: str
    display_name: str
    official_name: str
    vkn_or_tckn: str
    profile: VendorProfile
    normalized_name: str = ""
    aliases: list[str] = field(default_factory=list)
    accountant_name: str = ""
    search_text: str = ""
    special_case_kind: str = ""
    special_case_label: str = ""
    root_paths: list[str] = field(default_factory=list)
    periods: list[PeriodBucket] = field(default_factory=list)


@dataclass(slots=True)
class ScanLogEntry:
    timestamp: str
    level: str
    message: str
    context: str = ""


@dataclass(slots=True)
class ScanSummary:
    root_path: Path
    profile: VendorProfile
    total_files: int
    scanned_files: int
    skipped_files: int
    period_buckets: list[PeriodBucket]
    taxpayers: list[TaxpayerSummary]
    records: list[FileRecord]
    findings: list[str]
    logs: list[ScanLogEntry]
    scan_started_at: str
    scan_finished_at: str
