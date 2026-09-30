from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from xml.sax.saxutils import escape

import fitz

from .scanner import summary_to_dict


def export_json_report(summary, rows: list[dict[str, object]], dashboard: dict[str, object], target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target_path = target_dir / f"edefter-raporu-{timestamp}.json"
    payload = {
        "olusturulmaTarihi": datetime.now().isoformat(timespec="seconds"),
        "dashboard": dashboard,
        "donemler": rows,
        "teknikOzet": summary_to_dict(summary),
        "topluKontrol": build_grouped_export_rows(rows),
    }
    import json

    target_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target_path


def export_excel_report(summary, rows: list[dict[str, object]], target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target_path = target_dir / f"edefter-raporu-{timestamp}.xlsx"

    summary_headers = ["Alan", "Değer"]
    summary_rows = [
        ["Arşiv Klasörü", str(summary.root_path)],
        ["Profil", summary.profile.value],
        ["Tarama Başlangıcı", summary.scan_started_at.replace("T", " ")],
        ["Tarama Bitişi", summary.scan_finished_at.replace("T", " ")],
        ["Toplam Dosya", str(summary.total_files)],
        ["İşlenen Dosya", str(summary.scanned_files)],
        ["Atlanan Dosya", str(summary.skipped_files)],
        ["Mükellef Sayısı", str(len({(str(row.get("firma", "")), str(row.get("vkn", "")), str(row.get("yil", ""))) for row in rows}))],
        ["Dönem Sayısı", str(len(rows))],
    ]

    detail_headers = ["Firma", "VKN/TCKN", "Yıl", "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "Müşavir", "Durum"]
    detail_rows = build_grouped_export_rows(rows)

    with ZipFile(target_path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types_xml())
        archive.writestr("_rels/.rels", _root_rels_xml())
        archive.writestr("docProps/app.xml", _app_xml())
        archive.writestr("docProps/core.xml", _core_xml())
        archive.writestr("xl/workbook.xml", _workbook_xml())
        archive.writestr("xl/_rels/workbook.xml.rels", _workbook_rels_xml())
        archive.writestr("xl/styles.xml", _styles_xml())
        archive.writestr("xl/worksheets/sheet1.xml", _worksheet_xml(detail_headers, detail_rows))
        archive.writestr("xl/worksheets/sheet2.xml", _worksheet_xml(summary_headers, summary_rows))
    return target_path


def export_pdf_report(summary, rows: list[dict[str, object]], target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target_path = target_dir / f"edefter-raporu-{timestamp}.pdf"

    doc = fitz.open()
    page = doc.new_page(width=842, height=595)
    font_path = _pick_pdf_font()
    font_name = "F0"
    page.insert_font(fontname=font_name, fontfile=str(font_path))

    grouped_rows = build_grouped_export_rows(rows)
    headers = ["Firma", "VKN/TCKN", "Yıl", "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "Müşavir", "Durum"]
    lines = [
        "e-Defter Denetim Merkezi",
        f"Arşiv Klasörü: {summary.root_path}",
        f"Tarama Bitişi: {summary.scan_finished_at.replace('T', ' ')}",
        f"Mükellef Sayısı: {len(grouped_rows)}",
        f"Dönem Sayısı: {len(rows)}",
        "",
        "Toplu Kontrol",
        " | ".join(headers),
    ]
    lines.extend(" | ".join(row) for row in grouped_rows[:180])

    y = 28
    for index, line in enumerate(lines):
      font_size = 11 if index == 0 else 8
      page.insert_text((20, y), line[:180], fontname=font_name, fontsize=font_size, color=(0, 0, 0))
      y += 10 if index == 0 else 8.6
      if y > 575:
        break

    doc.save(target_path)
    doc.close()
    return target_path


def build_grouped_export_rows(rows: list[dict[str, object]]) -> list[list[str]]:
    grouped: dict[tuple[str, str, str], dict[str, object]] = {}
    month_keys = [f"{month:02d}" for month in range(1, 13)]
    for row in rows:
        key = (str(row.get("firma", "")), str(row.get("vkn", "")), str(row.get("yil", "")))
        current = grouped.setdefault(
            key,
            {
                "firma": key[0],
                "vkn": key[1],
                "yil": key[2],
                "maliMusavir": str(row.get("maliMusavir", "")),
                "durum": "Yeşil",
                "months": {month: "-" for month in month_keys},
            },
        )
        month = str(row.get("ay", ""))
        if month in month_keys:
            current["months"][month] = export_month_mark(row)
        current["durum"] = max_export_status(str(current["durum"]), export_status_label(row))

    def sort_key(item: dict[str, object]) -> tuple[int, str]:
        durum = str(item["durum"])
        rank = 0 if durum == "Kırmızı" else 1 if durum == "Sarı" else 2
        return rank, str(item["firma"]).casefold()

    ordered = sorted(grouped.values(), key=sort_key)
    return [
        [
            str(item["firma"]),
            str(item["vkn"]),
            str(item["yil"]),
            *[str(item["months"][month]) for month in month_keys],
            str(item["maliMusavir"]),
            str(item["durum"]),
        ]
        for item in ordered
    ]


def export_month_mark(row: dict[str, object]) -> str:
    risk = str(row.get("risk", ""))
    if row.get("ozelDurumTipi") or row.get("gecisRolu"):
        return "↔"
    if risk == "OK":
        return "✓"
    if risk in {"LOW", "MEDIUM"}:
        return "!"
    if risk in {"HIGH", "CRITICAL"}:
        return "✕"
    return "-"


def export_status_label(row: dict[str, object]) -> str:
    risk = str(row.get("risk", ""))
    if risk in {"HIGH", "CRITICAL"}:
        return "Kırmızı"
    if row.get("ozelDurumTipi") or row.get("gecisRolu") or risk in {"LOW", "MEDIUM"}:
        return "Sarı"
    return "Yeşil"


def max_export_status(current: str, new: str) -> str:
    order = {"Kırmızı": 3, "Sarı": 2, "Yeşil": 1}
    return current if order.get(current, 0) >= order.get(new, 0) else new


def _pick_pdf_font() -> Path:
    candidates = [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/calibri.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("PDF font bulunamadı.")


def _worksheet_xml(headers: list[str], rows: list[list[str]]) -> str:
    all_rows = [headers, *rows]
    row_xml = []
    for row_index, row in enumerate(all_rows, start=1):
        cells = []
        for col_index, value in enumerate(row, start=1):
            cell_ref = f"{_column_name(col_index)}{row_index}"
            style_index = "1" if row_index == 1 else "0"
            cells.append(f'<c r="{cell_ref}" t="inlineStr" s="{style_index}"><is><t xml:space="preserve">{escape(str(value))}</t></is></c>')
        row_xml.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    dimension = f"A1:{_column_name(len(headers))}{max(len(all_rows), 1)}"
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<dimension ref=\"{dimension}\"/>"
        "<sheetViews><sheetView workbookViewId=\"0\"/></sheetViews>"
        "<sheetFormatPr defaultRowHeight=\"18\"/>"
        "<cols>"
        + "".join(f'<col min="{index}" max="{index}" width="16" customWidth="1"/>' for index in range(1, len(headers) + 1))
        + "</cols>"
        f"<sheetData>{''.join(row_xml)}</sheetData>"
        "<pageMargins left=\"0.5\" right=\"0.5\" top=\"0.75\" bottom=\"0.75\" header=\"0.3\" footer=\"0.3\"/>"
        "</worksheet>"
    )


def _column_name(index: int) -> str:
    name = ""
    current = index
    while current:
        current, remainder = divmod(current - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _content_types_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>
"""


def _root_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
"""


def _app_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>e-Defter Denetim Merkezi</Application>
</Properties>
"""


def _core_xml() -> str:
    created = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:creator>SkynonLabs</dc:creator>
  <cp:lastModifiedBy>SkynonLabs</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{created}</dcterms:modified>
</cp:coreProperties>
"""


def _workbook_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Toplu Kontrol" sheetId="1" r:id="rId1"/>
    <sheet name="Özet" sheetId="2" r:id="rId2"/>
  </sheets>
</workbook>
"""


def _workbook_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>
"""


def _styles_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2">
    <font><sz val="11"/><name val="Calibri"/></font>
    <font><b/><sz val="11"/><name val="Calibri"/></font>
  </fonts>
  <fills count="2">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
  </fills>
  <borders count="1">
    <border><left/><right/><top/><bottom/><diagonal/></border>
  </borders>
  <cellStyleXfs count="1">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>
  </cellStyleXfs>
  <cellXfs count="2">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>
  </cellXfs>
  <cellStyles count="1">
    <cellStyle name="Normal" xfId="0" builtinId="0"/>
  </cellStyles>
</styleSheet>
"""
