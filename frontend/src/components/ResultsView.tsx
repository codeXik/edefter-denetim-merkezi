import { useMemo, useState } from "react";
import { SectionSummaryInline } from "./SectionSummaryInline";
import { YearStatusPicker, type YearStatusItem } from "./YearStatusPicker";
import type { DonemKaydi } from "../types";

interface ResultsViewProps {
  rows: DonemKaydi[];
  selectedYear: string;
  yearOptions: number[];
  yearStatuses: YearStatusItem[];
  scanning?: boolean;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onOpenDetail: (id: string) => void;
  onOpenTaxpayerProfile: (firma: string, vkn: string, yil: number) => void;
  onOpenWarnings: () => void;
  donemKarsilastirmaEtiketi?: string;
  onYearChange: (value: string) => void;
  onExportExcel: () => void;
  exporting: "excel" | "pdf" | null;
  statusMessage: string;
}

type DurumFiltresi = "Hepsi" | "Gönderilmiş" | "Gönderilmemiş" | "Hatalı";

interface FirmaSatiri {
  id: string;
  firma: string;
  vkn: string;
  yil: number;
  maliMusavir: string;
  aylar: Array<DonemKaydi | null>;
  ozelDurumTipi: string;
  demoLocked: boolean;
}

const AYLAR = ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"];

export function ResultsView({
  rows,
  selectedYear,
  yearOptions,
  yearStatuses,
  scanning = false,
  selectedId,
  onSelect,
  onOpenDetail,
  onOpenTaxpayerProfile,
  onOpenWarnings,
  donemKarsilastirmaEtiketi = "",
  onYearChange,
  onExportExcel,
  exporting,
  statusMessage,
}: ResultsViewProps) {
  const [firmaAra, setFirmaAra] = useState("");
  const [durumFiltresi, setDurumFiltresi] = useState<DurumFiltresi>("Hepsi");
  const [filtreAcik, setFiltreAcik] = useState(false);

  const filteredRows = useMemo(() => {
    const normalized = normalizeText(firmaAra);
    return rows.filter((row) => {
      if (!validYear(row.yil)) {
        return false;
      }
      if (normalized) {
        const haystack = normalizeText([row.firma, row.resmiUnvan, row.vkn, row.maliMusavir, row.aramaMetni].join(" "));
        if (!haystack.includes(normalized)) {
          return false;
        }
      }
      if (selectedYear !== "Tüm Yıllar" && selectedYear && String(row.yil) !== selectedYear) {
        return false;
      }
      if (durumFiltresi === "Gönderilmiş" && !isSent(row)) {
        return false;
      }
      if (durumFiltresi === "Gönderilmemiş" && isSent(row)) {
        return false;
      }
      if (durumFiltresi === "Hatalı" && row.risk === "OK" && !row.ozelDurumTipi && !row.gecisRolu) {
        return false;
      }
      return true;
    });
  }, [rows, firmaAra, selectedYear, durumFiltresi]);

  const groupedRows = useMemo(() => {
    const grouped = new Map<string, FirmaSatiri>();
    filteredRows.forEach((row) => {
      const key = `${row.firma}-${row.vkn}-${row.yil}`;
      const monthIndex = AYLAR.indexOf(row.ay);
      if (monthIndex < 0) {
        return;
      }
      const current = grouped.get(key);
      if (current) {
        current.aylar[monthIndex] = row;
        current.demoLocked = current.demoLocked || Boolean(row.demoLocked);
        if (!current.ozelDurumTipi && row.ozelDurumTipi) {
          current.ozelDurumTipi = row.ozelDurumTipi;
        }
      } else {
        const aylar = Array.from({ length: 12 }, () => null as DonemKaydi | null);
        aylar[monthIndex] = row;
        grouped.set(key, {
          id: key,
          firma: row.firma,
          vkn: row.vkn,
          yil: row.yil,
          maliMusavir: row.maliMusavir,
          aylar,
          ozelDurumTipi: row.ozelDurumTipi || "",
          demoLocked: Boolean(row.demoLocked),
        });
      }
    });
    return Array.from(grouped.values()).sort((a, b) => {
      const rankDiff = groupRank(a) - groupRank(b);
      if (rankDiff !== 0) {
        return rankDiff;
      }
      return a.firma.localeCompare(b.firma, "tr");
    });
  }, [filteredRows]);

  const summary = useMemo(
    () => ({
      toplamFirma: groupedRows.length,
      gonderilmisFirma: groupedRows.filter((group) => group.aylar.some((period) => period && isSent(period))).length,
      uyariFirma: groupedRows.filter((group) => groupRank(group) !== 2).length,
    }),
    [groupedRows],
  );

  return (
    <div className="results-stack">
      <section className="card taxpayer-list-panel taxpayer-list-panel-full">
        <div className="card-header-row results-header-row">
          <div className="results-header-main">
            <h2 className="section-title">Toplu Kontrol</h2>
            <SectionSummaryInline
              toplamFirma={summary.toplamFirma}
              gonderilmisFirma={summary.gonderilmisFirma}
              uyariFirma={summary.uyariFirma}
              donemKarsilastirmaEtiketi={donemKarsilastirmaEtiketi}
              onOpenWarnings={onOpenWarnings}
              visible={summary.toplamFirma > 0}
            />
          </div>
        </div>

        <div className="compact-search-row compact-search-row-results">
          <input
            className="compact-search-input"
            value={firmaAra}
            onChange={(event) => setFirmaAra(event.target.value)}
            placeholder="Mükellef, ünvan, VKN veya mali müşavir ara"
          />
          <div className="results-toolbar">
            <YearStatusPicker
              selectedYear={selectedYear}
              yearOptions={yearOptions}
              yearStatuses={yearStatuses}
              scanning={scanning}
              onYearChange={onYearChange}
              includeAllOption
              buttonClassName="compact-year-select-results"
            />
            <button className="button button-secondary icon-export-button" onClick={onExportExcel} title="Excel çıktısı al" type="button">
              {exporting === "excel" ? "..." : <ExcelIcon />}
            </button>
            <div className="header-menu-wrap">
              <button className="button button-secondary" onClick={() => setFiltreAcik((value) => !value)} type="button">
                Filtreler
              </button>
              {filtreAcik ? (
                <div className="filter-popover">
                  <label className="field-group">
                    <span>Mükellef Ara</span>
                    <input value={firmaAra} onChange={(event) => setFirmaAra(event.target.value)} placeholder="Ünvan, VKN, müşavir" />
                  </label>
                  <label className="field-group">
                    <span>Yıl</span>
                    <YearStatusPicker
                      selectedYear={selectedYear}
                      yearOptions={yearOptions}
                      yearStatuses={yearStatuses}
                      scanning={scanning}
                      onYearChange={onYearChange}
                      includeAllOption
                    />
                  </label>
                  <label className="field-group">
                    <span>Sorun Türü</span>
                    <select value={durumFiltresi} onChange={(event) => setDurumFiltresi(event.target.value as DurumFiltresi)}>
                      <option value="Hepsi">Hepsi</option>
                      <option value="Gönderilmiş">Gönderilmiş</option>
                      <option value="Gönderilmemiş">Gönderilmemiş</option>
                      <option value="Hatalı">Hatalı</option>
                    </select>
                  </label>
                </div>
              ) : null}
            </div>
          </div>
        </div>

        {statusMessage ? <p className="results-status-note">{statusMessage}</p> : null}

        <div className="period-list-table-wrap">
          <div className="period-list-table-head">
            <span>Firma</span>
            <span>Yıl</span>
            {AYLAR.map((ay) => (
              <span key={ay}>{ay}</span>
            ))}
            <span>Müşavir</span>
          </div>

          {groupedRows.length > 0 ? (
            <div className="period-list-table-body">
              {groupedRows.map((group) => (
                <div key={group.id} className={`period-list-row ${rowSurfaceClass(group)}`}>
                  <button
                    className="period-list-company"
                    onClick={() => onOpenTaxpayerProfile(group.firma, group.vkn, group.yil)}
                    type="button"
                    title={`${group.firma} (${group.vkn})`}
                  >
                    {group.demoLocked ? <span className="period-list-lock-mark" aria-hidden="true">🔒</span> : null}
                    {group.firma} ({group.vkn})
                  </button>
                  <span className="period-list-year">{group.yil}</span>
                  {group.aylar.map((period, index) => (
                    <button
                      key={`${group.id}-${AYLAR[index]}`}
                      className={`period-list-cell ${cellTone(period)} ${period?.id === selectedId ? "period-list-cell-active" : ""}`}
                      onClick={() => {
                        if (!period || period.demoLocked) {
                          return;
                        }
                        onSelect(period.id);
                        onOpenDetail(period.id);
                      }}
                      title={buildMonthTitle(period, group.yil, AYLAR[index])}
                      type="button"
                    >
                      {cellMark(period)}
                    </button>
                  ))}
                  <span className="period-list-advisor" title={group.demoLocked ? (group.aylar.find(Boolean)?.demoMessage || "Demo kilidi") : (group.maliMusavir || "Müşavir yok")}>
                    {group.demoLocked ? "Pro Mod ile açılır" : (group.maliMusavir || "-")}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="compact-empty-state">Filtreye uygun firma bulunamadı.</div>
          )}
        </div>
      </section>
    </div>
  );
}

function ExcelIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="toolbar-svg-icon">
      <path d="M7 3h7l5 5v11.25A1.75 1.75 0 0 1 17.25 21H7A2 2 0 0 1 5 19V5a2 2 0 0 1 2-2Z" fill="currentColor" opacity=".18" />
      <path d="M14 3v5h5" fill="none" stroke="currentColor" strokeWidth="1.7" />
      <path d="M8 9.5 10.2 12 8 14.5m4.6-5L10.4 12l2.2 2.5m1.8-5h2.6m-2.6 5h2.6" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function normalizeText(value: string) {
  return value
    .toLocaleLowerCase("tr-TR")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9çğıöşü\s]/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function isSent(row: DonemKaydi) {
  return Boolean(row.gonderimTarihi || row.gibOnayTarihi || row.gibOnayliBerat === "Tam");
}

function validYear(year: number) {
  return year >= 2020 && year <= 2100;
}

function cellTone(row: DonemKaydi | null) {
  if (!row) {
    return "period-list-cell-gray";
  }
  if (row.demoLocked) {
    return "period-list-cell-locked";
  }
  if (row.araDonemAtlamasi) {
    return "period-list-cell-red";
  }
  if (row.ozelDurumTipi === "tasfiye" || row.ozelDurumTipi === "kurulus" || row.gecisRolu === "transition") {
    return "period-list-cell-amber";
  }
  if (row.risk === "OK") {
    return "period-list-cell-green";
  }
  if (!isSent(row)) {
    return "period-list-cell-gray";
  }
  if (row.risk === "LOW" || row.risk === "MEDIUM") {
    return "period-list-cell-yellow";
  }
  return "period-list-cell-red";
}

function cellMark(row: DonemKaydi | null) {
  if (!row) {
    return "-";
  }
  if (row.demoLocked) {
    return "🔒";
  }
  if (row.araDonemAtlamasi) {
    return "X";
  }
  if (row.ozelDurumTipi === "tasfiye" || row.ozelDurumTipi === "kurulus" || row.gecisRolu === "transition") {
    return "↔";
  }
  if (row.risk === "OK") {
    return "✓";
  }
  if (row.risk === "LOW" || row.risk === "MEDIUM") {
    return "!";
  }
  return "✕";
}

function buildMonthTitle(row: DonemKaydi | null, year: number, month: string) {
  if (!row) {
    return `${month}/${year} - dosya bulunamadı`;
  }
  if (row.demoLocked) {
    return row.demoMessage || "Bu firma Demo Mod sınırı dışında.";
  }
  if (row.araDonemAtlamasi && row.kullaniciIstisnasi) {
    return `${row.firma} ${month}/${year} - kullanıcı istisnası: ${row.kullaniciIstisnaNotu || "açıklama girilmedi"}`;
  }
  if (row.ozelDurum) {
    return `${row.firma} ${month}/${year} - ${row.ozelDurum}`;
  }
  if (row.gecisEtiketi) {
    return `${row.firma} ${month}/${year} - ${row.gecisEtiketi}`;
  }
  return `${row.firma} ${month}/${year} - ${row.durum}`;
}

function rowSurfaceClass(group: FirmaSatiri) {
  if (group.demoLocked) {
    return "period-list-row-locked";
  }
  const rank = groupRank(group);
  if (rank === 0) {
    return "period-list-row-risk";
  }
  if (rank === 1) {
    return "period-list-row-transition";
  }
  return "period-list-row-clean";
}

function groupRank(group: FirmaSatiri) {
  if (group.demoLocked) {
    return 3;
  }
  if (group.aylar.some((period) => period && period.risk !== "OK" && !period.kullaniciIstisnasi && !["LOW", "MEDIUM"].includes(period.risk))) {
    return 0;
  }
  if (group.ozelDurumTipi === "tasfiye" || group.ozelDurumTipi === "kurulus" || group.aylar.some((period) => period && !period.kullaniciIstisnasi && (period.gecisRolu === "transition" || period.risk !== "OK"))) {
    return 1;
  }
  return 2;
}
