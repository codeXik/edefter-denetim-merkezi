import { openPath } from "../api";
import { riskIcon, riskLabel } from "../presentation";
import { YearStatusPicker, type YearStatusItem } from "./YearStatusPicker";
import type { DonemKaydi, MukellefKarti } from "../types";

interface TaxpayerProfileViewProps {
  card: MukellefKarti | null;
  periods: DonemKaydi[];
  yearOptions: number[];
  yearStatuses: YearStatusItem[];
  selectedYear: string;
  scanning?: boolean;
  onYearChange: (value: string) => void;
  onOpenPeriod: (periodId: string) => void;
  onBack: () => void;
}

export function TaxpayerProfileView({
  card,
  periods,
  yearOptions,
  yearStatuses,
  selectedYear,
  scanning = false,
  onYearChange,
  onOpenPeriod,
  onBack,
}: TaxpayerProfileViewProps) {
  if (!card) {
    return <div className="card compact-empty-state">Profil g\u00f6r\u00fcnt\u00fclenecek m\u00fckellef bulunamad\u0131.</div>;
  }

  const warnings = card.demoLocked
    ? []
    : periods.filter((period) => !period.kullaniciIstisnasi && (period.risk !== "OK" || period.ozelDurumTipi || period.gecisRolu));

  return (
    <div className="page-stack">
      <section className={`card taxpayer-profile-card taxpayer-profile-${card.durumGrubu || "green"} ${card.demoLocked ? "taxpayer-profile-locked" : ""}`}>
        <div className="card-header-row taxpayer-profile-top">
          <div className="taxpayer-profile-heading">
            <div className="taxpayer-profile-title-line">
              <h2 className="section-title">{card.gosterimAdi}</h2>
              <button
                className="icon-only-action"
                onClick={() => card.klasorYolu && void openPath(card.klasorYolu)}
                disabled={!card.klasorYolu || card.demoLocked}
                title="Klas\u00f6r\u00fc a\u00e7"
                type="button"
              >
                <FolderIcon />
              </button>
            </div>
            <p className="section-subtitle">{card.vknTckn}</p>
          </div>
          <div className="button-row">
            <YearStatusPicker
              selectedYear={selectedYear}
              yearOptions={yearOptions}
              yearStatuses={yearStatuses}
              scanning={scanning}
              onYearChange={onYearChange}
              buttonClassName="compact-year-select-profile"
            />
            <button className="button button-secondary" onClick={onBack} type="button">
              Geri
            </button>
          </div>
        </div>

        <div className="taxpayer-profile-summary-grid">
          <div className="taxpayer-profile-chip">
            <strong>Y\u0131l</strong>
            <span>{card.yil}</span>
          </div>
          <div className="taxpayer-profile-chip">
            <strong>Mali M\u00fc\u015favir</strong>
            <span>{card.maliMusavir || "-"}</span>
          </div>
          <div className="taxpayer-profile-chip">
            <strong>Durum</strong>
            <span>{card.demoLocked ? "Kilitli" : `${riskIcon(card.genelRisk)} ${riskLabel(card.genelRisk)}`}</span>
          </div>
          <div className="taxpayer-profile-chip">
            <strong>Uyar\u0131</strong>
            <span>{card.demoLocked ? "\u00d6nizleme" : `${warnings.length} kay\u0131t`}</span>
          </div>
        </div>

        {card.envanterVar ? (
          <div className="taxpayer-profile-notice taxpayer-profile-notice-info">
            {card.gibEnvanterVar
              ? `Bu y\u0131lda ${card.envanterDonemSayisi || 0} d\u00f6nemde envanter ve G\u0130B onayl\u0131 envanter berat\u0131 izleniyor.`
              : `Bu y\u0131lda ${card.envanterDonemSayisi || 0} d\u00f6nemde envanter kayd\u0131 izleniyor.`}
          </div>
        ) : null}
        {card.ozelDurum ? <div className="taxpayer-profile-notice">{card.ozelDurum}</div> : null}
        {card.demoLocked ? <div className="taxpayer-profile-notice taxpayer-profile-lock-notice">{card.demoMessage || "Bu firma Demo Mod s\u0131n\u0131r\u0131 d\u0131\u015f\u0131nda."}</div> : null}

        <div className={`months-grid months-grid-quarterly taxpayer-profile-months ${card.demoLocked ? "months-grid-locked" : ""}`}>
          {card.donemler.map((month) => (
            <button
              key={`${card.id}-${month.ayNo}`}
              className={`month-pill month-${monthTone(month)}`}
              disabled={card.demoLocked || !month.donemId}
              onClick={() => !card.demoLocked && month.donemId && onOpenPeriod(month.donemId)}
              type="button"
            >
              {month.donemId ? (
                <span className="month-eye" aria-hidden="true">
                  {month.gecisRolu === "transition" ? <TransitionIcon /> : <ViewDotIcon />}
                </span>
              ) : null}
              <strong>{month.ayNo}</strong>
              <span>{month.ayAd}</span>
            </button>
          ))}
        </div>
      </section>

      <section className="card">
        <div className="card-header-row">
          <div>
            <h2 className="section-title">M\u00fckellef Uyar\u0131lar\u0131</h2>
            <p className="section-subtitle">Se\u00e7ili y\u0131ldaki hareketler</p>
          </div>
        </div>
        {card.demoLocked ? (
          <div className="compact-empty-state">Detay uyar\u0131lar Pro Mod ile a\u00e7\u0131l\u0131r.</div>
        ) : warnings.length > 0 ? (
          <div className="warning-list">
            {warnings.map((period) => (
              <button key={period.id} className="warning-row" onClick={() => onOpenPeriod(period.id)} type="button">
                <strong>{period.yil}/{period.ay}</strong>
                <span>{period.ozelDurum || period.gecisEtiketi || period.durum}</span>
                <small>{period.ozet.join(" | ")}</small>
              </button>
            ))}
          </div>
        ) : (
          <div className="compact-empty-state">Bu m\u00fckellef i\u00e7in se\u00e7ili y\u0131lda uyar\u0131 g\u00f6r\u00fcnm\u00fcyor.</div>
        )}
      </section>
    </div>
  );
}

function monthTone(month: MukellefKarti["donemler"][number]) {
  if (month.araDonemAtlamasi) {
    return "red";
  }
  if (month.ozelDurumTipi === "tasfiye" || month.ozelDurumTipi === "kurulus" || month.gecisRolu === "transition") {
    return "amber";
  }
  return month.durumRengi;
}

function FolderIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="toolbar-svg-icon">
      <path d="M3 6.75A1.75 1.75 0 0 1 4.75 5h4.1c.48 0 .93.2 1.26.54l1.11 1.21h8.03A1.75 1.75 0 0 1 21 8.5v8.75A1.75 1.75 0 0 1 19.25 19H4.75A1.75 1.75 0 0 1 3 17.25Z" fill="currentColor" />
    </svg>
  );
}

function ViewDotIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" className="toolbar-svg-icon">
      <circle cx="10" cy="10" r="3.4" fill="currentColor" />
    </svg>
  );
}

function TransitionIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" className="toolbar-svg-icon">
      <path d="M4 7.5h8.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <path d="m10.5 4.8 3 2.7-3 2.7" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M16 12.5H7.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <path d="m9.5 9.8-3 2.7 3 2.7" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
