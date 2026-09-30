from __future__ import annotations

import hashlib
import json
import os
import re
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from time import perf_counter

from .audit import bucketize, build_findings
from .classifier import (
    classify_document,
    derive_company_name,
    extract_period,
    infer_period_from_path,
    normalize_company_name,
    normalize_search_text,
    path_contains_vkn,
)
from .models import DocumentType, FileRecord, ScanLogEntry, ScanSummary, SourceType, TaxpayerSummary, VendorProfile, XmlMetadata
from .profiles import resolve_profile
from .xml_reader import extract_xml_payload


SUPPORTED_EXTENSIONS = {".xml", ".zip", ".xslt", ".xsd", ".sch"}
DATE_RANGE_PATTERN = re.compile(r"^(?P<start>\d{2}\.\d{2}\.\d{4})-(?P<end>\d{2}\.\d{2}\.\d{4})$")


def fast_file_signature(path: Path, *, size: int, mtime_ns: int) -> str:
    payload = f"{path.name}|{size}|{mtime_ns}".encode("utf-8", errors="ignore")
    return hashlib.blake2b(payload, digest_size=12).hexdigest()


def inspect_zip(path: Path) -> tuple[tuple[str, ...], str]:
    try:
        with zipfile.ZipFile(path) as archive:
            names = tuple(name for name in archive.namelist() if not name.endswith("/"))
            if not names:
                return (), "ZIP has no file entries"
            return names, ""
    except Exception as exc:  # noqa: BLE001
        return (), str(exc)


def iter_archive_files(
    root_path: Path,
    ignored_names: frozenset[str],
    skipped_dir_names: frozenset[str],
    package_dir_names: frozenset[str],
    search_roots: list[Path] | None = None,
):
    ignored = {name.lower() for name in ignored_names | skipped_dir_names | package_dir_names}
    roots_to_scan = search_roots or [root_path]
    seen_files: set[Path] = set()
    for scan_root in roots_to_scan:
        if not scan_root.exists():
            continue
        for current_root, dir_names, file_names in os.walk(scan_root, topdown=True):
            dir_names[:] = [
                name
                for name in dir_names
                if name.lower() not in ignored and "silinen" not in name.lower() and "iptal" not in name.lower()
            ]
            current_path = Path(current_root)
            for file_name in file_names:
                path = current_path / file_name
                if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue
                resolved = path.resolve()
                if resolved in seen_files:
                    continue
                seen_files.add(resolved)
                yield path


def first_non_empty(values: list[str]) -> str:
    for value in values:
        if value:
            return value
    return ""


def most_common(values: list[str]) -> str:
    filtered = [value for value in values if value]
    if not filtered:
        return ""
    return Counter(filtered).most_common(1)[0][0]


def extract_archive_root_info(record: FileRecord) -> dict[str, object] | None:
    for part in record.relative_path.parts:
        match = DATE_RANGE_PATTERN.fullmatch(part)
        if not match:
            continue
        try:
            start = datetime.strptime(match.group("start"), "%d.%m.%Y")
            end = datetime.strptime(match.group("end"), "%d.%m.%Y")
        except ValueError:
            return None
        return {
            "label": part,
            "start": start,
            "end": end,
            "is_partial": not (start.day == 1 and start.month == 1),
        }
    return None


def detect_special_roots(records: list[FileRecord]) -> dict[str, dict[str, str]]:
    roots: dict[str, dict[str, object]] = {}
    full_roots_by_year: dict[int, list[dict[str, object]]] = defaultdict(list)

    for record in records:
        root_info = extract_archive_root_info(record)
        if not root_info:
            continue
        label = str(root_info["label"])
        entry = roots.setdefault(
            label,
            {
                "label": label,
                "start": root_info["start"],
                "end": root_info["end"],
                "is_partial": bool(root_info["is_partial"]),
                "tasfiye_hint": False,
            },
        )
        lowered_path = str(record.file_path).casefold()
        lowered_name = " ".join(
            value.casefold()
            for value in (record.company_name_from_path, record.xml_metadata.company_name, record.file_name)
            if value
        )
        if (
            "tasfiye" in lowered_path
            or "tasfiye" in lowered_name
            or "tas.h" in lowered_path
            or "tas h" in lowered_name
            or "tasf" in lowered_path
            or "tasf" in lowered_name
        ):
            entry["tasfiye_hint"] = True

    for root in roots.values():
        if not root["is_partial"]:
            full_roots_by_year[root["start"].year].append(root)

    special_roots: dict[str, dict[str, str]] = {}
    for root in roots.values():
        if not root["is_partial"]:
            continue
        year = root["start"].year
        matching_full = [
            candidate
            for candidate in full_roots_by_year.get(year, [])
            if candidate["start"] < root["start"]
        ]
        is_tasfiye = bool(root["tasfiye_hint"] or matching_full)
        if is_tasfiye:
            special_roots[root["label"]] = {
                "kind": "tasfiye",
                "label": "Tasfiye",
            }
        else:
            special_roots[root["label"]] = {
                "kind": "kurulus",
                "label": "Dönem İçi Kuruluş",
            }
    return special_roots


def assign_taxpayer_identities(records: list[FileRecord]) -> dict[str, dict[str, object]]:
    groups: dict[str, dict[str, object]] = {}
    id_index: dict[str, list[str]] = {}
    name_index: dict[str, str] = {}

    for index, record in enumerate(records, start=1):
        identifiers = [value for value in (record.xml_metadata.identifier.strip(), record.vkn_from_path.strip()) if value]
        raw_names = [value for value in (record.xml_metadata.company_name.strip(), record.company_name_from_path.strip()) if value]
        normalized_names = [normalize_search_text(value) for value in raw_names if normalize_search_text(value)]
        existing_keys: list[str] = []
        for identifier in identifiers:
            for candidate_key in id_index.get(identifier, []):
                candidate_group = groups.get(candidate_key)
                candidate_names = set(candidate_group.get("normalized_names", set())) if candidate_group else set()
                if not normalized_names or not candidate_names or candidate_names.intersection(normalized_names):
                    existing_keys.append(candidate_key)
        existing_keys.extend(name_index[value] for value in normalized_names if value in name_index)
        taxpayer_key = first_non_empty(existing_keys)
        if not taxpayer_key:
            primary_identifier = first_non_empty(identifiers)
            primary_name = first_non_empty(normalized_names)
            if primary_identifier and primary_name and primary_name != primary_identifier.casefold():
                taxpayer_key = f"{primary_identifier}|{primary_name}"
            else:
                taxpayer_key = primary_identifier or primary_name or f"TAXPAYER-{index:05d}"

        group = groups.setdefault(
            taxpayer_key,
            {
                "records": [],
                "identifiers": set(),
                "raw_names": set(),
                "normalized_names": set(),
                "accountants": set(),
            },
        )
        group["records"].append(record)
        group["identifiers"].update(identifiers)
        group["raw_names"].update(raw_names)
        group["normalized_names"].update(normalized_names)
        if record.xml_metadata.accountant_name:
            group["accountants"].add(record.xml_metadata.accountant_name.strip())
        for identifier in identifiers:
            id_index.setdefault(identifier, [])
            if taxpayer_key not in id_index[identifier]:
                id_index[identifier].append(taxpayer_key)
        for normalized_name in normalized_names:
            name_index[normalized_name] = taxpayer_key

    for taxpayer_key, group in list(groups.items()):
        taxpayer_records = group["records"]
        official_name = most_common([record.xml_metadata.company_name.strip() for record in taxpayer_records])
        display_name = official_name or most_common([normalize_company_name(record.company_name_from_path) for record in taxpayer_records]) or taxpayer_key
        vkn_or_tckn = first_non_empty(sorted(group["identifiers"])) or taxpayer_key
        accountant_name = most_common(list(group["accountants"]))
        special_roots = detect_special_roots(taxpayer_records)

        subgroup_records: dict[str, list[FileRecord]] = defaultdict(list)
        subgroup_meta: dict[str, dict[str, str]] = {}
        for record in taxpayer_records:
            root_info = extract_archive_root_info(record)
            special = special_roots.get(str(root_info["label"])) if root_info else None
            subgroup_key = taxpayer_key
            subgroup_kind = ""
            subgroup_label = ""
            if special and root_info:
                subgroup_key = f"{taxpayer_key}|{special['kind']}|{root_info['label']}"
                subgroup_kind = special["kind"]
                subgroup_label = special["label"]
            subgroup_records[subgroup_key].append(record)
            subgroup_meta[subgroup_key] = {
                "kind": subgroup_kind,
                "label": subgroup_label,
            }

        for subgroup_key, subgroup in subgroup_records.items():
            subgroup_kind = subgroup_meta[subgroup_key]["kind"]
            subgroup_label = subgroup_meta[subgroup_key]["label"]
            subgroup_official_name = most_common([record.xml_metadata.company_name.strip() for record in subgroup]) or official_name or display_name
            subgroup_display_name = subgroup_official_name or display_name
            if subgroup_kind == "tasfiye" and "tasfiye" not in subgroup_display_name.casefold():
                subgroup_display_name = f"{subgroup_display_name} (Tasfiye)"
            normalized_name = normalize_search_text(subgroup_display_name)
            aliases = sorted(
                {
                    value
                    for value in (
                        *group["raw_names"],
                        subgroup_display_name,
                        subgroup_official_name,
                        display_name,
                        official_name,
                        vkn_or_tckn,
                        subgroup_label,
                    )
                    if value
                }
            )
            search_text = normalize_search_text(" ".join([*aliases, accountant_name]))

            groups[subgroup_key] = {
                "records": subgroup,
                "identifiers": set(group["identifiers"]),
                "raw_names": set(group["raw_names"]),
                "normalized_names": {normalized_name},
                "accountants": set(group["accountants"]),
                "display_name": subgroup_display_name,
                "official_name": subgroup_official_name or subgroup_display_name,
                "normalized_name": normalized_name,
                "vkn_or_tckn": vkn_or_tckn,
                "aliases": aliases,
                "accountant_name": accountant_name,
                "search_text": search_text,
                "special_case_kind": subgroup_kind,
                "special_case_label": subgroup_label,
            }

            for record in subgroup:
                record.canonical_taxpayer_key = subgroup_key
                record.canonical_display_name = subgroup_display_name
                record.canonical_official_name = subgroup_official_name or subgroup_display_name
                record.canonical_vkn = vkn_or_tckn
                record.canonical_group_kind = subgroup_kind
                record.canonical_group_label = subgroup_label
                record.search_text = search_text

        if subgroup_records.keys() != {taxpayer_key}:
            groups.pop(taxpayer_key, None)

    return groups


def build_taxpayer_summaries(records: list[FileRecord], buckets: list) -> list[TaxpayerSummary]:
    bucket_map: dict[tuple[str, int | None, int | None], object] = {
        (bucket.company_key, bucket.period_year, bucket.period_month): bucket for bucket in buckets
    }
    identity_groups = assign_taxpayer_identities(records)
    groups: dict[str, list[FileRecord]] = defaultdict(list)
    for record in records:
        if record.period_year is None or record.period_month is None:
            continue
        key = record.canonical_taxpayer_key or record.xml_metadata.identifier or record.vkn_from_path or record.company_name_from_path or "UNKNOWN"
        groups[key].append(record)

    taxpayers: list[TaxpayerSummary] = []
    for taxpayer_key, taxpayer_records in groups.items():
        group = identity_groups.get(taxpayer_key, {})
        display_name = str(group.get("display_name") or taxpayer_records[0].canonical_display_name or taxpayer_key)
        official_name = str(group.get("official_name") or taxpayer_records[0].canonical_official_name or display_name)
        vkn_or_tckn = str(group.get("vkn_or_tckn") or taxpayer_records[0].canonical_vkn or taxpayer_key)
        period_keys = {
            (
                record.canonical_taxpayer_key or record.xml_metadata.identifier or record.vkn_from_path or record.company_name_from_path or "UNKNOWN",
                record.period_year,
                record.period_month,
            )
            for record in taxpayer_records
        }
        taxpayer_buckets = [bucket_map[key] for key in period_keys if key in bucket_map]
        taxpayers.append(
            TaxpayerSummary(
                taxpayer_key=taxpayer_key,
                display_name=display_name,
                official_name=official_name,
                vkn_or_tckn=vkn_or_tckn,
                profile=taxpayer_records[0].vendor_profile,
                normalized_name=str(group.get("normalized_name") or normalize_search_text(display_name)),
                aliases=list(group.get("aliases") or []),
                accountant_name=str(group.get("accountant_name") or ""),
                search_text=str(group.get("search_text") or normalize_search_text(f"{display_name} {vkn_or_tckn}")),
                special_case_kind=str(group.get("special_case_kind") or ""),
                special_case_label=str(group.get("special_case_label") or ""),
                root_paths=sorted({str(record.file_path.parent) for record in taxpayer_records}),
                periods=sorted(taxpayer_buckets, key=lambda item: (item.period_year or 0, item.period_month or 0)),
            )
        )
    return sorted(taxpayers, key=lambda item: item.display_name.casefold())


def build_scan_summary(
    root_path: Path,
    archive_profile: VendorProfile,
    records: list[FileRecord],
    logs: list[ScanLogEntry],
    *,
    total_files: int,
    scanned_files: int,
    skipped_files: int,
    started_at: str,
    started_perf: float,
) -> ScanSummary:
    assign_taxpayer_identities(records)
    period_buckets = bucketize(records)
    taxpayers = build_taxpayer_summaries(records, period_buckets)
    findings = build_findings(period_buckets)
    finished_at = datetime.now().isoformat(timespec="seconds")
    duration_ms = int((perf_counter() - started_perf) * 1000)
    logs.append(
        ScanLogEntry(
            timestamp=finished_at,
            level="INFO",
            message="Tarama tamamlandi.",
            context=f"{len(taxpayers)} mukellef / {len(period_buckets)} donem / {duration_ms} ms",
        )
    )
    return ScanSummary(
        root_path=root_path,
        profile=archive_profile.name,
        total_files=total_files,
        scanned_files=scanned_files,
        skipped_files=skipped_files,
        period_buckets=period_buckets,
        taxpayers=taxpayers,
        records=records,
        findings=findings,
        logs=logs,
        scan_started_at=started_at,
        scan_finished_at=finished_at,
    )


def scan_archive(
    root_path: Path,
    profile: VendorProfile,
    progress_callback=None,
    cancel_callback=None,
    included_years: set[int] | None = None,
    search_roots: list[Path] | None = None,
) -> ScanSummary:
    root_path = root_path.resolve()
    archive_profile = resolve_profile(profile, root_path)
    started_at = datetime.now().isoformat(timespec="seconds")
    started_perf = perf_counter()
    records: list[FileRecord] = []
    logs: list[ScanLogEntry] = []
    total_files = 0
    scanned_files = 0
    skipped_files = 0

    logs.append(ScanLogEntry(timestamp=started_at, level="INFO", message="Klasor taramasi basladi.", context=str(root_path)))

    visited_dirs: set[Path] = set()
    for path in iter_archive_files(
        root_path,
        archive_profile.ignore_dirs,
        archive_profile.system_dirs,
        archive_profile.package_dir_names,
        search_roots=search_roots,
    ):
        if cancel_callback and cancel_callback():
            raise RuntimeError("SCAN_CANCELLED")
        visited_dirs.add(path.parent)
        relative_path = path.relative_to(root_path)
        lower_parts = tuple(part.lower() for part in relative_path.parts)
        extension = path.suffix.lower()
        source_type = SourceType.ZIP if extension == ".zip" else SourceType.XML
        document_type = classify_document(path.name)
        scanned_files += 1
        stat_result = path.stat()

        year, month = extract_period(path.name)
        if year is None or month is None:
            inferred_year, inferred_month = infer_period_from_path(relative_path)
            year = year or inferred_year
            month = month or inferred_month

        if included_years:
            if year is None:
                skipped_files += 1
                continue
            if year not in included_years:
                skipped_files += 1
                continue

        total_files += 1

        xml_root_name = ""
        parse_status = "ok"
        parse_error = ""
        xml_metadata = XmlMetadata()
        package_entries: tuple[str, ...] = ()

        if extension == ".xml":
            xml_root_name, xml_metadata, parse_error = extract_xml_payload(path)
            if parse_error:
                parse_status = "error"
        elif extension == ".zip" and document_type is DocumentType.AGGREGATE_PACKAGE:
            package_entries, parse_error = inspect_zip(path)
            if parse_error:
                parse_status = "warning"

        records.append(
            FileRecord(
                file_path=path,
                relative_path=relative_path,
                vendor_profile=archive_profile.name,
                source_type=source_type,
                document_type=document_type,
                file_name=path.name,
                extension=extension,
                size=stat_result.st_size,
                sha256=fast_file_signature(path, size=stat_result.st_size, mtime_ns=stat_result.st_mtime_ns),
                company_name_from_path=derive_company_name(relative_path),
                vkn_from_path=path_contains_vkn(relative_path.parts),
                period_label=f"{year or '????'}-{month or '??'}",
                period_year=year,
                period_month=month,
                is_in_packages_folder=any(part in archive_profile.package_dir_names for part in lower_parts),
                is_in_deleted_folder=any(part in {".silinenler", "silinenler"} for part in lower_parts),
                is_system_artifact=any(part in archive_profile.system_dirs for part in lower_parts),
                xml_root_name=xml_root_name,
                parse_status=parse_status,
                parse_error=parse_error,
                package_entries=package_entries,
                xml_metadata=xml_metadata,
            )
        )
        if parse_error:
            logs.append(
                ScanLogEntry(
                    timestamp=datetime.now().isoformat(timespec="seconds"),
                    level="WARNING" if parse_status == "warning" else "ERROR",
                    message=f"Dosya islenirken sorun algilandi: {path.name}",
                    context=parse_error,
                )
            )
        if progress_callback and scanned_files % 6 == 0:
            progress_callback(
                {
                    "current_path": str(path),
                    "scanned_files": scanned_files,
                    "total_files": total_files,
                    "visited_dirs": len(visited_dirs),
                    "taxpayer_count": len({record.canonical_taxpayer_key or record.canonical_vkn or record.vkn_from_path or record.company_name_from_path for record in records if record.period_year is not None}),
                    "period_count": len({(record.canonical_taxpayer_key or record.canonical_vkn or record.vkn_from_path or record.company_name_from_path, record.period_year, record.period_month) for record in records if record.period_year is not None and record.period_month is not None}),
                    "phase_index": infer_scan_phase(document_type, scanned_files),
                }
            )

    return build_scan_summary(
        root_path=root_path,
        archive_profile=archive_profile,
        records=records,
        logs=logs,
        total_files=total_files,
        scanned_files=scanned_files,
        skipped_files=skipped_files,
        started_at=started_at,
        started_perf=started_perf,
    )


def infer_scan_phase(document_type: DocumentType, scanned_files: int) -> int:
    if scanned_files < 12:
        return 0
    if document_type in {DocumentType.JOURNAL_BOOK, DocumentType.LEDGER_BOOK, DocumentType.INVENTORY_BOOK}:
        return 1
    if document_type in {
        DocumentType.JOURNAL_BERAT,
        DocumentType.LEDGER_BERAT,
        DocumentType.INVENTORY_BERAT,
        DocumentType.GIB_APPROVED_JOURNAL_BERAT,
        DocumentType.GIB_APPROVED_LEDGER_BERAT,
        DocumentType.GIB_APPROVED_INVENTORY_BERAT,
    }:
        return 2
    if document_type in {DocumentType.AGGREGATE_PACKAGE, DocumentType.DEFTER_RAPORU}:
        return 3
    return 4


def summary_to_dict(summary: ScanSummary) -> dict[str, object]:
    def enum_value(value: object) -> str:
        return str(getattr(value, "value", value))

    return {
        "root_path": str(summary.root_path),
        "profile": enum_value(summary.profile),
        "total_files": summary.total_files,
        "scanned_files": summary.scanned_files,
        "skipped_files": summary.skipped_files,
        "periods": [
            {
                "company_key": bucket.company_key,
                "period_year": bucket.period_year,
                "period_month": bucket.period_month,
                "documents": {enum_value(document_type): len(files) for document_type, files in bucket.documents.items()},
            }
            for bucket in summary.period_buckets
        ],
        "findings": summary.findings,
        "taxpayer_count": len(summary.taxpayers),
        "scan_started_at": summary.scan_started_at,
        "scan_finished_at": summary.scan_finished_at,
    }


def write_json_summary(summary: ScanSummary, target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(summary_to_dict(summary), ensure_ascii=False, indent=2), encoding="utf-8")
