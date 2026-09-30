interface SectionSummaryInlineProps {
  toplamFirma: number;
  gonderilmisFirma: number;
  uyariFirma: number;
  onOpenWarnings: () => void;
  visible?: boolean;
  donemKarsilastirmaEtiketi?: string;
}

export function SectionSummaryInline({
  toplamFirma,
  gonderilmisFirma,
  uyariFirma,
  onOpenWarnings,
  visible = true,
  donemKarsilastirmaEtiketi = "",
}: SectionSummaryInlineProps) {
  if (!visible) {
    return null;
  }

  return (
    <div className="section-summary-inline">
      <span className="section-summary-chip">
        <strong>{toplamFirma}</strong>
        <small>firma tespit edildi</small>
      </span>
      <span className="section-summary-chip">
        <strong>{gonderilmisFirma}</strong>
        <small>firma g\u00f6nderilmi\u015f</small>
      </span>
      <button
        className={`section-summary-chip section-summary-chip-warning section-summary-chip-clickable ${uyariFirma > 0 ? "section-summary-chip-warning-active" : ""}`}
        onClick={onOpenWarnings}
        type="button"
      >
        <strong>{uyariFirma}</strong>
        <small>firma i\u00e7in uyar\u0131 var</small>
      </button>
      {donemKarsilastirmaEtiketi ? (
        <button className="section-summary-chip section-summary-chip-clickable" onClick={onOpenWarnings} type="button">
          <strong>{donemKarsilastirmaEtiketi}</strong>
          <small>ge\u00e7mi\u015f d\u00f6nem kar\u015f\u0131la\u015ft\u0131rmas\u0131</small>
        </button>
      ) : null}
    </div>
  );
}
