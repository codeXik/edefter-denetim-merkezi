import { riskIcon, riskTone } from "../presentation";
import { Badge } from "./Badge";
import { SectionSummaryInline } from "./SectionSummaryInline";
import { YearStatusPicker, type YearStatusItem } from "./YearStatusPicker";
import type { DashboardOzeti, MukellefKarti } from "../types";

interface DashboardViewProps {
  dashboard: DashboardOzeti;
  visibleCards: MukellefKarti[];
  filteredCount: number;
  gonderilmisCount: number;
  uyariCount: number;
  donemKarsilastirmaEtiketi?: string;
  warningText?: string | null;
  searchText: string;
  selectedYear: string;
  yearOptions: number[];
  yearStatuses: YearStatusItem[];
  scanning?: boolean;
  selectedTaxpayerId: string | null;
  onSearchTextChange: (value: string) => void;
  onYearChange: (value: string) => void;
  onPreviousCards: () => void;
  onNextCards: () => void;
  onSelectTaxpayer: (taxpayerId: string) => void;
  onOpenTaxpayerProfile: (taxpayerId: string) => void;
  onOpenPeriod: (periodId: string) => void;
  onOpenFolder: (folderPath: string) => void;
  onChooseFolder: () => void;
  onOpenWarnings: () => void;
}

export function DashboardView({
  dashboard,
  visibleCards,
  filteredCount,
  gonderilmisCount,
  uyariCount,
  donemKarsilastirmaEtiketi = "",
  warningText,
  searchText,
  selectedYear,
  yearOptions,
  yearStatuses,
  scanning = false,
  selectedTaxpayerId,
  onSearchTextChange,
  onYearChange,
  onPreviousCards,
  onNextCards,
  onSelectTaxpayer,
  onOpenTaxpayerProfile,
  onOpenPeriod,
  onOpenFolder,
  onChooseFolder,
  onOpenWarnings,
}: DashboardViewProps) {
  const selectedCardId = selectedTaxpayerId ?? visibleCards[0]?.id ?? null;

  if (!dashboard.arsivKlasoru) {
    return (
      <div className="compact-layout compact-layout-wide">
        <section className="card startup-onboarding-card">
          {warningText ? <div className="startup-warning-banner">{warningText}</div> : null}
          <div className="startup-onboarding-icon" aria-hidden="true">
            <FolderIcon />
          </div>
          <h2>e-Defter bulunan klas\u00f6r\u00fc se\u00e7in</h2>
          <p>\u0130lk tarama i\u00e7in m\u00fc\u015fteri klas\u00f6r\u00fcn\u00fc se\u00e7in. Klas\u00f6r se\u00e7ildikten sonra tarama ba\u015flat\u0131l\u0131r.</p>
          <button className="button button-primary" onClick={onChooseFolder} type="button">
            Klas\u00f6r Se\u00e7
          </button>
        </section>
      </div>
    );
  }

  return (
    <div className="compact-layout compact-layout-wide">
      <section className="card taxpayer-carousel-card taxpayer-carousel-card-compact">
        <div className="carousel-header">
          <div className="carousel-header-main">
            <h2 className="section-title">M\u00fckellefler</h2>
            <SectionSummaryInline
              toplamFirma={filteredCount}
              gonderilmisFirma={gonderilmisCount}
              uyariFirma={uyariCount}
              donemKarsilastirmaEtiketi={donemKarsilastirmaEtiketi}
              onOpenWarnings={onOpenWarnings}
              visible={filteredCount > 0}
            />
          </div>
          <div className="button-row">
            <button className="button button-secondary square-button" onClick={onPreviousCards} type="button" aria-label="\u00d6nceki kartlar">
              <ChevronLeftIcon />
            </button>
            <button className="button button-secondary square-button" onClick={onNextCards} type="button" aria-label="Sonraki kartlar">
              <ChevronRightIcon />
            </button>
          </div>
        </div>

        <div className="compact-search-row">
          <input
            className="compact-search-input"
            value={searchText}
            onChange={(event) => onSearchTextChange(event.target.value)}
            placeholder="M\u00fckellef, \u00fcnvan, VKN veya mali m\u00fc\u015favir ara"
          />
          <YearStatusPicker
            selectedYear={selectedYear}
            yearOptions={yearOptions}
            yearStatuses={yearStatuses}
            scanning={scanning}
            onYearChange={onYearChange}
          />
        </div>

        {visibleCards.length > 0 ? (
          <div className="taxpayer-grid taxpayer-grid-compact">
            {visibleCards.map((card) => (
              <article
                key={card.id}
                className={`taxpayer-card taxpayer-card-mini ${cardSurfaceClass(card)} ${
                  selectedCardId === card.id ? "taxpayer-card-selected" : ""
                }`}
                onClick={() => onSelectTaxpayer(card.id)}
              >
                <div className={`taxpayer-card-body ${card.demoLocked ? "taxpayer-card-body-locked" : ""}`}>
                  <div className="taxpayer-card-header">
                    <div className="taxpayer-card-title-wrap">
                      <button
                        className="taxpayer-name-link"
                        onClick={(event) => {
                          event.stopPropagation();
                          onOpenTaxpayerProfile(card.id);
                        }}
                        type="button"
                      >
                        <strong className="taxpayer-name-single" title={card.gosterimAdi}>
                          {card.gosterimAdi}
                        </strong>
                      </button>
                      <p>{card.vknTckn}</p>
                    </div>
                    <div className="taxpayer-card-badge-wrap">
                      <button
                        className="icon-only-action"
                        onClick={(event) => {
                          event.stopPropagation();
                          if (card.klasorYolu && !card.demoLocked) {
                            onOpenFolder(card.klasorYolu);
                          }
                        }}
                        disabled={!card.klasorYolu || card.demoLocked}
                        title="Klas\u00f6r\u00fc a\u00e7"
                        type="button"
                      >
                        <FolderIcon />
                      </button>
                      <span className="taxpayer-year-badge">{card.yil}</span>
                      {card.envanterVar ? (
                        <span
                          className={`taxpayer-inventory-badge ${card.gibEnvanterVar ? "taxpayer-inventory-badge-gib" : ""}`}
                          title={
                            card.gibEnvanterVar
                              ? "Bu y\u0131lda envanter ve G\u0130B onayl\u0131 envanter berat\u0131 var"
                              : "Bu y\u0131lda envanter kayd\u0131 var"
                          }
                        >
                          E
                        </span>
                      ) : null}
                      {card.demoLocked ? (
                        <span className="taxpayer-lock-badge" title={card.demoMessage || "Demo kilidi"}>
                          <LockIcon />
                        </span>
                      ) : null}
                      <Badge tone={riskTone(card.genelRisk)}>{riskIcon(card.genelRisk)}</Badge>
                    </div>
                  </div>

                  <div className="taxpayer-card-meta">
                    <span>{card.eksikDonemSayisi} sorunlu d\u00f6nem</span>
                    <span>{card.kritikSorunSayisi} kritik</span>
                  </div>

                  <div className="taxpayer-card-note-wrap">
                    {card.maliMusavir ? <div className="taxpayer-card-note">Mali m\u00fc\u015favir: {card.maliMusavir}</div> : null}
                    <div className={`taxpayer-card-note taxpayer-card-note-soft ${card.ozelDurum ? "taxpayer-card-note-special" : ""}`}>
                      {card.demoLocked ? (card.demoMessage || "Demo s\u0131n\u0131r\u0131 d\u0131\u015f\u0131nda.") : buildCardShortSummary(card)}
                    </div>
                  </div>

                  <div className={`months-grid months-grid-quarterly ${card.demoLocked ? "months-grid-locked" : ""}`}>
                    {card.donemler.map((month) => (
                      <button
                        key={`${card.id}-${month.ayNo}`}
                        className={`month-pill month-${monthTone(month)}`}
                        disabled={card.demoLocked || !month.donemId}
                        onClick={(event) => {
                          event.stopPropagation();
                          if (!card.demoLocked && month.donemId) {
                            onOpenPeriod(month.donemId);
                          }
                        }}
                        title={`${month.ayNo} - ${month.ayAd}: ${month.ozet}`}
                        type="button"
                      >
                        {month.donemId ? (
                          <span className="month-eye" aria-hidden="true">
                            {month.gecisRolu === "transition" || month.ozelDurumTipi === "tasfiye" ? <TransitionIcon /> : <ViewDotIcon />}
                          </span>
                        ) : null}
                        <strong>{month.ayNo}</strong>
                        <span>{month.ayAd.slice(0, 3)}</span>
                      </button>
                    ))}
                  </div>
                </div>
                {card.demoLocked ? (
                  <div className="taxpayer-card-demo-lock">
                    <span className="taxpayer-card-demo-lock-icon" aria-hidden="true">
                      <LockIcon />
                    </span>
                    <div className="taxpayer-card-demo-lock-copy">
                      <strong>Pro Mod ile a\u00e7\u0131l\u0131r</strong>
                      <span>\u0130lk 4 firma d\u0131\u015f\u0131nda kalan veriler kilitlidir</span>
                    </div>
                  </div>
                ) : null}
              </article>
            ))}
          </div>
        ) : (
          <div className="compact-empty-state">Se\u00e7ili filtrede g\u00f6sterilecek m\u00fckellef bulunamad\u0131.</div>
        )}
      </section>
    </div>
  );
}

function FolderIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="toolbar-svg-icon">
      <path d="M3 6.75A1.75 1.75 0 0 1 4.75 5h4.1c.48 0 .93.2 1.26.54l1.11 1.21h8.03A1.75 1.75 0 0 1 21 8.5v8.75A1.75 1.75 0 0 1 19.25 19H4.75A1.75 1.75 0 0 1 3 17.25Z" fill="currentColor" />
    </svg>
  );
}

function LockIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="toolbar-svg-icon">
      <path d="M8 10V7.75A4 4 0 0 1 12 3.75a4 4 0 0 1 4 4V10" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <rect x="5.5" y="10" width="13" height="10.5" rx="3" fill="currentColor" opacity="0.18" />
      <rect x="6.5" y="11" width="11" height="8.5" rx="2.4" fill="none" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="12" cy="15" r="1.2" fill="currentColor" />
      <path d="M12 16.2v1.8" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function ChevronLeftIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" className="toolbar-svg-icon">
      <path d="m12.5 4.5-5 5 5 5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ChevronRightIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" className="toolbar-svg-icon">
      <path d="m7.5 4.5 5 5-5 5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
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

function buildCardShortSummary(card: MukellefKarti) {
  if (card.ozelDurumTipi === "tasfiye") {
    return "Tasfiye klas\u00f6r\u00fc izleniyor";
  }
  if (card.ozelDurumTipi === "kurulus") {
    return "D\u00f6nem i\u00e7inde kurulu\u015f kayd\u0131 izleniyor";
  }
  if ((card.onayliIstisnaSayisi ?? 0) > 0) {
    return `${card.onayliIstisnaSayisi} kullan\u0131c\u0131 onayl\u0131 istisna var`;
  }
  if (card.ozelDurum) {
    return card.ozelDurum;
  }
  if (card.kritikSorunSayisi > 0) {
    return `${card.kritikSorunSayisi} kritik sorun var`;
  }
  if (card.eksikDonemSayisi > 0) {
    return `${card.eksikDonemSayisi} d\u00f6nem kontrol bekliyor`;
  }
  return "T\u00fcm g\u00f6r\u00fcnen d\u00f6nemler temiz";
}

function cardSurfaceClass(card: MukellefKarti) {
  if (card.demoLocked) {
    return "taxpayer-card-locked";
  }
  if (card.durumGrubu === "red") {
    return "taxpayer-card-danger";
  }
  if (card.durumGrubu === "yellow") {
    return "taxpayer-card-warning";
  }
  return "taxpayer-card-ok";
}

function monthTone(month: MukellefKarti["donemler"][number]) {
  if (month.kullaniciIstisnasi) {
    return "green";
  }
  if (month.ozelDurumTipi === "tasfiye" || month.gecisRolu === "transition") {
    return "amber";
  }
  return month.durumRengi;
}
