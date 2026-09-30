from __future__ import annotations

from collections import Counter

from .models import DocumentType, FileRecord, PeriodBucket, SourceType


EXPECTED_CORE_TYPES = {
    DocumentType.JOURNAL_BOOK,
    DocumentType.LEDGER_BOOK,
    DocumentType.JOURNAL_BERAT,
    DocumentType.LEDGER_BERAT,
    DocumentType.GIB_APPROVED_JOURNAL_BERAT,
    DocumentType.GIB_APPROVED_LEDGER_BERAT,
}


def bucketize(records: list[FileRecord]) -> list[PeriodBucket]:
    buckets: dict[tuple[str, int | None, int | None], PeriodBucket] = {}
    for record in records:
        if record.is_system_artifact or record.is_in_deleted_folder:
            continue
        if record.document_type in {DocumentType.AUXILIARY, DocumentType.AGGREGATE_PACKAGE, DocumentType.UNKNOWN}:
            continue
        if record.period_year is None or record.period_month is None:
            continue
        key = (
            record.canonical_taxpayer_key or record.canonical_vkn or record.vkn_from_path or record.company_name_from_path or "UNKNOWN",
            record.period_year,
            record.period_month,
        )
        bucket = buckets.get(key)
        if bucket is None:
            bucket = PeriodBucket(company_key=key[0], period_year=key[1], period_month=key[2])
            buckets[key] = bucket
        bucket.documents.setdefault(record.document_type, []).append(record)
    return sorted(buckets.values(), key=lambda item: (item.company_key, item.period_year or 0, item.period_month or 0))


def build_findings(buckets: list[PeriodBucket]) -> list[str]:
    findings: list[str] = []
    for bucket in buckets:
        types_present = set(bucket.documents)
        missing = EXPECTED_CORE_TYPES - types_present
        prefix = f"{bucket.company_key} {bucket.period_year or '????'}-{bucket.period_month or '??'}"
        for document_type in sorted(missing, key=document_type_name):
            findings.append(f"{prefix}: missing {document_type_name(document_type)}")
        for document_type, docs in bucket.documents.items():
            source_counts = Counter(doc.source_type for doc in docs)
            if source_counts[SourceType.XML] > 1:
                findings.append(f"{prefix}: duplicate XML for {document_type_name(document_type)}")
            if source_counts[SourceType.ZIP] > 1:
                findings.append(f"{prefix}: duplicate ZIP for {document_type_name(document_type)}")
    return findings


def document_type_name(value: object) -> str:
    if hasattr(value, "value"):
        return str(getattr(value, "value"))
    return str(value)
