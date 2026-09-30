import { useEffect, useState } from "react";
import { openPath } from "../api";
import { riskIcon, riskLabel, riskTone, statusClass, statusIcon, statusTone } from "../presentation";
import { Badge } from "./Badge";
import type { DonemKaydi } from "../types";

interface PeriodDetailViewProps {
  period: DonemKaydi | null;
  onOpenXmlViewer?: (periodId: string) => void;
  onOpenControlXml?: (period: DonemKaydi, controlId: string) => void;
  onSetPeriodOverride?: (periodId: string, approved: boolean, note: string) => void;
}

export function PeriodDetailView({ period, onOpenXmlViewer, onOpenControlXml, onSetPeriodOverride }: PeriodDetailViewProps) {
  const [overrideNote, setOverrideNote] = useState("");

  useEffect(() => {
    setOverrideNote(period?.kullaniciIstisnaNotu || "");
  }, [period?.id, period?.kullaniciIstisnaNotu]);

  if (!period) {
    return (
      <div className="empty-state">
        <h2>Dönem seçilmedi</h2>
        <p>Toplu Kontrol veya Mükellef Kontrol ekranından bir dönem seçerek detayları görüntüleyin.</p>
      </div>
    );
  }

  const xmlGoruntulenebilir = period.risk === "OK";
  const supportFiles = [...period.topluPaketler, ...period.yardimciDosyalar];
  const anaRiskEtiketi = riskLabel(period.risk);
  const durumRozetiGoster = period.durum !== anaRiskEtiketi;
  const inventoryControls = period.kontroller.filter((item) => item.id.includes("INVENTORY"));
  const hasInventory = inventoryControls.length > 0;
  const hasGibInventory = inventoryControls.some((item) => item.id === "GIB_APPROVED_INVENTORY_BERAT");

  return (
    <div className="page-stack">
      <section className="card period-hero-card compact-period-hero">
        <div className="card-header-row">
          <div>
            <h2 className="section-title">{period.firma}</h2>
            <p className="section-subtitle">VKN: {period.vkn} • {period.yil}/{period.ay}</p>
          </div>
          <div className="button-row">
            <Badge tone={riskTone(period.risk)}>{riskIcon(period.risk)} {anaRiskEtiketi}</Badge>
            {hasInventory ? <Badge tone={hasGibInventory ? "ok" : "info"}>{hasGibInventory ? "GİB Envanter" : "Envanter"}</Badge> : null}
            {period.gecisEtiketi ? <Badge tone="info">{period.gecisEtiketi}</Badge> : null}
            {durumRozetiGoster ? <Badge tone={statusTone(period.durum)}>{period.durum}</Badge> : null}
          </div>
        </div>

        <div className="period-summary-strip">
          <div className="period-summary-chip">
            <strong>Gönderim</strong>
            <span>{period.gonderimTarihi || "-"}</span>
          </div>
          <div className="period-summary-chip">
            <strong>İmza</strong>
            <span>{period.imzaTarihi || "-"}</span>
          </div>
          <div className="period-summary-chip">
            <strong>GİB Onay</strong>
            <span>{period.gibOnayTarihi || "-"}</span>
          </div>
          <div className="period-summary-chip">
            <strong>Dönem</strong>
            <span>{period.donemBaslangic || "-"} / {period.donemBitis || "-"}</span>
          </div>
        </div>

        <div className="detail-actions">
          <button className="button button-secondary" onClick={() => void openPath(period.klasorYolu)} disabled={!period.klasorYolu} type="button">
            Klasörü Aç
          </button>
          {xmlGoruntulenebilir ? (
            <button className="button button-primary" onClick={() => period.id && onOpenXmlViewer?.(period.id)} type="button">
              GİB Onaylı Sureti Aç
            </button>
          ) : null}
        </div>
        {hasInventory ? (
          <div className="taxpayer-profile-notice taxpayer-profile-notice-info">
            {hasGibInventory
              ? "Bu dönemde envanter defteri, envanter beratı ve GİB onaylı envanter beratı bulundu."
              : "Bu dönemde envanter kayıtları bulundu."}
          </div>
        ) : null}
      </section>

      <section className="card">
        <div className="card-header-row">
          <div>
            <h2 className="section-title">Kontrol Özeti</h2>
            <p className="section-subtitle">Temel belge seti ve hızlı erişim</p>
          </div>
        </div>
        <div className="period-check-grid compact-period-grid">
          {period.kontroller.map((item) => (
            <article key={item.id} className={`period-check-card period-check-${statusClass(item.durum)}`}>
              <div className="period-check-icon">{statusIcon(item.durum)}</div>
              <div className="period-check-body">
                <strong>{item.etiket}</strong>
                <span>{item.aciklama}</span>
                <small>XML: {item.xmlAdet} • ZIP: {item.zipAdet} • Beklenen: {item.beklenenAdet}</small>
              </div>
              <div className="period-check-side">
                <div className="period-check-state">{item.durum}</div>
                <button
                  className="button button-secondary button-small"
                  onClick={() => onOpenControlXml?.(period, item.id)}
                  disabled={!item.dosyaYollari.some((path) => path.toLocaleLowerCase("tr-TR").endsWith(".xml"))}
                  type="button"
                >
                  Aç
                </button>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="card">
        <div className="card-header-row">
          <div>
            <h2 className="section-title">Bulunan Dosyalar</h2>
            <p className="section-subtitle">Bu dönem için görülen XML ve ZIP dosyaları</p>
          </div>
        </div>

        <div className="file-checklist compact-file-checklist">
          {period.dosyalar.map((dosya) => (
            <div className="file-row compact-file-row" key={dosya.id}>
              <div>
                <strong>{dosya.etiket}</strong>
                <p>{dosya.dosyaAdi}</p>
                <small>{dosya.yol}</small>
              </div>
              <div className="file-meta">
                <Badge tone={statusTone(dosya.durum)}>{dosya.durum}</Badge>
                <button className="button button-secondary button-small" onClick={() => void openPath(dosya.yol)} type="button">
                  Dosyayı Aç
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>

      {supportFiles.length > 0 ? (
        <section className="card">
          <div className="card-header-row">
            <div>
              <h2 className="section-title">Ek Dosyalar</h2>
              <p className="section-subtitle">Toplu paket ve yardımcı dosyalar</p>
            </div>
          </div>
          <div className="supporting-file-list">
            {supportFiles.map((file) => (
              <button key={file.id} className="supporting-file-item" onClick={() => void openPath(file.yol)} type="button">
                <strong>{file.etiket}</strong>
                <span>{file.dosyaAdi}</span>
                <small>{file.kaynak} • {file.boyut}</small>
              </button>
            ))}
          </div>
        </section>
      ) : null}

      {period.sorunlar.length > 0 ? (
        <section className="card">
          <h2 className="section-title">Uyarılar</h2>
          <div className="issue-list compact-issue-list">
            {period.sorunlar.map((sorun) => (
              <div key={sorun.id} className="issue-item">
                <div className="issue-header">
                  <strong>{sorun.baslik}</strong>
                  <Badge tone={riskTone(sorun.risk)}>{riskIcon(sorun.risk)} {riskLabel(sorun.risk)}</Badge>
                </div>
                <p>{sorun.aciklama}</p>
                <small>Öneri: {sorun.onerilenIslem}</small>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {period.araDonemAtlamasi ? (
        <section className="card">
          <div className="card-header-row">
            <div>
              <h2 className="section-title">Kullanici Istisnasi</h2>
              <p className="section-subtitle">Donem kutusu kirmizi kalir, ancak bu kaydi genel uyaridan cikarabilirsiniz.</p>
            </div>
          </div>
          <div className="issue-list compact-issue-list">
            <textarea
              className="compact-search-input"
              onChange={(event) => setOverrideNote(event.target.value)}
              placeholder="Aciklama yazin"
              rows={3}
              value={overrideNote}
            />
            <div className="button-row">
              <button
                className="button button-secondary"
                onClick={() => onSetPeriodOverride?.(period.id, true, overrideNote)}
                type="button"
              >
                Sorun Yok Olarak Isaretle
              </button>
              {period.kullaniciIstisnasi ? (
                <button
                  className="button button-secondary"
                  onClick={() => onSetPeriodOverride?.(period.id, false, "")}
                  type="button"
                >
                  Istisnayi Kaldir
                </button>
              ) : null}
            </div>
            {period.kullaniciIstisnasi ? (
              <small>Kayitli not: {period.kullaniciIstisnaNotu || "-"} {period.kullaniciIstisnaTarihi ? `(${period.kullaniciIstisnaTarihi})` : ""}</small>
            ) : null}
          </div>
        </section>
      ) : null}
    </div>
  );
}
