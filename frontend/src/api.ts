import { mockData } from "./mockData";
import type { HizliKesifSonucu, IslemDurumu, SistemDurumu, TaramaVerisi, XmlOnizleme } from "./types";

declare global {
  interface Window {
    pywebview?: {
      api: {
        get_initial_data: () => Promise<TaramaVerisi>;
        scan_archive: (rootPath: string, profile?: string) => Promise<TaramaVerisi>;
        start_scan_archive: (rootPath: string, profile?: string) => Promise<boolean>;
        start_history_scan_archive: (rootPath: string, profile?: string) => Promise<boolean>;
        start_scan_years_archive: (rootPath: string, years: number[], profile?: string) => Promise<boolean>;
        choose_folder: () => Promise<string | null>;
        quick_discover: (rootPath: string) => Promise<HizliKesifSonucu>;
        start_quick_discover: (rootPath: string) => Promise<boolean>;
        get_job_status: () => Promise<IslemDurumu>;
        cancel_job: () => Promise<boolean>;
        choose_license_file: () => Promise<string | null>;
        choose_xml_file: () => Promise<string | null>;
        install_license: (sourcePath: string) => Promise<{ ok: boolean; license: SistemDurumu["lisans"]; taramaVerisi?: TaramaVerisi | null }>;
        get_system_status: () => Promise<SistemDurumu>;
        read_xml_preview: (targetPath: string) => Promise<XmlOnizleme>;
        open_path: (targetPath: string) => Promise<boolean>;
        open_external_url: (targetUrl: string) => Promise<boolean>;
        export_excel_report: (selected_year?: string) => Promise<string | null>;
        export_pdf_report: (selected_year?: string) => Promise<string | null>;
        export_json_report: () => Promise<string | null>;
        set_period_override: (periodId: string, approved: boolean, note?: string) => Promise<TaramaVerisi>;
      };
    };
  }
}

function isDesktopRuntime() {
  return window.location.protocol === "file:";
}

async function waitForDesktopApi(timeoutMs = 4000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (window.pywebview?.api) {
      return window.pywebview.api;
    }
    await new Promise((resolve) => window.setTimeout(resolve, 80));
  }
  return window.pywebview?.api ?? null;
}

export function emptyDashboardData(): TaramaVerisi {
  return {
    dashboard: {
      profil: "Genel",
      arsivKlasoru: "",
      sonTarama: "Henuz tarama yapilmadi",
      toplamFirma: 0,
      toplamDonem: 0,
      eksikDonem: 0,
      kritikHata: 0,
      genelSkor: 0,
      riskDagilimi: { OK: 0, LOW: 0, MEDIUM: 0, HIGH: 0, CRITICAL: 0 },
      sonOzet: [],
      ilerleme: {
        asama: "Arsiv klasoru bekleniyor",
        yuzde: 0,
        islenenDosya: 0,
        toplamDosya: 0,
        bulunanMukellef: 0,
        hataSayisi: 0,
      },
      mukellefKartlari: [],
      islemGunlugu: [],
    },
    donemler: [],
    teknik_ozet: {},
    sistemDurumu: undefined,
    acilisXmlYolu: "",
  };
}

export async function getInitialData(): Promise<TaramaVerisi> {
  const api = await waitForDesktopApi();
  if (api?.get_initial_data) {
    return api.get_initial_data();
  }
  if (isDesktopRuntime()) {
    return emptyDashboardData();
  }
  return mockData;
}

export async function runArchiveScan(rootPath: string, profile = "auto"): Promise<TaramaVerisi> {
  const api = await waitForDesktopApi();
  if (api?.scan_archive) {
    return api.scan_archive(rootPath, profile);
  }
  return isDesktopRuntime() ? emptyDashboardData() : mockData;
}

export async function chooseFolder(): Promise<string | null> {
  const api = await waitForDesktopApi();
  if (api?.choose_folder) {
    return api.choose_folder();
  }
  return null;
}

export async function runQuickDiscovery(rootPath: string): Promise<HizliKesifSonucu> {
  const api = await waitForDesktopApi();
  if (api?.quick_discover) {
    return api.quick_discover(rootPath);
  }
  return {
    baslangicKlasoru: rootPath,
    bulundu: false,
    adaylar: [],
  };
}

export async function startQuickDiscovery(rootPath: string): Promise<boolean> {
  const api = await waitForDesktopApi();
  if (api?.start_quick_discover) {
    return api.start_quick_discover(rootPath);
  }
  return !isDesktopRuntime();
}

export async function startArchiveScan(rootPath: string, profile = "auto"): Promise<boolean> {
  const api = await waitForDesktopApi();
  if (api?.start_scan_archive) {
    return api.start_scan_archive(rootPath, profile);
  }
  return !isDesktopRuntime();
}

export async function startHistoryArchiveScan(rootPath: string, profile = "auto"): Promise<boolean> {
  const api = await waitForDesktopApi();
  if (api?.start_history_scan_archive) {
    return api.start_history_scan_archive(rootPath, profile);
  }
  return !isDesktopRuntime();
}

export async function startScanYearsArchive(rootPath: string, years: number[], profile = "auto"): Promise<boolean> {
  const api = await waitForDesktopApi();
  if (api?.start_scan_years_archive) {
    return api.start_scan_years_archive(rootPath, years, profile);
  }
  return !isDesktopRuntime();
}

export async function getJobStatus(): Promise<IslemDurumu> {
  const api = await waitForDesktopApi();
  if (api?.get_job_status) {
    return api.get_job_status();
  }
  return {
    aktif: false,
    tamamlandi: false,
    basarili: true,
    iptalIstenmis: false,
    iptalEdildi: false,
    islemTuru: "idle",
    asama: "Beklemede",
    mesaj: "Hazir",
    detay: "",
    yuzde: 0,
    tarananKlasor: 0,
    adaySayisi: 0,
    mukellefSayisi: 0,
    donemSayisi: 0,
    gecenSureSaniye: 0,
    sonIslem: "",
    loglar: [],
    hata: "",
    tumYillar: [],
    aktifYil: null,
    bekleyenYillar: [],
    tamamlananYillar: [],
    yilIlerleme: {},
  };
}

export async function cancelJob(): Promise<boolean> {
  const api = await waitForDesktopApi();
  if (api?.cancel_job) {
    return api.cancel_job();
  }
  return false;
}

export async function chooseLicenseFile(): Promise<string | null> {
  const api = await waitForDesktopApi();
  if (api?.choose_license_file) {
    return api.choose_license_file();
  }
  return null;
}

export async function chooseXmlFile(): Promise<string | null> {
  const api = await waitForDesktopApi();
  if (api?.choose_xml_file) {
    return api.choose_xml_file();
  }
  return null;
}

export async function installLicense(sourcePath: string): Promise<{ ok: boolean; license: SistemDurumu["lisans"]; taramaVerisi?: TaramaVerisi | null } | null> {
  const api = await waitForDesktopApi();
  if (api?.install_license) {
    return api.install_license(sourcePath);
  }
  return null;
}

export async function getSystemStatus(): Promise<SistemDurumu | null> {
  const api = await waitForDesktopApi();
  if (api?.get_system_status) {
    return api.get_system_status();
  }
  return null;
}

export async function readXmlPreview(targetPath: string): Promise<XmlOnizleme | null> {
  const api = await waitForDesktopApi();
  if (api?.read_xml_preview) {
    return api.read_xml_preview(targetPath);
  }
  return null;
}

export async function openPath(targetPath: string): Promise<boolean> {
  const api = await waitForDesktopApi();
  if (api?.open_path) {
    return api.open_path(targetPath);
  }
  return false;
}

export async function openExternalUrl(targetUrl: string): Promise<boolean> {
  const api = await waitForDesktopApi();
  if (api?.open_external_url) {
    return api.open_external_url(targetUrl);
  }
  window.open(targetUrl, "_blank", "noopener,noreferrer");
  return true;
}

export async function exportExcelReport(selectedYear?: string): Promise<string | null> {
  const api = await waitForDesktopApi();
  if (api?.export_excel_report) {
    return api.export_excel_report(selectedYear);
  }
  return null;
}

export async function exportPdfReport(selectedYear?: string): Promise<string | null> {
  const api = await waitForDesktopApi();
  if (api?.export_pdf_report) {
    return api.export_pdf_report(selectedYear);
  }
  return null;
}

export async function exportJsonReport(): Promise<string | null> {
  const api = await waitForDesktopApi();
  if (api?.export_json_report) {
    return api.export_json_report();
  }
  return null;
}

export async function setPeriodOverride(periodId: string, approved: boolean, note = ""): Promise<TaramaVerisi | null> {
  const api = await waitForDesktopApi();
  if (api?.set_period_override) {
    return api.set_period_override(periodId, approved, note);
  }
  return null;
}
