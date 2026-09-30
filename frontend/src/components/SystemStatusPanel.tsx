import { Badge } from "./Badge";
import type { SistemDurumu } from "../types";

interface SystemStatusPanelProps {
  systemStatus: SistemDurumu | null;
  onOpenPath: (path: string) => void;
  onLoadLicense: () => void;
}

export function SystemStatusPanel({ systemStatus, onOpenPath, onLoadLicense }: SystemStatusPanelProps) {
  if (!systemStatus) {
    return null;
  }

  const lisans = systemStatus.lisans;
  const tone = lisans.valid ? "ok" : "warning";
  const copyDeviceCode = async () => {
    if (!lisans.device_code) {
      return;
    }
    await navigator.clipboard.writeText(lisans.device_code);
  };

  return (
    <section className="card system-status-panel">
      <div className="card-header-row">
        <div>
          <h2 className="section-title">Sistem Durumu</h2>
          <p className="section-subtitle">Lisans, log ve teknik tanılama görünürlüğü</p>
        </div>
        <Badge tone={tone}>{lisans.label}</Badge>
      </div>

      <div className="system-grid">
        <div className="detail-meta-item">
          <strong>Sürüm</strong>
          <span>{systemStatus.uygulama.surum}</span>
        </div>
        <div className="detail-meta-item">
          <strong>Çalışma Modu</strong>
          <span>{systemStatus.uygulama.mod}</span>
        </div>
        <div className="detail-meta-item detail-meta-item-wide">
          <strong>Lisans Mesajı</strong>
          <span>{lisans.message}</span>
        </div>
        <div className="detail-meta-item">
          <strong>Cihaz Kodu</strong>
          <span>{lisans.device_code || "-"}</span>
        </div>
      </div>

      <div className="system-actions">
        <button className="button button-secondary" onClick={() => onOpenPath(systemStatus.yollar.log)}>Log Klasörü</button>
        <button className="button button-secondary" onClick={() => onOpenPath(systemStatus.yollar.appLog)}>App Log</button>
        <button className="button button-secondary" onClick={() => onOpenPath(systemStatus.yollar.debugLog)}>Debug Log</button>
        <button className="button button-secondary" onClick={() => onOpenPath(systemStatus.yollar.errorLog)}>Error Log</button>
      </div>

      <div className="system-diagnostics">
        <div className="system-diagnostic-row">
          <strong>Son Hata</strong>
          <span>{systemStatus.gunluk.sonHataSatiri || "Hata kaydı görünmüyor."}</span>
        </div>
        <div className="system-diagnostic-row">
          <strong>Son Debug</strong>
          <span>{systemStatus.gunluk.sonDebugSatiri || "Debug kaydı görünmüyor."}</span>
        </div>
      </div>
    </section>
  );
}
