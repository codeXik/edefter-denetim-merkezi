# e-Defter Denetim Merkezi

Ücretsiz ve açık kaynaklı e-Defter ön denetim aracı. SkynonLabs® ürünüdür.

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-destek%20ol-FFDD00?logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/skynonlabs)

Bu proje, Luca ve Zirve gibi farklı üretici arşivlerinden gelen e-Defter klasörlerini okuyup
ön denetim yapan yerel bir masaüstü/CLI çekirdeğidir.

Temel kapsam:

- klasör ve alt klasör tarama
- XML ve ZIP dosyası tanıma
- Luca/Zirve/genel arşiv yapısı algılama
- belge türü sınıflandırma
- firma/yıl/ay bazlı gruplama
- eksik ve uyumsuz belge setlerini raporlama

Bu araç:

- dosya üretimini değiştirmez
- XML içeriklerini düzenlemez
- GİB'e gönderim yapmaz
- resmi onay vermez

## Kurulum

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
cd frontend
npm install
cd ..
```

## CLI Kullanımı

```powershell
edefter-denetim scan "Z:\Evrak Çantası\LucaEdefter" --profile auto
edefter-denetim scan "Z:\Evrak Çantası\eDefter" --profile auto --json-out reports\zirve-summary.json
```

## Masaüstü Uygulama

Geliştirme:

```powershell
cd frontend
npm run dev
```

Ayrı terminal:

```powershell
python -m edefter_denetim.desktop.app
```

Üretim derlemesi:

```powershell
cd frontend
npm run build
cd ..
python -m edefter_denetim.desktop.app
```

## Doğrulama Betikleri

Örnek gerçek arşiv kökleriyle smoke test:

```powershell
python scripts\demo_smoke_test.py
```

Örnek gerçek arşiv kökleriyle performans ölçümü:

```powershell
python scripts\perf_scan_benchmark.py
```

İstenirse farklı klasörler `EDEFTER_TEST_ROOTS` ile `;` ayrılmış olarak verilebilir.

## EXE Paketleme

Önce frontend derlenir:

```powershell
cd frontend
npm run build
cd ..
```

Sonra PyInstaller ile paket alınır:

```powershell
pyinstaller --clean EdefterDenetimMerkezi.spec
```

Çıktı klasörü:

```text
dist\e-Defter Denetim Merkezi\
```

Çalıştırılacak dosya:

```text
dist\e-Defter Denetim Merkezi\e-Defter Denetim Merkezi.exe
```

Notlar:

- Frontend asset yolları relatif üretildiği için exe altında beyaz ekran riski azaltıldı.
- Uygulama logları `logs` klasörüne yazılır.
- Rapor çıktıları `reports` klasörüne yazılır.
- `Z:\Evrak Çantası` gibi çok geniş ana köklerde tam tarama uzun sürebilir; hızlı keşif ve aday kök seçimi önerilir.

## Dizinler

- [docs/research-notes.md](C:\Users\Admin\Documents\Edefter%20Denetim%20Merkezi\docs\research-notes.md)
- [docs/roadmap.md](C:\Users\Admin\Documents\Edefter%20Denetim%20Merkezi\docs\roadmap.md)
- [src/edefter_denetim](C:\Users\Admin\Documents\Edefter%20Denetim%20Merkezi\src\edefter_denetim)
- [frontend](C:\Users\Admin\Documents\Edefter%20Denetim%20Merkezi\frontend)


## Destek

Proje işine yaradıysa bir kahve ısmarlayarak destek olabilirsin: https://buymeacoffee.com/skynonlabs

## Lisans

GNU GPL v3.0. Ayrıntılar için [LICENSE](LICENSE) dosyasına bakın.
