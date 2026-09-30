export type RiskLevel = "OK" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export type DurumTipi =
  | "Tam"
  | "Eksik"
  | "Bozuk"
  | "Tekrar"
  | "Eşleşmedi"
  | "İncelenmeli";

export type ProfilTipi = "Luca" | "Zirve" | "Genel" | "Klasör Taraması";

export type DonemDosyaDurumu =
  | "Bulundu"
  | "Eksik"
  | "Tekrar"
  | "Bozuk"
  | "Eşleşmedi";

export interface ArsivAdayi {
  klasorYolu: string;
  guvenSkoru: number;
  mukellefSayisi: number;
  yilSayisi: number;
  aySayisi: number;
  eslesenDosyaSayisi: number;
  ornekler: string[];
  ozet: string;
}

export interface HizliKesifSonucu {
  baslangicKlasoru: string;
  adaylar: ArsivAdayi[];
  bulundu: boolean;
}

export interface IslemDurumu {
  aktif: boolean;
  tamamlandi: boolean;
  basarili: boolean;
  iptalIstenmis: boolean;
  iptalEdildi: boolean;
  islemTuru: "idle" | "discover" | "scan" | "history";
  asama: string;
  mesaj: string;
  detay: string;
  yuzde: number;
  tarananKlasor: number;
  adaySayisi: number;
  mukellefSayisi: number;
  donemSayisi: number;
  gecenSureSaniye: number;
  sonIslem: string;
  loglar: string[];
  hata: string;
  tumYillar?: number[];
  aktifYil?: number | null;
  bekleyenYillar?: number[];
  tamamlananYillar?: number[];
  yilIlerleme?: Record<string, {
    toplamDosya: number;
    islenenDosya: number;
    yuzde: number;
    durum: "ready" | "active" | "queued";
  }>;
  kesifSonucu?: HizliKesifSonucu;
  taramaVerisi?: TaramaVerisi;
}

export interface DonemDosyasi {
  id: string;
  etiket: string;
  dosyaAdi: string;
  yol: string;
  boyut: string;
  hash: string;
  kaynak: string;
  belgeTipi: string;
  olusturmaTarihi: string;
  imzaTarihi: string;
  durum: DonemDosyaDurumu;
}

export interface YardimciDosya {
  id: string;
  etiket: string;
  dosyaAdi: string;
  yol: string;
  kaynak: string;
  boyut: string;
}

export interface SorunKaydi {
  id: string;
  risk: RiskLevel;
  baslik: string;
  aciklama: string;
  ilgiliDosya: string;
  onerilenIslem: string;
}

export interface LogKaydi {
  saat: string;
  seviye: "INFO" | "WARNING" | "ERROR";
  mesaj: string;
}

export interface KontrolKalemi {
  id: string;
  etiket: string;
  aciklama: string;
  durum: DurumTipi;
  xmlAdet: number;
  zipAdet: number;
  beklenenAdet: number;
  dosyaYollari: string[];
}

export interface DonemKaydi {
  id: string;
  firmaAnahtari?: string;
  firma: string;
  resmiUnvan: string;
  vkn: string;
  yil: number;
  ay: string;
  profil: ProfilTipi;
  aramaMetni: string;
  maliMusavir: string;
  gonderimTarihi: string;
  imzaTarihi: string;
  gibOnayTarihi: string;
  donemBaslangic: string;
  donemBitis: string;
  klasorYolu: string;
  kontroller: KontrolKalemi[];
  yevmiye: DurumTipi;
  kebir: DurumTipi;
  yevmiyeBerat: DurumTipi;
  kebirBerat: DurumTipi;
  gibOnayliBerat: DurumTipi;
  defterRaporu: DurumTipi;
  envanterVar?: boolean;
  gibEnvanterVar?: boolean;
  durum: DurumTipi;
  risk: RiskLevel;
  ozet: string[];
  aksiyonlar: string[];
  ozelDurumTipi?: string;
  ozelDurum?: string;
  dosyalar: DonemDosyasi[];
  topluPaketler: YardimciDosya[];
  yardimciDosyalar: YardimciDosya[];
  sorunlar: SorunKaydi[];
  loglar: LogKaydi[];
  gecisTipi?: string;
  gecisEtiketi?: string;
  gecisRolu?: string;
  gecisTarihi?: string;
  arsivKokleri?: string[];
  araDonemAtlamasi?: boolean;
  kullaniciIstisnasi?: boolean;
  kullaniciIstisnaNotu?: string;
  kullaniciIstisnaTarihi?: string;
  demoLocked?: boolean;
  demoMessage?: string;
}

export interface MukellefDonemOzet {
  ayNo: string;
  ayAd: string;
  durumRengi: "green" | "yellow" | "red" | "gray" | "amber";
  kisaDurum: string;
  ozet: string;
  risk: RiskLevel;
  donemId: string;
  envanterVar?: boolean;
  gibEnvanterVar?: boolean;
  gecisRolu?: string;
  gecisEtiketi?: string;
  ozelDurumTipi?: string;
  araDonemAtlamasi?: boolean;
  kullaniciIstisnasi?: boolean;
  demoLocked?: boolean;
  demoMessage?: string;
}

export interface MukellefKarti {
  id: string;
  firmaAnahtari?: string;
  gosterimAdi: string;
  resmiUnvan: string;
  vknTckn: string;
  yil: number;
  profil: ProfilTipi;
  aramaMetni: string;
  maliMusavir: string;
  genelRisk: RiskLevel;
  eksikDonemSayisi: number;
  kritikSorunSayisi: number;
  envanterVar?: boolean;
  gibEnvanterVar?: boolean;
  envanterDonemSayisi?: number;
  sonTarama: string | number;
  donemler: MukellefDonemOzet[];
  klasorYolu: string;
  ozelDurum?: string;
  ozelDurumTipi?: string;
  gecisFirma?: boolean;
  durumGrubu?: "red" | "yellow" | "green";
  onayliIstisnaSayisi?: number;
  demoLocked?: boolean;
  demoMessage?: string;
}

export interface IlerlemeDurumu {
  asama: string;
  yuzde: number;
  islenenDosya: number;
  toplamDosya: number;
  bulunanMukellef: number;
  hataSayisi: number;
}

export interface DashboardOzeti {
  profil: ProfilTipi;
  arsivKlasoru: string;
  sonTarama: string;
  hazirYillar?: number[];
  tumYillar?: number[];
  toplamFirma: number;
  gecisFirmaSayisi?: number;
  toplamDonem: number;
  eksikDonem: number;
  kritikHata: number;
  genelSkor: number;
  riskDagilimi: Record<RiskLevel, number>;
  sonOzet: Array<{
    id: string;
    firma: string;
    donem: string;
    sorun: string;
    risk: RiskLevel;
  }>;
  ilerleme: IlerlemeDurumu;
  mukellefKartlari: MukellefKarti[];
  islemGunlugu: LogKaydi[];
  demoKilitliFirma?: number;
  demoAcikFirma?: number;
}

export interface TaramaVerisi {
  dashboard: DashboardOzeti;
  donemler: DonemKaydi[];
  teknik_ozet?: unknown;
  sistemDurumu?: SistemDurumu;
  acilisXmlYolu?: string;
}

export interface XmlOnizleme {
  ok: boolean;
  message?: string;
  fileName?: string;
  path?: string;
  size?: number;
  content?: string;
  truncated?: boolean;
}

export interface LisansDurumu {
  mode: string;
  label: string;
  valid: boolean;
  licensee: string;
  license_id: string;
  issued_at: string;
  device_code: string;
  message: string;
  license_path: string;
  demo: {
    limit: number;
    used_count: number;
    remaining: number;
    archives: string[];
    firms?: Array<{
      key: string;
      label: string;
      registered_at?: string;
    }>;
    registered_keys?: string[];
    current_archive?: string;
    current_registered?: boolean;
    current_registered_count?: number;
    is_full: boolean;
    can_add_current: boolean;
  };
}

export interface SistemDurumu {
  uygulama: {
    ad: string;
    surum: string;
    mod: string;
  };
  lisans: LisansDurumu;
  yollar: {
    kok: string;
    log: string;
    rapor: string;
    appLog: string;
    debugLog: string;
    errorLog: string;
  };
  gunluk: {
    appLogVar: boolean;
    debugLogVar: boolean;
    errorLogVar: boolean;
    sonHataSatiri: string;
    sonDebugSatiri: string;
  };
}
