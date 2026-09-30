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
        <small>firma gönderilmiş</small>
      </span>
      <button
        className={`section-summary-chip section-summary-chip-warning section-summary-chip-clickable ${uyariFirma > 0 ? "section-summary-chip-warning-active" : ""}`}
        onClick={onOpenWarnings}
        type="button"
      >
        <strong>{uyariFirma}</strong>
        <small>firma için uyarı var</small>
      </button>
      {donemKarsilastirmaEtiketi ? (
        <button className="section-summary-chip section-summary-chip-clickable" onClick={onOpenWarnings} type="button">
          <strong>{donemKarsilastirmaEtiketi}</strong>
          <small>geçmiş dönem karşılaştırması</small>
        </button>
      ) : null}
    </div>
  );
}
