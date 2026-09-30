import { lazy, Suspense, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import {
  cancelJob,
  chooseFolder,
  chooseLicenseFile,
  chooseXmlFile,
  emptyDashboardData,
  exportExcelReport,
  exportPdfReport,
  getInitialData,
  getJobStatus,
  getSystemStatus,
  installLicense,
  openExternalUrl,
  openPath,
  readXmlPreview,
  setPeriodOverride,
  startArchiveScan,
  startScanYearsArchive,
} from "./api";
import brandLogo from "./assets/brand-logo.png";
import { XmlViewerModal } from "./components/XmlViewerModal";
import type { DonemKaydi, IslemDurumu, MukellefKarti, SistemDurumu, TaramaVerisi } from "./types";

const DashboardView = lazy(async () => ({
  default: (await import("./components/DashboardView")).DashboardView,
}));
const ResultsView = lazy(async () => ({
  default: (await import("./components/ResultsView")).ResultsView,
}));
const PeriodDetailView = lazy(async () => ({
  default: (await import("./components/PeriodDetailView")).PeriodDetailView,
}));
const TaxpayerProfileView = lazy(async () => ({
  default: (await import("./components/TaxpayerProfileView")).TaxpayerProfileView,
}));

type Sayfa = "dashboard" | "results" | "detail" | "profile";

interface XmlKaynak {
  key: string;
  label: string;
  path: string;
  count: number;
}

interface LisansSonucDurumu {
  durum: "success" | "error";
  baslik: string;
  mesaj: string;
  eylemEtiketi: string;
}

type YilHazirlikDurumu = "ready" | "active" | "queued";

interface YilDurumuOgesi {
  year: number;
  status: YilHazirlikDurumu;
  progress: number;
  metric: string;
}

interface DonemKarsilastirmaOgesi {
  id: string;
  oncekiEtiket: string;
  simdikiEtiket: string;
  oncekiSayi: number;
  simdikiSayi: number;
  eksikFirmalar: string[];
  ozelDurumluFirmalar: string[];
}

const SKYNONLABS_URL = "https://skynonlabs.com/";
const SUPPORT_BASE_URL = "https://support.skynonlabs.com/";
const LABEL_KILAVUZ = "K\u0131lavuz";
const LABEL_HAKKINDA = "Hakk\u0131nda";

function App() {
  const [sayfa, setSayfa] = useState<Sayfa>("dashboard");
  const [data, setData] = useState<TaramaVerisi | null>(null);
  const [seciliId, setSeciliId] = useState<string | null>(null);
  const [seciliMukellefId, setSeciliMukellefId] = useState<string | null>(null);
  const [kartBaslangici, setKartBaslangici] = useState(0);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [taraniyor, setTaraniyor] = useState(false);
  const [durumMesaji, setDurumMesaji] = useState("");
  const [aramaMetni, setAramaMetni] = useState("");
  const [seciliYil, setSeciliYil] = useState("");
  const [baslangicKlasoru, setBaslangicKlasoru] = useState("");
  const [klasorSecildi, setKlasorSecildi] = useState(false);
  const [klasorUyarisi, setKlasorUyarisi] = useState("");
  const [islemDurumu, setIslemDurumu] = useState<IslemDurumu | null>(null);
  const [sistemDurumu, setSistemDurumu] = useState<SistemDurumu | null>(null);
  const [lisansAcik, setLisansAcik] = useState(false);
  const [lisansYukleniyor, setLisansYukleniyor] = useState(false);
  const [lisansSonucu, setLisansSonucu] = useState<LisansSonucDurumu | null>(null);
  const [lisansKopyaMesaji, setLisansKopyaMesaji] = useState("");
  const [logMenuAcik, setLogMenuAcik] = useState(false);
  const [uyariPopupAcik, setUyariPopupAcik] = useState(false);
  const [kilavuzAcik, setKilavuzAcik] = useState(false);
  const [xmlPopupAcik, setXmlPopupAcik] = useState(false);
  const [xmlKaynaklar, setXmlKaynaklar] = useState<XmlKaynak[]>([]);
  const [xmlKaynakKey, setXmlKaynakKey] = useState<string | null>(null);
  const [xmlIcerik, setXmlIcerik] = useState("");
  const [xmlDosyaAdi, setXmlDosyaAdi] = useState("");
  const [xmlKisaltildi, setXmlKisaltildi] = useState(false);
  const [xmlYukleniyor, setXmlYukleniyor] = useState(false);
  const [xmlBaslik, setXmlBaslik] = useState("");
  const [xmlAltBaslik, setXmlAltBaslik] = useState("");
  const [exporting, setExporting] = useState<"excel" | "pdf" | null>(null);
  const [scanMenuAcik, setScanMenuAcik] = useState(false);
  const pollingRef = useRef<number | null>(null);
  const gecikmeliArama = useDeferredValue(aramaMetni);

  useEffect(() => {
    void (async () => {
      try {
        const initialData = await getInitialData();
        setData(initialData);
        setSistemDurumu(initialData.sistemDurumu ?? null);
        setBaslangicKlasoru(initialData.dashboard?.arsivKlasoru ?? "");
        setKlasorSecildi(Boolean(initialData.dashboard?.arsivKlasoru));
        if (initialData.sistemDurumu == null) {
          const freshStatus = await getSystemStatus();
          if (freshStatus) {
            setSistemDurumu(freshStatus);
          }
        }
        setSeciliId(null);
        setSeciliMukellefId(null);
        if (initialData.acilisXmlYolu) {
          await openXmlPathInModal(initialData.acilisXmlYolu, "Açılan XML", "Windows üzerinden açılan XML dosyası");
        }
      } catch {
        setData(emptyDashboardData());
        setKlasorSecildi(false);
        setBaslangicKlasoru("");
        setKlasorUyarisi("Arayüz ilk veriyi yüklerken sorun yaşadı. Klasörü yeniden seçin.");
      } finally {
        setYukleniyor(false);
      }
    })();
    return () => stopPolling();
  }, []);

  useEffect(() => {
    if (taraniyor) {
      setScanMenuAcik(false);
    }
  }, [taraniyor]);

  const aktifKokKlasor = baslangicKlasoru;
  const isProMode = Boolean(sistemDurumu?.lisans?.valid);
  const hasScanResults = ((data?.dashboard.mukellefKartlari.length ?? 0) > 0) || ((data?.donemler.length ?? 0) > 0);
  const dashboardData = useMemo(() => {
    if (!data) {
      return null;
    }
    if (klasorSecildi) {
      return data;
    }
    return {
      ...data,
      dashboard: {
        ...data.dashboard,
        arsivKlasoru: "",
        toplamFirma: 0,
        toplamDonem: 0,
        eksikDonem: 0,
        kritikHata: 0,
        sonOzet: [],
        mukellefKartlari: [],
      },
      donemler: [],
    };
  }, [data, klasorSecildi]);
  const seciliDonem = useMemo(() => data?.donemler.find((item) => item.id === seciliId) ?? null, [data, seciliId]);
  const discoveredYears = useMemo(
    () => (dashboardData?.dashboard.tumYillar ?? []).filter((year) => Number.isInteger(year)).sort((a, b) => b - a),
    [dashboardData],
  );
  const availableResultYears = useMemo(() => {
    const rowYears = (dashboardData?.donemler ?? []).map((row) => row.yil).filter(Boolean);
    const cardYears = (dashboardData?.dashboard.mukellefKartlari ?? []).map((card) => card.yil).filter(Boolean);
    return Array.from(new Set([...rowYears, ...cardYears])).sort((a, b) => b - a);
  }, [dashboardData]);
  const dashboardYears = useMemo(
    () => Array.from(new Set([...availableResultYears, ...discoveredYears])).sort((a, b) => b - a),
    [availableResultYears, discoveredYears],
  );
  const validatedReadyYears = useMemo(
    () => Array.from(new Set(dashboardData?.dashboard.hazirYillar ?? [])).sort((a, b) => b - a),
    [dashboardData],
  );
  const dashboardYearStatuses = useMemo(
    () => buildYearStatuses(dashboardYears, validatedReadyYears, islemDurumu),
    [dashboardYears, validatedReadyYears, islemDurumu],
  );
  const scanMenuYears = useMemo(
    () => dashboardYearStatuses.map((item) => ({ year: item.year, status: item.status })),
    [dashboardYearStatuses],
  );
  const aktifYil = useMemo(() => {
    if (!dashboardYears.length) {
      return "";
    }
    if (seciliYil && dashboardYears.includes(Number(seciliYil))) {
      return seciliYil;
    }
    return String(dashboardYears[0]);
  }, [dashboardYears, seciliYil]);
  const gercekUyarilar = useMemo(() => {
    const rows = dashboardData?.donemler ?? [];
    if (!aktifYil || aktifYil === "Tüm Yıllar") {
      return rows.filter((row) => row.risk !== "OK" && !row.kullaniciIstisnasi);
    }
    return rows.filter((row) => row.risk !== "OK" && !row.kullaniciIstisnasi && String(row.yil) === aktifYil);
  }, [dashboardData, aktifYil]);
  const uyariFirmaSayisi = useMemo(
    () => new Set(gercekUyarilar.map((row) => `${row.firma}|${row.vkn}`)).size,
    [gercekUyarilar],
  );
  const sonTaramaMetni = useMemo(() => formatLastScanText(dashboardData?.dashboard.sonTarama), [dashboardData]);

  const filteredCards = useMemo(() => {
    const cards = dashboardData?.dashboard.mukellefKartlari ?? [];
    const normalized = normalizeText(gecikmeliArama);
    const targetYear = !aktifYil || aktifYil === "Tüm Yıllar" ? null : Number(aktifYil);
    return cards.filter((card) => {
      if (targetYear !== null && card.yil !== targetYear) {
        return false;
      }
      if (!normalized) {
        return true;
      }
      return matchesCard(card, normalized);
    }).sort(sortTaxpayerCards);
  }, [dashboardData, gecikmeliArama, aktifYil]);

  const visibleCards = useMemo(
    () => filteredCards.slice(kartBaslangici, kartBaslangici + 3),
    [filteredCards, kartBaslangici],
  );
  const dashboardSummary = useMemo(() => ({
    toplamFirma: filteredCards.length,
    gonderilmisFirma: filteredCards.filter((card) => card.donemler.some((month) => Boolean(month.donemId))).length,
    uyariFirma: filteredCards.filter((card) => (card.durumGrubu ?? "green") !== "green").length,
  }), [filteredCards]);
  const donemKarsilastirmalari = useMemo(
    () => buildQuarterComparisons(data?.donemler ?? [], aktifYil, gecikmeliArama),
    [data, aktifYil, gecikmeliArama],
  );
  const donemKarsilastirmaEtiketi = useMemo(() => {
    const firstAlert = donemKarsilastirmalari.find((item) => item.eksikFirmalar.length > 0) ?? donemKarsilastirmalari[0];
    if (!firstAlert) {
      return "";
    }
    return `${firstAlert.oncekiEtiket}/${firstAlert.simdikiEtiket}: ${firstAlert.oncekiSayi}-${firstAlert.simdikiSayi}`;
  }, [donemKarsilastirmalari]);
  const selectedTaxpayerCard = useMemo(
    () => (dashboardData?.dashboard.mukellefKartlari ?? []).find((card) => card.id === seciliMukellefId) ?? null,
    [dashboardData, seciliMukellefId],
  );
  const selectedTaxpayerPeriods = useMemo(() => {
    if (!selectedTaxpayerCard) {
      return [];
    }
    if (selectedTaxpayerCard.demoLocked) {
      return [];
    }
    return (data?.donemler ?? [])
      .filter(
        (row) =>
          row.firma === selectedTaxpayerCard.gosterimAdi &&
          row.vkn === selectedTaxpayerCard.vknTckn &&
          row.yil === selectedTaxpayerCard.yil,
      )
      .sort((a, b) => a.ay.localeCompare(b.ay, "tr"));
  }, [data, selectedTaxpayerCard]);
  const demoHakMetni = !isProMode
    ? `Demo ${sistemDurumu?.lisans?.demo?.used_count ?? 0}/${sistemDurumu?.lisans?.demo?.limit ?? 4}`
    : "";

  useEffect(() => {
    setKartBaslangici(0);
  }, [gecikmeliArama, seciliYil]);

  useEffect(() => {
    if (!dashboardYears.length) {
      setSeciliYil("");
      return;
    }
    if (!seciliYil || seciliYil === "Tüm Yıllar" || !dashboardYears.includes(Number(seciliYil))) {
      setSeciliYil(String(dashboardYears[0]));
    }
  }, [dashboardYears.join("|"), seciliYil]);

  useEffect(() => {
    if (!filteredCards.length) {
      setSeciliMukellefId(null);
      return;
    }
    if (!seciliMukellefId || !filteredCards.some((card) => card.id === seciliMukellefId)) {
      setSeciliMukellefId(filteredCards[0].id);
    }
  }, [filteredCards, seciliMukellefId]);

  const progressYuzde = islemDurumu?.aktif
    ? Math.max(islemDurumu.yuzde, 8)
    : ((data?.dashboard.toplamDonem ?? 0) > 0)
      ? 100
      : 0;
  const progressMesaj = buildProgressMessage(islemDurumu, data);
  const progressStats = buildProgressStats(islemDurumu);

  async function handleChooseFolder() {
    const selectedFolder = await chooseFolder();
    if (!selectedFolder) {
      return;
    }
    setBaslangicKlasoru(selectedFolder);
    setKlasorSecildi(true);
    setKlasorUyarisi("");
    setData((current) => {
      const base = current ?? emptyDashboardData();
      return {
        ...base,
        dashboard: {
          ...base.dashboard,
          arsivKlasoru: selectedFolder,
          sonTarama: "Henüz tarama yapılmadı",
          toplamFirma: 0,
          toplamDonem: 0,
          eksikDonem: 0,
          kritikHata: 0,
          sonOzet: [],
          mukellefKartlari: [],
          ilerleme: {
            ...base.dashboard.ilerleme,
            asama: "e-Defter klasörü seçildi",
            yuzde: 0,
            islenenDosya: 0,
            toplamDosya: 0,
            bulunanMukellef: 0,
            hataSayisi: 0,
          },
        },
        donemler: [],
      };
    });
    setSeciliId(null);
    setSeciliMukellefId(null);
    setDurumMesaji(`Müşteri klasörü seçildi: ${selectedFolder}`);
    setSayfa("dashboard");
  }

  async function handleStartScan(targetPath?: string) {
    const rootPath = targetPath || aktifKokKlasor;
    if (!rootPath) {
      return;
    }
    setTaraniyor(true);
    setDurumMesaji("e-Defter taraması başlatıldı.");
    setIslemDurumu((current) => ({
      ...(current || {
        aktif: false,
        tamamlandi: false,
        basarili: true,
        iptalIstenmis: false,
        iptalEdildi: false,
        islemTuru: "scan",
        asama: "Hazırlanıyor",
        mesaj: "Tarama kuyruğu hazırlanıyor...",
        detay: rootPath,
        yuzde: 0,
        tarananKlasor: 0,
        adaySayisi: 0,
        mukellefSayisi: 0,
        donemSayisi: 0,
        gecenSureSaniye: 0,
        sonIslem: rootPath,
        loglar: [],
        hata: "",
        tumYillar: [],
        aktifYil: null,
        bekleyenYillar: [],
        tamamlananYillar: [],
        yilIlerleme: {},
      }),
      aktif: true,
      tamamlandi: false,
      basarili: true,
      islemTuru: "scan",
      asama: "Hazırlanıyor",
      mesaj: "Tarama kuyruğu hazırlanıyor...",
      detay: rootPath,
      sonIslem: rootPath,
    }));
    await new Promise((resolve) => window.setTimeout(resolve, 0));
    const started = await startArchiveScan(rootPath);
    if (!started) {
      setTaraniyor(false);
      const status = await getJobStatus();
      setIslemDurumu(status);
      setDurumMesaji(status.hata || status.mesaj || "Tarama başlatılamadı.");
      await refreshSystemStatus();
      return;
    }
    startPolling();
  }

  async function handleStartSelectedYears(years: number[]) {
    const rootPath = aktifKokKlasor;
    if (!rootPath || years.length === 0) {
      return;
    }
    setTaraniyor(true);
    setDurumMesaji(`${years.join(", ")} taraması başlatıldı.`);
    setIslemDurumu((current) => ({
      ...(current || {
        aktif: false,
        tamamlandi: false,
        basarili: true,
        iptalIstenmis: false,
        iptalEdildi: false,
        islemTuru: "history",
        asama: "Hazırlanıyor",
        mesaj: "Seçilen yıl kuyruğu hazırlanıyor...",
        detay: years.join(", "),
        yuzde: 0,
        tarananKlasor: 0,
        adaySayisi: 0,
        mukellefSayisi: 0,
        donemSayisi: 0,
        gecenSureSaniye: 0,
        sonIslem: rootPath,
        loglar: [],
        hata: "",
        tumYillar: [],
        aktifYil: null,
        bekleyenYillar: [],
        tamamlananYillar: [],
        yilIlerleme: {},
      }),
      aktif: true,
      tamamlandi: false,
      basarili: true,
      islemTuru: "history",
      asama: "Hazırlanıyor",
      mesaj: "Seçilen yıl kuyruğu hazırlanıyor...",
      detay: years.join(", "),
      sonIslem: rootPath,
    }));
    await new Promise((resolve) => window.setTimeout(resolve, 0));
    const started = await startScanYearsArchive(rootPath, years);
    if (!started) {
      setTaraniyor(false);
      const status = await getJobStatus();
      setIslemDurumu(status);
      setDurumMesaji(status.hata || status.mesaj || "Yıl taraması başlatılamadı.");
      await refreshSystemStatus();
      return;
    }
    startPolling();
  }

  async function handleCancelJob() {
    const cancelled = await cancelJob();
    if (cancelled) {
      setDurumMesaji("İptal isteği gönderildi.");
    }
  }

  function handleResetView() {
    stopPolling();
    setTaraniyor(false);
    setIslemDurumu(null);
    setDurumMesaji("");
    setLisansAcik(false);
    setLogMenuAcik(false);
    setUyariPopupAcik(false);
  }

  function startPolling() {
    stopPolling();
    pollingRef.current = window.setInterval(() => {
      void pollJobStatus();
    }, 450);
    void pollJobStatus();
  }

  function stopPolling() {
    if (pollingRef.current !== null) {
      window.clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }

  async function pollJobStatus() {
    const status = await getJobStatus();
    setIslemDurumu(status);
    setDurumMesaji(status.detay || status.mesaj);
    if (status.aktif && status.taramaVerisi) {
      const partialResult = status.taramaVerisi;
      setData(partialResult);
      setSistemDurumu(partialResult.sistemDurumu ?? null);
      setBaslangicKlasoru(partialResult.dashboard?.arsivKlasoru ?? baslangicKlasoru);
      setKlasorSecildi(true);
      setKlasorUyarisi("");
      setSeciliId((current) => current ?? partialResult.donemler[0]?.id ?? null);
      setSeciliMukellefId((current) => current ?? partialResult.dashboard.mukellefKartlari[0]?.id ?? null);
      setTaraniyor(true);
    }
    if (!status.aktif && status.tamamlandi) {
      stopPolling();
      if (!status.basarili) {
        setTaraniyor(false);
        setDurumMesaji(status.hata || "Islem sirasinda hata olustu.");
        return;
      }

      if (status.taramaVerisi) {
        const scanResult = status.taramaVerisi;
        const hasArchiveData =
          (scanResult.dashboard.mukellefKartlari?.length ?? 0) > 0 ||
          (scanResult.donemler?.length ?? 0) > 0;
        if (!hasArchiveData) {
          setData(emptyDashboardData());
          setBaslangicKlasoru("");
          setKlasorSecildi(false);
          setSeciliId(null);
          setSeciliMukellefId(null);
          setTaraniyor(false);
          setDurumMesaji("e-Defter bulunamadı. Doğru klasörü seçin.");
          setKlasorUyarisi("e-Defter bulunamadı. Doğru klasörü seçin.");
          return;
        }
        setData(scanResult);
        setSistemDurumu(scanResult.sistemDurumu ?? null);
        setBaslangicKlasoru(scanResult.dashboard?.arsivKlasoru ?? baslangicKlasoru);
        setSeciliId(scanResult.donemler[0]?.id ?? null);
        setSeciliMukellefId(scanResult.dashboard.mukellefKartlari[0]?.id ?? null);
        setKlasorSecildi(true);
        setKlasorUyarisi("");
        setKartBaslangici(0);
        setTaraniyor(false);
        setDurumMesaji("Tarama tamamlandı.");
      }
    }
  }

  async function refreshSystemStatus() {
    const status = await getSystemStatus();
    if (status) {
      setSistemDurumu(status);
    }
  }

  async function handleInstallLicense() {
    if (lisansYukleniyor) {
      return;
    }
    const sourcePath = await chooseLicenseFile();
    if (!sourcePath) {
      return;
    }
    setLisansYukleniyor(true);
    const result = await installLicense(sourcePath);
    if (!result) {
      setLisansYukleniyor(false);
      return;
    }
    const successMessage = result.license.valid
      ? "Lisans işlemi başarılıdır. Pro Modu etkinleştirildi."
      : result.license.message;
    setDurumMesaji(successMessage);
    if (result.taramaVerisi) {
      const refreshedData = result.taramaVerisi;
      setData(refreshedData);
      setSeciliId((current) => current && refreshedData.donemler.some((row) => row.id === current) ? current : refreshedData.donemler[0]?.id ?? null);
      setSeciliMukellefId((current) => current && refreshedData.dashboard.mukellefKartlari.some((card) => card.id === current) ? current : refreshedData.dashboard.mukellefKartlari[0]?.id ?? null);
    }
    setSistemDurumu((current) => current ? ({
      ...current,
      lisans: result.license,
      uygulama: {
        ...current.uygulama,
        mod: result.license.valid ? "Pro Modu" : result.license.label,
      },
    }) : current);
    const refreshedStatus = await getSystemStatus();
    if (refreshedStatus) {
      setSistemDurumu({
        ...refreshedStatus,
        uygulama: {
          ...refreshedStatus.uygulama,
          mod: result.license.valid ? "Pro Modu" : refreshedStatus.uygulama.mod,
        },
      });
    }
    if (result.license.valid) {
      setLisansSonucu({
        durum: "success",
        baslik: "Lisans ekleme başarılı",
        mesaj: "Program Pro Modu olarak güncellendi.",
        eylemEtiketi: "Tamam",
      });
      setLisansAcik(true);
    } else {
      setLisansSonucu({
        durum: "error",
        baslik: "Lisans doğrulanamadı",
        mesaj: result.license.message || "Lisans dosyası geçersiz.",
        eylemEtiketi: "Tekrar dene",
      });
      setLisansAcik(true);
    }
    setLisansYukleniyor(false);
  }

  async function handleCopyLicenseCode() {
    const deviceCode = sistemDurumu?.lisans.device_code;
    if (!deviceCode) {
      return;
    }
    await navigator.clipboard.writeText(deviceCode);
    setLisansKopyaMesaji("Panoya kopyalandı.");
    window.setTimeout(() => {
      setLisansKopyaMesaji((current) => (current === "Panoya kopyalandı." ? "" : current));
    }, 2200);
  }

  async function handleToggleLicense() {
    setLogMenuAcik(false);
    if (lisansAcik) {
      setLisansSonucu(null);
    }
    if (!lisansAcik && !sistemDurumu) {
      const freshStatus = await getSystemStatus();
      if (freshStatus) {
        setSistemDurumu(freshStatus);
      }
    }
    setLisansAcik((value) => !value);
  }

  function handleLicenseResultAction() {
    if (lisansSonucu?.durum === "success") {
      setLisansAcik(false);
      setLisansSonucu(null);
      return;
    }
    setLisansSonucu(null);
  }

  async function openXmlKaynak(source: XmlKaynak) {
    setXmlYukleniyor(true);
    setXmlKaynakKey(source.key);
    const preview = await readXmlPreview(source.path);
    setXmlYukleniyor(false);
    if (!preview?.ok) {
      setXmlIcerik(preview?.message || "XML önizleme alınamadı.");
      setXmlDosyaAdi(source.path);
      setXmlKisaltildi(false);
      return;
    }
    setXmlIcerik(preview.content || "");
    setXmlDosyaAdi(preview.fileName || source.path);
    setXmlKisaltildi(Boolean(preview.truncated));
  }

  async function handleOpenPeriod(periodId: string) {
    const period = data?.donemler.find((item) => item.id === periodId) ?? null;
    if (!period) {
      return;
    }
    if (period.demoLocked) {
      setDurumMesaji(period.demoMessage || "Bu firma Demo Mod siniri disinda. Pro Mod ile acilir.");
      return;
    }
    if (period.risk === "OK") {
      const sources = buildXmlSources(period);
      if (sources.length > 0) {
        setXmlKaynaklar(sources);
        setXmlBaslik(`${period.firma} - ${period.ay}/${period.yil}`);
        setXmlAltBaslik("Yevmiye, kebir ve GİB onaylı suret görüntüleme");
        setXmlPopupAcik(true);
        await openXmlKaynak(sources[0]);
        return;
      }
    }
    setSeciliId(periodId);
    setSayfa("detail");
  }

  function handleOpenTaxpayerProfile(taxpayerId: string) {
    setSeciliMukellefId(taxpayerId);
    setSayfa("profile");
  }

  function handleOpenTaxpayerProfileByIdentity(firma: string, vkn: string, yil: number) {
    const card = (dashboardData?.dashboard.mukellefKartlari ?? []).find(
      (item) => item.gosterimAdi === firma && item.vknTckn === vkn && item.yil === yil,
    );
    if (!card) {
      return;
    }
    setSeciliMukellefId(card.id);
    setSeciliYil(String(yil));
    setSayfa("profile");
  }

  async function handleExport(kind: "excel" | "pdf") {
    setExporting(kind);
    const reportPath = kind === "excel" ? await exportExcelReport(aktifYil) : await exportPdfReport(aktifYil);
    setExporting(null);
    if (reportPath) {
      setDurumMesaji(`${kind.toUpperCase()} çıktısı hazırlandı.`);
      await openPath(reportPath);
    }
  }

  async function openXmlPathInModal(xmlPath: string, label: string, subtitle: string) {
    const source = {
      key: "manual-xml",
      label,
      path: xmlPath,
      count: 1,
    };
    setXmlKaynaklar([source]);

    setXmlBaslik("e-Defter Görüntüle");
    setXmlAltBaslik(subtitle);
    setXmlPopupAcik(true);
    await openXmlKaynak(source);
  }

  async function handleOpenXmlFile() {
    const selectedXml = await chooseXmlFile();
    if (!selectedXml) {
      return;
    }
    await openXmlPathInModal(selectedXml, "Seçilen XML", "Seçilen XML dosyası uygulama içinde görüntüleniyor");
  }

  async function handleOpenControlXml(period: DonemKaydi, controlId: string) {
    if (period.demoLocked) {
      setDurumMesaji(period.demoMessage || "Bu XML yalnizca Pro Modda acilir.");
      return;
    }
    const control = period.kontroller.find((item) => item.id === controlId);
    if (!control) {
      return;
    }
    const xmlPaths = control.dosyaYollari.filter((path) => path.toLocaleLowerCase("tr-TR").endsWith(".xml"));
    if (xmlPaths.length === 0) {
      setDurumMesaji("Bu kontrol kalemi için gösterilecek XML bulunamadı.");
      return;
    }
    const sources = xmlPaths.map((path, index) => ({
      key: `${control.id}-${index}`,
      label: xmlPaths.length > 1 ? `${control.etiket} ${index + 1}` : control.etiket,
      path,
      count: 1,
    }));
    setXmlKaynaklar(sources);
    setXmlBaslik(`${period.firma} - ${control.etiket}`);
    setXmlAltBaslik("Kontrol özeti içinden seçilen XML dosyası");
    setXmlPopupAcik(true);
    await openXmlKaynak(sources[0]);
  }

  async function handleSetPeriodOverride(periodId: string, approved: boolean, note: string) {
    const result = await setPeriodOverride(periodId, approved, note);
    if (!result) {
      setDurumMesaji("Dönem istisna kaydı güncellenemedi.");
      return;
    }
    setData(result);
    setSistemDurumu(result.sistemDurumu ?? null);
    setDurumMesaji(approved ? "Dönem istisna olarak kaydedildi." : "Dönem istisna kaydı kaldırıldı.");
  }

  function closeXmlModal() {
    setXmlPopupAcik(false);
    setXmlKaynaklar([]);
    setXmlKaynakKey(null);
    setXmlIcerik("");
    setXmlDosyaAdi("");
    setXmlKisaltildi(false);
    setXmlYukleniyor(false);
  }

  if (yukleniyor || !data || !dashboardData) {
    return (
      <div className="startup-screen">
        <div className="startup-card">
          <img className="brand-mark brand-mark-large" src={brandLogo} alt="e-Defter Denetim Merkezi" />
          <h1>e-Defter Denetim Merkezi</h1>
          <p>Arayüz hazırlanıyor...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="compact-app-shell">
      <header className="transferio-header">
        <div className="transferio-brand-block">
          <img className="brand-mark" src={brandLogo} alt="e-Defter Denetim Merkezi" />
          <div>
            <div className="transferio-brand-title-row transferio-brand-title-row-compact">
              <h1>e-Defter Denetim Merkezi</h1>
              {demoHakMetni ? <span className="mini-status-pill mini-status-demo">{demoHakMetni}</span> : null}
              <button className="mini-status-pill mini-status-path" onClick={() => void handleChooseFolder()} title={baslangicKlasoru || "Klasör seç"} type="button">
                <span className="mini-status-path-icon" aria-hidden="true">{"📁"}</span>
                <span className="mini-status-path-text">{baslangicKlasoru || "Klasör seç"}</span>
              </button>
              <button
                className={`mini-status-pill mini-status-warning-icon ${gercekUyarilar.length > 0 ? "mini-status-attention" : ""}`}
                onClick={() => setUyariPopupAcik(true)}
                title={`${uyariFirmaSayisi} firma için uyarı var`}
                type="button"
              >
                <span className="warning-badge-icon" aria-hidden="true">!</span>
                <span className="warning-badge-count">{uyariFirmaSayisi}</span>
              </button>
              <button className="mini-status-pill mini-status-blue" onClick={() => setKilavuzAcik(true)} type="button">{LABEL_KILAVUZ}</button>
              <button className="mini-status-pill mini-status-blue" onClick={() => void openExternalUrl(SUPPORT_BASE_URL)} type="button">S.S.S</button>
              <button className="mini-status-pill mini-status-blue" onClick={() => void openExternalUrl(SUPPORT_BASE_URL)} type="button">Destek</button>
              <button className="mini-status-pill mini-status-blue" onClick={() => void openExternalUrl(SKYNONLABS_URL)} type="button">{LABEL_HAKKINDA}</button>
              <div className="header-menu-wrap">
                <button className="mini-status-pill mini-status-blue" onClick={() => { setLogMenuAcik((value) => !value); setLisansAcik(false); }} type="button">
                  Loglar
                </button>
                {logMenuAcik ? (
                  <div className="header-menu-panel">
                    <button className="header-menu-item" onClick={() => sistemDurumu?.yollar.log && void openPath(sistemDurumu.yollar.log)} type="button">Log Klasörü</button>
                    <button className="header-menu-item" onClick={() => sistemDurumu?.yollar.appLog && void openPath(sistemDurumu.yollar.appLog)} type="button">Uygulama Logu</button>
                    <button className="header-menu-item" onClick={() => sistemDurumu?.yollar.debugLog && void openPath(sistemDurumu.yollar.debugLog)} type="button">Hata Ayıklama Logu</button>
                    <button className="header-menu-item" onClick={() => sistemDurumu?.yollar.errorLog && void openPath(sistemDurumu.yollar.errorLog)} type="button">Hata Logu</button>
                    <button className="header-menu-item" onClick={() => sistemDurumu?.yollar.rapor && void openPath(sistemDurumu.yollar.rapor)} type="button">Rapor Klasörü</button>
                  </div>
                ) : null}
              </div>
              <div className="header-menu-wrap">
                <button className="mini-status-pill mini-status-blue" onClick={() => void openExternalUrl("https://buymeacoffee.com/skynonlabs")} type="button">
                  ☕ Destek Ol
                </button>
                {lisansAcik ? (
                  <div className="license-popover">
                    <button className="license-close-button" onClick={() => { setLisansAcik(false); setLisansSonucu(null); }} type="button">
                      X
                    </button>
                    {lisansSonucu ? (
                      <div className={`license-result-banner ${lisansSonucu.durum === "success" ? "license-result-success" : "license-result-error"}`}>
                        <div className="license-success-icon">
                          {lisansSonucu.durum === "success" ? <CheckIcon /> : "!"}
                        </div>
                        <strong>{lisansSonucu.baslik}</strong>
                        <span>{lisansSonucu.mesaj}</span>
                        <button className="button button-secondary license-result-action" onClick={handleLicenseResultAction} type="button">
                          {lisansSonucu.eylemEtiketi}
                        </button>
                      </div>
                    ) : null}
                    {!lisansSonucu ? (
                      <>
                        <strong>Cihaz Kodu</strong>
                        <div className="license-code-box">{sistemDurumu?.lisans.device_code || "-"}</div>
                        {sistemDurumu ? (
                          <div className="license-detail-grid">
                            <span>Lisans Sahibi</span><span>{sistemDurumu.lisans.licensee || "-"}</span>
                            <span>Lisans Modu</span><span>{normalizeModeLabel(sistemDurumu.lisans.valid ? "Pro Modu" : sistemDurumu.lisans.label)}</span>
                            <span>Lisans Tarihi</span><span>{sistemDurumu.lisans.issued_at || "-"}</span>
                            <span>Lisans ID</span><span>{sistemDurumu.lisans.license_id || "-"}</span>
                            <span>Lisans Konumu</span><span>{sistemDurumu.lisans.license_path || "-"}</span>
                          </div>
                        ) : (
                          <div className="license-detail-grid">
                            <span>Durum</span><span>Yükleniyor...</span>
                          </div>
                        )}
                        <div className="button-row">
                          <button className="button button-secondary" onClick={() => void handleCopyLicenseCode()} type="button">
                            Kopyala
                          </button>
                          <button className="button button-secondary" onClick={() => void handleInstallLicense()} disabled={lisansYukleniyor} type="button">
                            {lisansYukleniyor ? "Yükleniyor..." : "Lisans Ekle"}
                          </button>
                          <button className="button button-secondary" onClick={() => void openExternalUrl(SUPPORT_BASE_URL)} type="button">
                            Satın Alım
                          </button>
                        </div>
                        <div className="button-row">
                          <button className="button button-secondary" onClick={() => void openExternalUrl(SUPPORT_BASE_URL)} type="button">
                            S.S.S
                          </button>
                          <button className="button button-secondary" onClick={() => void openExternalUrl(SUPPORT_BASE_URL)} type="button">
                            Teknik Destek
                          </button>
                        </div>
                        {lisansKopyaMesaji ? <div className="license-copy-feedback">{lisansKopyaMesaji}</div> : null}
                      </>
                    ) : null}
                  </div>
                ) : null}
              </div>
            </div>
            <div className="brand-subline-row">
              <p className="brand-subline">SkynonLabs® ürünüdür.</p>
            </div>
          </div>
        </div>

        <div className="transferio-header-right">
          <div className="transferio-actions-row">
            <button className="button button-secondary" onClick={() => setSayfa("dashboard")} type="button">Mükellef Kontrol</button>
            <button className="button button-secondary" onClick={() => setSayfa("results")} type="button">Toplu Kontrol</button>
            <button className="button button-secondary" onClick={() => void handleChooseFolder()} type="button">Müşteri Klasörü Seç</button>
            <button className="button button-secondary" onClick={() => void handleOpenXmlFile()} type="button">e-Defter Görüntüle</button>
            <div className="header-menu-wrap">
              <button className="button button-secondary" onClick={() => { setLogMenuAcik((value) => !value); setLisansAcik(false); }} type="button">
                Loglar
              </button>
              {logMenuAcik ? (
                <div className="header-menu-panel">
                  <button className="header-menu-item" onClick={() => sistemDurumu?.yollar.log && void openPath(sistemDurumu.yollar.log)} type="button">Log Klasörü</button>
                  <button className="header-menu-item" onClick={() => sistemDurumu?.yollar.appLog && void openPath(sistemDurumu.yollar.appLog)} type="button">Uygulama Logu</button>
                  <button className="header-menu-item" onClick={() => sistemDurumu?.yollar.debugLog && void openPath(sistemDurumu.yollar.debugLog)} type="button">Hata Ayıklama Logu</button>
                  <button className="header-menu-item" onClick={() => sistemDurumu?.yollar.errorLog && void openPath(sistemDurumu.yollar.errorLog)} type="button">Hata Logu</button>
                  <button className="header-menu-item" onClick={() => sistemDurumu?.yollar.rapor && void openPath(sistemDurumu.yollar.rapor)} type="button">Rapor Klasörü</button>
                </div>
              ) : null}
            </div>
            <div className="header-menu-wrap">
              <button className="button button-secondary" onClick={() => void openExternalUrl("https://buymeacoffee.com/skynonlabs")} type="button">
                ☕ Bana Kahve Ismarla
              </button>
              {lisansAcik ? (
                <div className="license-popover">
                  <button className="license-close-button" onClick={() => { setLisansAcik(false); setLisansSonucu(null); }} type="button">
                    X
                  </button>
                  {lisansSonucu ? (
                    <div className={`license-result-banner ${lisansSonucu.durum === "success" ? "license-result-success" : "license-result-error"}`}>
                      <div className="license-success-icon">{lisansSonucu.durum === "success" ? "✓" : "!"}</div>
                      <strong>{lisansSonucu.baslik}</strong>
                      <span>{lisansSonucu.mesaj}</span>
                      <button className="button button-secondary license-result-action" onClick={handleLicenseResultAction} type="button">
                        {lisansSonucu.eylemEtiketi}
                      </button>
                    </div>
                  ) : null}
                  {!lisansSonucu ? (
                    <>
                      <strong>Cihaz Kodu</strong>
                      <div className="license-code-box">{sistemDurumu?.lisans.device_code || "-"}</div>
                      {sistemDurumu ? (
                        <div className="license-detail-grid">
                          <span>Lisans Sahibi</span><span>{sistemDurumu.lisans.licensee || "-"}</span>
                          <span>Lisans Modu</span><span>{normalizeModeLabel(sistemDurumu.lisans.valid ? "Pro Modu" : sistemDurumu.lisans.label)}</span>
                          <span>Lisans Tarihi</span><span>{sistemDurumu.lisans.issued_at || "-"}</span>
                          <span>Lisans ID</span><span>{sistemDurumu.lisans.license_id || "-"}</span>
                          <span>Lisans Konumu</span><span>{sistemDurumu.lisans.license_path || "-"}</span>
                        </div>
                      ) : (
                        <div className="license-detail-grid">
                          <span>Durum</span><span>Yükleniyor...</span>
                        </div>
                      )}
                      <div className="button-row">
                        <button
                          className="button button-secondary"
                          onClick={() => void handleCopyLicenseCode()}
                          type="button"
                        >
                          Kopyala
                        </button>
                        <button className="button button-secondary" onClick={() => void handleInstallLicense()} disabled={lisansYukleniyor} type="button">
                          {lisansYukleniyor ? "Yükleniyor..." : "Lisans Ekle"}
                        </button>
                        <button className="button button-secondary" onClick={() => void openExternalUrl(SUPPORT_BASE_URL)} type="button">
                          Satın Alım
                        </button>
                      </div>
                      <div className="button-row">
                        <button className="button button-secondary" onClick={() => void openExternalUrl(SUPPORT_BASE_URL)} type="button">
                          S.S.S
                        </button>
                        <button className="button button-secondary" onClick={() => void openExternalUrl(SUPPORT_BASE_URL)} type="button">
                          Teknik Destek
                        </button>
                      </div>
                      {lisansKopyaMesaji ? <div className="license-copy-feedback">{lisansKopyaMesaji}</div> : null}
                    </>
                  ) : null}
                </div>
              ) : null}
            </div>
            <div className="header-progress-controls header-progress-controls-compact">
              <button className="button button-secondary icon-circle-button" onClick={() => void handleStartScan()} disabled={taraniyor || !aktifKokKlasor} title="Tara" type="button">
                <PlayIcon />
              </button>
              <button className="button button-secondary icon-circle-button" onClick={() => void handleCancelJob()} disabled={!taraniyor} title="Durdur / İptal" type="button">
                ■
              </button>
              <button className="button button-secondary icon-circle-button" onClick={handleResetView} title="Sıfırla" type="button">
                ↻
              </button>
            </div>
            <div className="header-menu-wrap">
              <div className="scan-action-row">
                {sonTaramaMetni ? (
                  <button
                    className="button button-secondary scan-info-button"
                    onClick={() => setDurumMesaji(`Son tarama: ${sonTaramaMetni}`)}
                    title={`Son tarama: ${sonTaramaMetni}`}
                    type="button"
                  >
                    <span className="scan-info-button-label">Son tarama bilgileri</span>
                    <span className="scan-info-button-value">{sonTaramaMetni}</span>
                  </button>
                ) : null}
                <div className={`split-primary ${aktifKokKlasor && !taraniyor && !hasScanResults ? "button-primary-attention" : ""}`}>
                <button
                  className="button button-primary split-primary-main"
                  onClick={() => void handleStartScan()}
                  disabled={taraniyor || !aktifKokKlasor}
                  type="button"
                >
                  {islemDurumu?.aktif && islemDurumu?.islemTuru === "scan" ? "Taranıyor..." : "e-Defter Tara"}
                </button>
                <button
                  className="button button-primary split-primary-toggle"
                  onClick={() => setScanMenuAcik((value) => !value)}
                  disabled={taraniyor || !aktifKokKlasor}
                  type="button"
                >
                  ▾
                </button>
                </div>
              </div>
              {scanMenuAcik ? (
                <div className="header-menu-panel scan-menu-panel">
                  <button className="header-menu-item" onClick={() => void handleStartScan()} type="button">
                    Aktif Yılı Tara ({scanMenuYears[0]?.year || "Yıl"})
                  </button>
                  {scanMenuYears.length > 0 ? <div className="header-menu-section-title">Yıl Seçerek Tara</div> : null}
                  {scanMenuYears.map((item) => (
                    <button key={item.year} className="header-menu-item" onClick={() => void handleStartSelectedYears([item.year])} type="button">
                      {item.year} Tara {item.status === "ready" ? "(Hazır)" : item.status === "active" ? "(Taranıyor)" : taraniyor ? "(Bekliyor)" : "(Taranmadı)"}
                    </button>
                  ))}
                  <button className="header-menu-item header-menu-item-strong" onClick={() => void handleStartSelectedYears(scanMenuYears.map((item) => item.year))} type="button">
                    Tüm Dönemleri Tara
                  </button>
                </div>
              ) : null}
            </div>
          </div>

          <div className="header-progress-block header-progress-inline">
            <div className="header-progress-track">
              <div className="header-progress-fill" style={{ width: `${progressYuzde}%` }}>
                <span>{progressMesaj}</span>
              </div>
              <div className="header-progress-meta-overlay">{progressStats}</div>
            </div>
            {dashboardYearStatuses.length > 0 ? (
              <div className="header-year-track-shell">
                <span className="header-year-arrow header-year-arrow-left" aria-hidden="true"><ArrowLeftIcon /></span>
                <div className="header-year-track">
                {dashboardYearStatuses.map((item) => (
                  <button
                    key={item.year}
                    className={`header-year-segment header-year-segment-${item.status} ${item.status === "ready" ? "header-year-segment-clickable" : ""} ${aktifYil === String(item.year) ? "header-year-segment-selected" : ""}`}
                    disabled={item.status !== "ready"}
                    onClick={() => {
                      if (item.status === "ready") {
                        setSeciliYil(String(item.year));
                      }
                    }}
                    type="button"
                  >
                    <div
                      className={`header-year-segment-fill header-year-segment-fill-${item.status}`}
                      style={{ width: `${item.progress}%` }}
                    />
                    <span className="header-year-segment-label">
                      <span className="header-year-segment-title">
                        {item.year} {item.status === "ready" ? "" : item.status === "active" ? "Taranıyor" : taraniyor ? "Bekliyor" : "Taranmadı"}
                      </span>
                      <span className="header-year-segment-metric">
                        {item.status === "ready" ? "✓" : item.metric}
                      </span>
                    </span>
                  </button>
                ))}
                </div>
                <span className="header-year-arrow header-year-arrow-right" aria-hidden="true"><ArrowRightIcon /></span>
              </div>
            ) : null}
          </div>
        </div>
      </header>

      <main className="compact-content">
        <Suspense fallback={<LazyPanel />}>
          {sayfa === "dashboard" && (
            <DashboardView
              dashboard={dashboardData.dashboard}
              visibleCards={visibleCards}
              filteredCount={filteredCards.length}
              gonderilmisCount={dashboardSummary.gonderilmisFirma}
              uyariCount={dashboardSummary.uyariFirma}
              donemKarsilastirmaEtiketi={donemKarsilastirmaEtiketi}
              warningText={klasorUyarisi}
              searchText={aramaMetni}
              selectedYear={aktifYil}
              yearOptions={dashboardYears}
              yearStatuses={dashboardYearStatuses}
              scanning={taraniyor}
              selectedTaxpayerId={seciliMukellefId}
              onSearchTextChange={setAramaMetni}
              onYearChange={setSeciliYil}
              onPreviousCards={() => setKartBaslangici((value) => Math.max(value - 3, 0))}
              onNextCards={() => setKartBaslangici((value) => Math.min(value + 3, Math.max(filteredCards.length - 3, 0)))}
              onSelectTaxpayer={setSeciliMukellefId}
              onOpenTaxpayerProfile={handleOpenTaxpayerProfile}
              onOpenPeriod={(periodId) => void handleOpenPeriod(periodId)}
              onOpenFolder={(folderPath) => void openPath(folderPath)}
              onChooseFolder={() => void handleChooseFolder()}
              onOpenWarnings={() => setUyariPopupAcik(true)}
            />
          )}

          {sayfa === "results" && (
            <ResultsView
              rows={data.donemler}
              selectedYear={aktifYil}
              yearOptions={dashboardYears}
              yearStatuses={dashboardYearStatuses}
              scanning={taraniyor}
              selectedId={seciliId}
              onSelect={setSeciliId}
              onOpenDetail={(periodId) => void handleOpenPeriod(periodId)}
              onOpenTaxpayerProfile={handleOpenTaxpayerProfileByIdentity}
              onOpenWarnings={() => setUyariPopupAcik(true)}
              donemKarsilastirmaEtiketi={donemKarsilastirmaEtiketi}
              onYearChange={setSeciliYil}
              onExportExcel={() => void handleExport("excel")}
              exporting={exporting}
              statusMessage={durumMesaji}
            />
          )}

          {sayfa === "detail" && (
            <PeriodDetailView
              period={seciliDonem}
              onOpenXmlViewer={(periodId) => void handleOpenPeriod(periodId)}
              onOpenControlXml={(period, controlId) => void handleOpenControlXml(period, controlId)}
              onSetPeriodOverride={(periodId, approved, note) => void handleSetPeriodOverride(periodId, approved, note)}
            />
          )}

          {sayfa === "profile" && (
            <TaxpayerProfileView
              card={selectedTaxpayerCard}
              periods={selectedTaxpayerPeriods}
              yearOptions={dashboardYears}
              yearStatuses={dashboardYearStatuses}
              selectedYear={aktifYil}
              scanning={taraniyor}
              onYearChange={setSeciliYil}
              onOpenPeriod={(periodId) => void handleOpenPeriod(periodId)}
              onBack={() => setSayfa("dashboard")}
            />
          )}
        </Suspense>
      </main>

      <footer className="app-footer">SkynonLabs® ürünüdür. • {sistemDurumu?.uygulama.surum || "v0.1.0"}</footer>

      <XmlViewerModal
        title={xmlBaslik}
        subtitle={xmlAltBaslik}
        visible={xmlPopupAcik}
        sources={xmlKaynaklar}
        selectedKey={xmlKaynakKey}
        xmlContent={xmlIcerik}
        xmlFileName={xmlDosyaAdi}
        truncated={xmlKisaltildi}
        loading={xmlYukleniyor}
        onClose={closeXmlModal}
        onSelectSource={(key) => {
          const source = xmlKaynaklar.find((item) => item.key === key);
          if (source) {
            void openXmlKaynak(source);
          }
        }}
      />

      {uyariPopupAcik ? (
        <div className="modal-backdrop" onClick={() => setUyariPopupAcik(false)}>
          <div className="modal-card warning-modal-card" onClick={(event) => event.stopPropagation()}>
            <div className="card-header-row">
              <div>
                <h2 className="section-title">Genel Uyarı ve Hatalar</h2>
                <p className="section-subtitle">Sorunlu aylara dokunup ilgili dönemi açın.</p>
              </div>
              <button className="button button-secondary" onClick={() => setUyariPopupAcik(false)} type="button">Kapat</button>
            </div>

            <div className="warning-list">
              {donemKarsilastirmalari.length > 0 ? (
                <>
                  {donemKarsilastirmalari.map((item) => (
                    <div key={item.id} className="warning-row">
                      <strong>{item.oncekiEtiket} - {item.simdikiEtiket}</strong>
                      <span>{item.oncekiSayi} mükellef {"→"} {item.simdikiSayi} mükellef</span>
                      <small>
                        {item.eksikFirmalar.length > 0
                          ? `Eksik görünen mükellefler: ${item.eksikFirmalar.join(", ")}`
                          : "Açıklanamayan eksik mükellef görünmüyor."}
                      </small>
                      {item.ozelDurumluFirmalar.length > 0 ? (
                        <small>Özel durumlu farklar: {item.ozelDurumluFirmalar.join(", ")}</small>
                      ) : null}
                    </div>
                  ))}
                </>
              ) : null}
              {gercekUyarilar.length > 0 ? (
                gercekUyarilar.map((row) => (
                  <button
                    key={row.id}
                    className="warning-row"
                    onClick={() => {
                      setUyariPopupAcik(false);
                      handleOpenTaxpayerProfileByIdentity(row.firma, row.vkn, row.yil);
                    }}
                    type="button"
                  >
                    <strong>{row.firma} ({row.vkn})</strong>
                    <span>{row.yil}/{row.ay}</span>
                    <small>{row.ozet.join(" | ")}</small>
                  </button>
                ))
              ) : donemKarsilastirmalari.length === 0 ? (
                <div className="compact-empty-state">Gösterilecek genel uyarı veya hata kaydı bulunmuyor.</div>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}

      {kilavuzAcik ? (
        <div className="modal-backdrop" onClick={() => setKilavuzAcik(false)}>
          <div className="modal-card kilavuz-modal-card" onClick={(event) => event.stopPropagation()}>
            <div className="card-header-row">
              <div>
                <h2 className="section-title">Kılavuz</h2>
                <p className="section-subtitle">Programın ne işe yaradığını ve nasıl kullanılacağını adım adım anlatır.</p>
              </div>
              <button className="button button-secondary" onClick={() => setKilavuzAcik(false)} type="button">Kapat</button>
            </div>

            <div className="kilavuz-content">
              <section className="kilavuz-section">
                <strong>1. Program ne işe yarar?</strong>
                <p>Bu program, e-Defter klasörlerinizi tarar ve her mükellefin hangi dönemlerinin eksiksiz, eksik, uyarılı veya hatalı olduğunu tek ekranda gösterir. XML görüntüleme, toplu kontrol, profil görünümü ve lisans yönetimi aynı program içinde çalışır.</p>
              </section>
              <section className="kilavuz-section">
                <strong>2. İlk kullanım</strong>
                <p>Önce <strong>Müşteri Klasörü Seç</strong> düğmesine basın. e-Defter dosyalarının bulunduğu ana klasörü seçin. Sonra <strong>e-Defter Tara</strong> düğmesi ile ilk kontrolü başlatın.</p>
              </section>
              <section className="kilavuz-section">
                <strong>3. Tarama seçenekleri</strong>
                <p>e-Defter Tara menüsünde üç akış vardır: aktif yılı tara, seçtiğiniz yılı tara ve tüm dönemleri tara. Önce aktif yıl hızlı gelir. Diğer yıllar isterseniz ayrıca taranır. Üstteki yıl barı hangi yılın hazır, sırada veya taranıyor olduğunu gösterir.</p>
              </section>
              <section className="kilavuz-section">
                <strong>4. Mükellef Kontrol</strong>
                <p>Bu alan tek tek mükellef kartlarını gösterir. Kartın üstünden klasörü açabilir, yılı değiştirebilir ve aylara basarak dönem detayına geçebilirsiniz. Profil ekranında mükellefin seçili yıldaki tüm dönemleri bir arada görünür.</p>
              </section>
              <section className="kilavuz-section">
                <strong>5. Toplu Kontrol</strong>
                <p>Bu alan tüm firmaları liste halinde gösterir. Hangi ayın yeşil, sarı veya kırmızı olduğunu hızlıca görürsünüz. Liste, önce sorunlu firmaları gösterecek şekilde sıralanır. Başlıktaki özet alanından toplam firma, gönderilmiş firma ve uyarılı firma sayısını açabilirsiniz.</p>
              </section>
              <section className="kilavuz-section">
                <strong>6. Renkler ne anlama gelir?</strong>
                <p>Yeşil: dönem doğru görünüyor. Sarı: kontrol edilmesi gereken durum var. Kırmızı: eksik veya hatalı dosya var. Gri: o ay için dosya görünmüyor. Tasfiye, kuruluş dönemi veya geçiş gibi özel durumlar sarı uyarı olarak gösterilir.</p>
              </section>
              <section className="kilavuz-section">
                <strong>7. XML görüntüleme</strong>
                <p><strong>e-Defter Görüntüle</strong> ile istediğiniz XML dosyasını seçebilirsiniz. Dönem içindeki uygun alanlara bastığınızda XML programın içinde açılır. Windows üzerinden sağ tık ile <strong>e-Defter Denetim Merkezi ile Aç</strong> seçeneğini de kullanabilirsiniz.</p>
              </section>
              <section className="kilavuz-section">
                <strong>8. Demo ve Pro Modu</strong>
                <p>Demo Modunda sadece 4 firma tam açılır. Diğer firmalar kilitli önizleme olarak görünür. Pro Modu etkinleştirildiğinde tüm firma ve dönemler açılır.</p>
              </section>
              <section className="kilavuz-section">
                <strong>9. Lisans</strong>
                <p><strong>Lisans</strong> alanında cihaz kodunu görebilir, kopyalayabilir ve lisans dosyanızı ekleyebilirsiniz. Lisans doğruysa program Pro Modu olarak çalışır. Satın alım ve destek bağlantıları aynı alanda yer alır.</p>
              </section>
              <section className="kilavuz-section">
                <strong>10. Loglar</strong>
                <p>Bir sorun yaşarsanız <strong>Loglar</strong> alanından uygulama logu, hata ayıklama logu ve hata logunu açabilirsiniz. Bu kayıtlar sorunu bulmayı kolaylaştırır.</p>
              </section>
              <section className="kilavuz-section">
                <strong>11. S.S.S, destek ve satın alım</strong>
                <p>Üst alandaki <strong>S.S.S</strong> bağlantısı sık sorulan sorulara gider. <strong>Destek</strong> bağlantısı teknik destek alanını açar. Lisans penceresindeki <strong>Satın Alım</strong> bağlantısı Pro Modu satın alma sayfasına yönlendirir.</p>
              </section>
              <div className="button-row">
                <button className="button button-secondary" onClick={() => void openExternalUrl(SUPPORT_BASE_URL)} type="button">S.S.S</button>
                <button className="button button-secondary" onClick={() => void openExternalUrl(SUPPORT_BASE_URL)} type="button">Teknik Destek</button>
                <button className="button button-secondary" onClick={() => void openExternalUrl(SUPPORT_BASE_URL)} type="button">Satın Alım</button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function LazyPanel() {
  return <div className="card compact-empty-state">Görünüm yükleniyor...</div>;
}

function matchesCard(card: MukellefKarti, normalized: string) {
  const haystack = normalizeText(
    [card.gosterimAdi, card.resmiUnvan, card.vknTckn, card.maliMusavir, card.aramaMetni].join(" "),
  );
  return haystack.includes(normalized);
}

function buildQuarterComparisons(rows: DonemKaydi[], selectedYear: string, searchText: string) {
  const normalizedSearch = normalizeText(searchText);
  const targetYear = !selectedYear || selectedYear === "Tüm Yıllar" ? null : Number(selectedYear);
  const filteredRows = rows.filter((row) => {
    if (targetYear !== null && row.yil !== targetYear) {
      return false;
    }
    if (!normalizedSearch) {
      return true;
    }
    const haystack = normalizeText([row.firma, row.resmiUnvan, row.vkn, row.maliMusavir, row.aramaMetni].join(" "));
    return haystack.includes(normalizedSearch);
  });
  if (filteredRows.length === 0) {
    return [] as DonemKarsilastirmaOgesi[];
  }

  const quarterMap = new Map<number, Map<string, { firma: string; ozel: boolean }>>();
  for (const row of filteredRows) {
    const month = Number(row.ay);
    if (!Number.isFinite(month) || month < 1 || month > 12) {
      continue;
    }
    const quarterIndex = Math.floor((month - 1) / 3);
    const firmKey = `${row.firma}|${row.vkn}`;
    const quarterFirms = quarterMap.get(quarterIndex) ?? new Map<string, { firma: string; ozel: boolean }>();
    const current = quarterFirms.get(firmKey);
    quarterFirms.set(firmKey, {
      firma: row.firma,
      ozel: Boolean(row.ozelDurumTipi || row.gecisRolu),
    });
    if (!quarterMap.has(quarterIndex)) {
      quarterMap.set(quarterIndex, quarterFirms);
    } else if (current && current.ozel) {
      quarterFirms.set(firmKey, current);
    }
  }

  const comparisons: DonemKarsilastirmaOgesi[] = [];
  for (let quarterIndex = 0; quarterIndex < 3; quarterIndex += 1) {
    const previous = quarterMap.get(quarterIndex);
    const current = quarterMap.get(quarterIndex + 1);
    if (!previous || !current) {
      continue;
    }
    const missingEntries = Array.from(previous.entries()).filter(([firmKey]) => !current.has(firmKey));
    const eksikFirmalar = missingEntries.filter(([, value]) => !value.ozel).map(([, value]) => value.firma).sort((a, b) => a.localeCompare(b, "tr"));
    const ozelDurumluFirmalar = missingEntries.filter(([, value]) => value.ozel).map(([, value]) => value.firma).sort((a, b) => a.localeCompare(b, "tr"));
    comparisons.push({
      id: `Q${quarterIndex + 1}-Q${quarterIndex + 2}`,
      oncekiEtiket: quarterLabel(quarterIndex),
      simdikiEtiket: quarterLabel(quarterIndex + 1),
      oncekiSayi: previous.size,
      simdikiSayi: current.size,
      eksikFirmalar,
      ozelDurumluFirmalar,
    });
  }
  return comparisons;
}

function quarterLabel(quarterIndex: number) {
  const startMonth = quarterIndex * 3 + 1;
  const endMonth = startMonth + 2;
  return `${String(startMonth).padStart(2, "0")}-${String(endMonth).padStart(2, "0")}`;
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

function buildXmlSources(period: DonemKaydi): XmlKaynak[] {
  const buildSource = (key: string, label: string, belgeTipleri: string[]) => {
    const files = period.dosyalar.filter((file) => belgeTipleri.includes(file.belgeTipi) && file.kaynak === "XML");
    if (files.length === 0) {
      return null;
    }
    return { key, label, path: files[0].yol, count: files.length };
  };

  return [
    buildSource("journal", "Y", ["JOURNAL_BOOK"]),
    buildSource("ledger", "K", ["LEDGER_BOOK"]),
    buildSource("inventory", "E", ["INVENTORY_BOOK"]),
    buildSource("inventory-berat", "EB", ["INVENTORY_BERAT"]),
    buildSource("gib", "GİB Onaylı Suret", ["GIB_APPROVED_JOURNAL_BERAT", "GIB_APPROVED_LEDGER_BERAT", "GIB_APPROVED_INVENTORY_BERAT"]),
  ].filter((item): item is XmlKaynak => item !== null);
}
function normalizeModeLabel(value?: string) {
  if (!value) {
    return "Demo Modu";
  }
  const normalized = value.toLocaleLowerCase("tr-TR");
  if (normalized.includes("tam") || normalized.includes("pro") || normalized.includes("surum")) {
    return "Pro Modu";
  }
  return value;
}

function buildProgressMessage(status: IslemDurumu | null, data: TaramaVerisi | null) {
  const rawMessage = status?.mesaj?.trim() ?? "";
  if (rawMessage) {
    const normalized = rawMessage.toLocaleLowerCase("tr-TR");
    if (!normalized.includes("has no attribute") && !normalized.includes("object has no attribute")) {
      return rawMessage;
    }
  }
  return ((data?.dashboard.toplamDonem ?? 0) > 0) ? "Sonuç ekranı hazır" : "Hazır";
}

function buildProgressStats(status: IslemDurumu | null) {
  if (!status) {
    return "";
  }
  const parts = [
    status.tarananKlasor > 0 ? `${status.tarananKlasor} dosya islendi` : "",
    status.mukellefSayisi > 0 ? `${status.mukellefSayisi} mukellef` : "",
    status.donemSayisi > 0 ? `${status.donemSayisi} donem` : "",
  ].filter(Boolean);
  return parts.join(" | ");
}

function buildYearStatuses(allYears: number[], readyYears: number[], status: IslemDurumu | null): YilDurumuOgesi[] {
  const years = new Set<number>(allYears);
  for (const year of status?.tumYillar ?? []) {
    years.add(year);
  }
  for (const year of status?.tamamlananYillar ?? []) {
    years.add(year);
  }
  const readySet = new Set<number>([...readyYears, ...(status?.tamamlananYillar ?? [])]);
  const activeYear = status?.aktifYil ?? null;
  const queuedSet = new Set<number>(status?.bekleyenYillar ?? []);
  const yearProgress = status?.yilIlerleme ?? {};
  const sortedYears = Array.from(years).sort((a, b) => b - a);
  const activeProgress = estimateActiveYearProgress(status, sortedYears, readySet, activeYear);
  return sortedYears
    .map((year) => {
      const progressInfo = yearProgress[String(year)];
      if (activeYear === year && !readySet.has(year)) {
        return {
          year,
          status: "active" as const,
          progress: clampProgress(progressInfo?.yuzde ?? activeProgress),
          metric: formatYearMetric(progressInfo?.yuzde ?? activeProgress),
        };
      }
      if (readySet.has(year)) {
        return { year, status: "ready" as const, progress: 100, metric: "" };
      }
      if (queuedSet.has(year) || activeYear === year) {
        return { year, status: "queued" as const, progress: 0, metric: "" };
      }
      return { year, status: "queued" as const, progress: 0, metric: "" };
    });
}

function clampProgress(value: number) {
  return Math.max(0, Math.min(100, value));
}

function formatYearMetric(value: number) {
  const safeValue = clampProgress(value);
  return `%${safeValue.toFixed(1)}`;
}

function formatLastScanText(value: string | null | undefined) {
  if (!value) {
    return "";
  }
  const normalized = String(value).trim();
  if (!normalized || normalized.toLocaleLowerCase("tr-TR").includes("hen")) {
    return "";
  }
  const parsed = normalized.includes("T") ? normalized.replace("T", " ") : normalized;
  const match = parsed.match(/^(\d{4})-(\d{2})-(\d{2})[ ](\d{2}):(\d{2})(?::\d{2})?$/);
  if (match) {
    return `${match[3]}.${match[2]}.${match[1]} ${match[4]}:${match[5]}`;
  }
  return parsed;
}

function estimateActiveYearProgress(
  status: IslemDurumu | null,
  years: number[],
  readySet: Set<number>,
  activeYear: number | null,
) {
  if (!status?.aktif || !activeYear || years.length === 0) {
    return 0;
  }
  const readyCount = years.filter((year) => readySet.has(year)).length;
  const remainingYears = Math.max(years.length - readyCount, 1);
  const overall = Math.max(0, Math.min(100, status.yuzde || 0));
  const completedShare = (readyCount / years.length) * 100;
  const availableShare = Math.max(100 - completedShare, 1);
  const normalized = Math.max(0, Math.min(100, ((overall - completedShare) / availableShare) * 100));
  return Math.max(12, Math.min(96, normalized / remainingYears + 18));
}

function sortTaxpayerCards(a: MukellefKarti, b: MukellefKarti) {
  const rankDiff = taxpayerRank(a) - taxpayerRank(b);
  if (rankDiff !== 0) {
    return rankDiff;
  }
  return a.gosterimAdi.localeCompare(b.gosterimAdi, "tr");
}

function CheckIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" className="toolbar-svg-icon">
      <path d="m4.5 10.5 3.5 3.5 7-8" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function PlayIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" className="toolbar-svg-icon">
      <path d="M6 4.8v10.4L14.8 10 6 4.8Z" fill="currentColor" />
    </svg>
  );
}

function ArrowLeftIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" className="toolbar-svg-icon">
      <path d="m11.8 4.8-5 5.2 5 5.2" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ArrowRightIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" className="toolbar-svg-icon">
      <path d="m8.2 4.8 5 5.2-5 5.2" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function taxpayerRank(card: MukellefKarti) {
  if (card.durumGrubu === "red") {
    return 0;
  }
  if (card.durumGrubu === "yellow" || card.ozelDurumTipi || card.gecisFirma || card.genelRisk !== "OK") {
    return 1;
  }
  return 2;
}

export default App;

