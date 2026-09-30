import type { ArsivAdayi, HizliKesifSonucu, IslemDurumu } from "../types";

interface WizardViewProps {
  startFolder: string;
  discovery: HizliKesifSonucu | null;
  progress: IslemDurumu | null;
  autoContinue: boolean;
  selectedCandidatePath: string | null;
  discovering: boolean;
  scanning: boolean;
  onChooseStartFolder: () => void;
  onAutoContinueChange: (value: boolean) => void;
  onRunDiscovery: () => void;
  onCancelJob: () => void;
  onSelectCandidate: (candidatePath: string) => void;
  onScanSelectedCandidate: () => void;
  onUseCandidate: (candidate: ArsivAdayi) => void;
  onDirectScan: () => void;
}

export function WizardView({
  startFolder,
  discovery,
  progress,
  autoContinue,
  selectedCandidatePath,
  discovering,
  scanning,
  onChooseStartFolder,
  onAutoContinueChange,
  onRunDiscovery,
  onCancelJob,
  onSelectCandidate,
  onScanSelectedCandidate,
  onUseCandidate,
  onDirectScan,
}: WizardViewProps) {
  const hasFolder = Boolean(startFolder);
  const aktifIslem = discovering || scanning;

  return (
    <div className="wizard-layout">
      <section className="card wizard-hero">
        <div>
          <h2 className="section-title">Sihirbaz Çalıştır</h2>
          <p className="section-subtitle">
            Program önce hızlı tarama yapar, muhtemel e-Defter ana klasörlerini bulur, sonra seçilen klasörde gerçek denetimi başlatır.
          </p>
        </div>
        <div className="button-row">
          <button className="button button-secondary" onClick={onChooseStartFolder} disabled={aktifIslem}>
            Başlangıç Klasörü Seç
          </button>
          <button className="button button-primary" disabled={!hasFolder || discovering || scanning} onClick={onRunDiscovery}>
            {discovering ? "Hızlı Tarama Çalışıyor..." : "Sihirbazı Çalıştır"}
          </button>
          <button className="button button-secondary" disabled={!hasFolder || discovering || scanning} onClick={onDirectScan}>
            Doğrudan Kontrol Et
          </button>
          <button className="button button-secondary" disabled={!aktifIslem} onClick={onCancelJob}>
            İptal Et
          </button>
        </div>
        <label className="wizard-toggle">
          <input
            type="checkbox"
            checked={autoContinue}
            onChange={(event) => onAutoContinueChange(event.target.checked)}
            disabled={aktifIslem}
          />
          <span>Hızlı tarama bitince en güçlü adayla otomatik devam et</span>
        </label>
      </section>

      <section className="card wizard-info">
        <strong>Başlangıç klasörü</strong>
        <p>{startFolder || "Henüz klasör seçilmedi."}</p>
      </section>

      <section className="card wizard-monitor-card">
        <div className="card-header-row">
          <div>
            <h2 className="section-title">İşlem Merkezi</h2>
            <p className="section-subtitle">
              {progress?.aktif
                ? "Tarama arka planda canlı olarak izleniyor"
                : progress?.iptalEdildi
                  ? "Son işlem kullanıcı tarafından iptal edildi"
                  : "Sihirbaz başlatıldığında ilerleme burada canlı görünür"}
            </p>
          </div>
        </div>

        <div className="wizard-progress-shell">
          <div className="wizard-progress-track">
            <div className="wizard-progress-fill" style={{ width: `${Math.max(progress?.yuzde ?? 0, 12)}%` }}>
              <span>{progress?.mesaj || "Hazır"}</span>
            </div>
          </div>
          <div className="wizard-progress-caption">
            <strong>{progress?.asama || "Beklemede"}</strong>
            <span>{progress?.detay || "Klasör seçip sihirbazı başlatın."}</span>
          </div>
        </div>

        <div className="wizard-metrics-grid">
          <div className="wizard-metric-card">
            <span>Taranan klasör</span>
            <strong>{formatNumber(progress?.tarananKlasor ?? 0)}</strong>
          </div>
          <div className="wizard-metric-card">
            <span>Aday kök</span>
            <strong>{formatNumber(progress?.adaySayisi ?? 0)}</strong>
          </div>
          <div className="wizard-metric-card">
            <span>Mükellef</span>
            <strong>{formatNumber(progress?.mukellefSayisi ?? 0)}</strong>
          </div>
          <div className="wizard-metric-card">
            <span>Dönem</span>
            <strong>{formatNumber(progress?.donemSayisi ?? 0)}</strong>
          </div>
          <div className="wizard-metric-card">
            <span>Geçen süre</span>
            <strong>{formatElapsed(progress?.gecenSureSaniye ?? 0)}</strong>
          </div>
        </div>

        <div className="wizard-last-action">
          <strong>Son işlem</strong>
          <span>{progress?.sonIslem || "Henüz işlem yok."}</span>
        </div>

        <div className="wizard-mini-log">
          {(progress?.loglar?.length ?? 0) > 0 ? (
            progress?.loglar.map((log, index) => (
              <div key={`${log}-${index}`} className="wizard-mini-log-row">
                <span>{log}</span>
              </div>
            ))
          ) : (
            <div className="compact-empty-state small-panel-empty">Canlı işlem akışı burada görünecek.</div>
          )}
        </div>
      </section>

      <section className="card wizard-steps">
        <div className="wizard-step">
          <strong>1. Klasör yapısı taranır</strong>
          <span>VKN/TCKN, şirket adı, yıl aralığı ve ay klasörü sinyalleri toplanır.</span>
        </div>
        <div className="wizard-step">
          <strong>2. Aday kökler hazırlanır</strong>
          <span>En güçlü e-Defter ana klasörleri güven skoru ile listelenir.</span>
        </div>
        <div className="wizard-step">
          <strong>3. Derin denetim başlar</strong>
          <span>Seçilen kökte mükellef, dönem ve belge seti riskleri hesaplanır.</span>
        </div>
      </section>

      <section className="card wizard-candidates">
        <div className="card-header-row">
          <div>
            <h2 className="section-title">Bulunan Ana Klasörler</h2>
            <p className="section-subtitle">
              {discovery ? `${discovery.adaylar.length} aday bulundu` : "Henüz hızlı tarama yapılmadı"}
            </p>
          </div>
          <div className="button-row">
            <button
              className="button button-secondary"
              disabled={!discovery || discovery.adaylar.length === 0 || discovering || scanning}
              onClick={onRunDiscovery}
            >
              Adayları Yenile
            </button>
            <button
              className="button button-primary"
              disabled={!selectedCandidatePath || discovering || scanning}
              onClick={onScanSelectedCandidate}
            >
              Seçili Adayı Tara
            </button>
          </div>
        </div>

        {discovery && discovery.adaylar.length > 0 ? (
          <div className="candidate-list">
            {discovery.adaylar.map((candidate) => (
              <article
                key={candidate.klasorYolu}
                className={`candidate-card ${selectedCandidatePath === candidate.klasorYolu ? "candidate-card-selected" : ""}`}
              >
                <div className="candidate-head">
                  <div>
                    <h3>{candidate.klasorYolu}</h3>
                    <p>{candidate.ozet}</p>
                  </div>
                  <div className="candidate-score">{candidate.guvenSkoru}</div>
                </div>
                <div className="candidate-meta">
                  <span>{candidate.mukellefSayisi} mükellef</span>
                  <span>{candidate.yilSayisi} yıl</span>
                  <span>{candidate.aySayisi} ay klasörü</span>
                  <span>{candidate.eslesenDosyaSayisi} dosya işareti</span>
                </div>
                {candidate.ornekler.length > 0 ? (
                  <div className="candidate-samples">
                    Örnekler: {candidate.ornekler.join(", ")}
                  </div>
                ) : null}
                <div className="candidate-actions">
                  <button
                    className="button button-secondary"
                    disabled={scanning || discovering}
                    onClick={() => onSelectCandidate(candidate.klasorYolu)}
                  >
                    {selectedCandidatePath === candidate.klasorYolu ? "Seçildi" : "Adayı Seç"}
                  </button>
                  <button className="button button-primary" disabled={scanning || discovering} onClick={() => onUseCandidate(candidate)}>
                    Bu Klasörü Kullan
                  </button>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="compact-empty-state">
            {discovery && !discovery.bulundu
              ? "Uygun e-Defter ana klasörü bulunamadı. Başka bir başlangıç klasörü seçebilir veya doğrudan kontrol başlatabilirsiniz."
              : "Hızlı tarama sonrası aday klasörler burada listelenecek."}
          </div>
        )}
      </section>
    </div>
  );
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("tr-TR").format(value);
}

function formatElapsed(value: number) {
  const seconds = Math.max(0, Math.floor(value));
  const minutes = Math.floor(seconds / 60);
  const remaining = seconds % 60;
  if (minutes === 0) {
    return `${remaining} sn`;
  }
  return `${minutes} dk ${remaining} sn`;
}
