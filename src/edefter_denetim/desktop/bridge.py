from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import unicodedata
import hashlib
from collections import Counter, deque
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from xml.dom import minidom

import webview

from edefter_denetim.app_paths import get_logs_dir, get_reports_dir, get_scan_cache_dir as get_runtime_scan_cache_dir
from edefter_denetim.classifier import classify_document
from edefter_denetim.desktop.discovery import discover_archives
from edefter_denetim.license import can_scan_archive, evaluate_license, install_license_file, register_demo_firms
from edefter_denetim.log_utils import LOGGER_NAME, setup_logging
from edefter_denetim.models import DocumentType, FileRecord, PeriodBucket, ScanSummary, TaxpayerSummary, VendorProfile
from edefter_denetim.reporting import export_excel_report, export_json_report, export_pdf_report
from edefter_denetim.scanner import build_scan_summary, scan_archive, summary_to_dict


DISCOVERY_MESSAGES = [
    "Klasörler okunuyor...",
    "VKN/TCKN yapıları aranıyor...",
    "Yıl ve ay klasörleri eşleştiriliyor...",
    "Yevmiye ve berat izleri toplanıyor...",
    "Aday arşiv kökleri doğrulanıyor...",
]

SCAN_MESSAGES = [
    "Mükellef kartları hazırlanıyor...",
    "Dönem klasörleri bağlanıyor...",
    "XML ve ZIP dosyaları sınıflandırılıyor...",
    "Belge seti riskleri hesaplanıyor...",
    "Sonuç ekranı hazırlanıyor...",
]

DATE_RANGE_PATTERN = re.compile(r"^(?P<start>\d{2}\.\d{2}\.\d{4})-(?P<end>\d{2}\.\d{2}\.\d{4})$")
PERIOD_OVERRIDE_FILENAME = "edefter_period_overrides.json"
SCAN_CACHE_DIRNAME = "scan_cache"


class DesktopApi:
    def __init__(self, project_root: Path, launch_xml_path: Path | None = None) -> None:
        self.project_root = project_root
        self.launch_xml_path = launch_xml_path
        setup_logging(project_root)
        self.logger = logging.getLogger(LOGGER_NAME)
        self.last_summary: ScanSummary | None = None
        self.last_rows: list[dict[str, Any]] = []
        self.last_dashboard: dict[str, Any] = empty_dashboard()
        self._job_lock = threading.Lock()
        self._job_state = idle_job_state()
        self._worker: threading.Thread | None = None
        self._cancel_requested = False

    def get_initial_data(self) -> dict[str, object]:
        self.logger.info("İlk veri yükleme başladı.")
        self.logger.info("Kullanıcı klasör seçimi bekleniyor.")
        startup_xml_path = str(self.launch_xml_path) if self.launch_xml_path else ""
        self.launch_xml_path = None
        cached_result = load_latest_scan_cache_result(self.project_root)
        if cached_result:
            dashboard = cached_result.get("dashboard", {})
            if isinstance(dashboard, dict):
                root_path = str(dashboard.get("arsivKlasoru", "")).strip()
                if root_path:
                    try:
                        dashboard["tumYillar"] = collect_archive_years(repair_windows_path(root_path))
                    except Exception:
                        dashboard["tumYillar"] = list(dashboard.get("hazirYillar", []) or [])
            self._store_last_result(cached_result)
            cached_result["sistemDurumu"] = self.get_system_status()
            cached_result["acilisXmlYolu"] = startup_xml_path
            return cached_result
        return {
            "dashboard": empty_dashboard(),
            "donemler": [],
            "teknik_ozet": {},
            "sistemDurumu": self.get_system_status(),
            "acilisXmlYolu": startup_xml_path,
        }

    def get_job_status(self) -> dict[str, object]:
        with self._job_lock:
            state = dict(self._job_state)
            state["loglar"] = list(self._job_state["loglar"])
            return state

    def choose_folder(self) -> str | None:
        window = webview.windows[0]
        selection = window.create_file_dialog(webview.FOLDER_DIALOG)
        if not selection:
            self.logger.info("Klasör seçimi iptal edildi.")
            return None
        selected = str(selection[0])
        self.logger.info("Klasör seçildi: %s", selected)
        return selected

    def choose_license_file(self) -> str | None:
        window = webview.windows[0]
        selection = window.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=False,
            file_types=("Lisans Dosyası (*.json)",),
        )
        if not selection:
            return None
        return str(selection[0])

    def choose_xml_file(self) -> str | None:
        window = webview.windows[0]
        selection = window.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=False,
            file_types=("XML Dosyasi (*.xml)",),
        )
        if not selection:
            self.logger.info("XML dosyasi secimi iptal edildi.")
            return None
        selected = str(selection[0])
        self.logger.info("XML dosyasi secildi: %s", selected)
        return selected

    def install_license(self, source_path: str) -> dict[str, object]:
        license_data = install_license_file(self.project_root, Path(source_path))
        self.logger.info("Lisans dosyası yüklendi: %s", source_path)
        refreshed_result = self._rebuild_last_result() if self.last_summary else None
        return {
            "ok": True,
            "license": evaluate_license(self.project_root),
            "raw": license_data,
            "taramaVerisi": refreshed_result,
        }

    def set_period_override(self, period_id: str, approved: bool, note: str = "") -> dict[str, object]:
        if not self.last_summary:
            raise RuntimeError("Aktif tarama verisi bulunmuyor.")
        save_period_override(self.project_root, period_id, approved, note)
        self.logger.info("Donem istisna kaydi guncellendi. id=%s approved=%s", period_id, approved)
        return self._rebuild_last_result()

    def get_system_status(self) -> dict[str, object]:
        license_state = evaluate_license(self.project_root)
        log_dir = get_logs_dir()
        report_dir = get_reports_dir()
        return {
            "uygulama": {
                "ad": "e-Defter Denetim Merkezi",
                "surum": "v0.1.0",
                "mod": license_state["label"],
            },
            "lisans": license_state,
            "yollar": {
                "kok": str(self.project_root),
                "log": str(log_dir),
                "rapor": str(report_dir),
                "appLog": str(log_dir / "app.log"),
                "debugLog": str(log_dir / "debug.log"),
                "errorLog": str(log_dir / "error.log"),
            },
            "gunluk": {
                "appLogVar": (log_dir / "app.log").exists(),
                "debugLogVar": (log_dir / "debug.log").exists(),
                "errorLogVar": (log_dir / "error.log").exists(),
                "sonHataSatiri": tail_text(log_dir / "error.log"),
                "sonDebugSatiri": tail_text(log_dir / "debug.log"),
            },
        }

    def quick_discover(self, root_path: str) -> dict[str, object]:
        repaired_root = repair_windows_path(root_path)
        self.logger.info("Hızlı keşif başlatıldı. root=%s repaired=%s", root_path, repaired_root)
        candidates = discover_archives(repaired_root)
        self.logger.info("Hızlı keşif tamamlandı. aday=%s", len(candidates))
        return {"baslangicKlasoru": str(repaired_root), "adaylar": candidates, "bulundu": bool(candidates)}

    def start_quick_discover(self, root_path: str) -> bool:
        return self._start_background_job("discover", self._run_quick_discover_job, str(repair_windows_path(root_path)))

    def start_scan_archive(self, root_path: str, profile: str = VendorProfile.AUTO.value) -> bool:
        repaired_root = str(repair_windows_path(root_path))
        can_scan, license_state, message = can_scan_archive(self.project_root, repaired_root)
        if not can_scan:
            self.logger.warning("Demo tarama limiti nedeniyle tarama engellendi. root=%s", root_path)
            with self._job_lock:
                self._job_state = idle_job_state()
                self._job_state.update(
                    {
                        "tamamlandi": True,
                        "basarili": False,
                        "hata": message,
                        "mesaj": message,
                        "detay": license_state["message"],
                    }
                )
            return False
        return self._start_background_job("scan", self._run_scan_job_fast, repaired_root, profile)

    def start_history_scan_archive(self, root_path: str, profile: str = VendorProfile.AUTO.value) -> bool:
        repaired_root = str(repair_windows_path(root_path))
        can_scan, license_state, message = can_scan_archive(self.project_root, repaired_root)
        if not can_scan:
            self.logger.warning("Gecmis yil taramasi demo limiti nedeniyle engellendi. root=%s", root_path)
            with self._job_lock:
                self._job_state = idle_job_state()
                self._job_state.update(
                    {
                        "tamamlandi": True,
                        "basarili": False,
                        "hata": message,
                        "mesaj": message,
                        "detay": license_state["message"],
                    }
                )
            return False
        return self._start_background_job("history", self._run_history_scan_job, repaired_root, profile)

    def start_scan_years_archive(self, root_path: str, years: list[int], profile: str = VendorProfile.AUTO.value) -> bool:
        repaired_root = str(repair_windows_path(root_path))
        can_scan, license_state, message = can_scan_archive(self.project_root, repaired_root)
        if not can_scan:
            with self._job_lock:
                self._job_state = idle_job_state()
                self._job_state.update(
                    {
                        "tamamlandi": True,
                        "basarili": False,
                        "hata": message,
                        "mesaj": message,
                        "detay": license_state["message"],
                    }
                )
            return False
        normalized_years = sorted({int(year) for year in years if int(year) >= 2000}, reverse=True)
        if not normalized_years:
            return False
        return self._start_background_job("history", self._run_selected_years_scan_job, repaired_root, profile, normalized_years)

    def cancel_job(self) -> bool:
        with self._job_lock:
            if not self._job_state["aktif"]:
                return False
            self._cancel_requested = True
            self._job_state["iptalIstenmis"] = True
            self._job_state["detay"] = "İşlem iptal isteği alındı, güvenli durdurma bekleniyor."
            self._job_state["loglar"].appendleft("İptal isteği alındı.")
            return True

    def open_path(self, target_path: str) -> bool:
        path = repair_windows_path(target_path)
        if not path.exists():
            self.logger.warning("Açılmak istenen yol bulunamadı: %s", target_path)
            return False
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
            self.logger.info("Yol açıldı: %s", target_path)
            return True
        except Exception as exc:  # noqa: BLE001
            self.logger.exception("Yol açılırken hata oluştu: %s", target_path)
            self.logger.error("Open path hatası: %s", exc)
            return False

    def open_external_url(self, target_url: str) -> bool:
        try:
            os.startfile(str(target_url))  # type: ignore[attr-defined]
            self.logger.info("Harici baglanti acildi: %s", target_url)
            return True
        except Exception as exc:  # noqa: BLE001
            self.logger.exception("Harici baglanti acilirken hata olustu: %s", target_url)
            self.logger.error("Open url hatasi: %s", exc)
            return False

    def read_xml_preview(self, target_path: str) -> dict[str, object]:
        path = Path(target_path)
        if not path.exists() or path.suffix.lower() != ".xml":
            return {"ok": False, "message": "XML dosyası bulunamadı."}
        try:
            size = path.stat().st_size
            raw_text = path.read_text(encoding="utf-8", errors="replace")
            truncated = False
            if size <= 1_200_000:
                try:
                    pretty = minidom.parseString(raw_text.encode("utf-8")).toprettyxml(indent="  ")
                except Exception:
                    pretty = raw_text
            else:
                pretty = raw_text[:350_000]
                truncated = len(raw_text) > len(pretty)
            return {
                "ok": True,
                "fileName": path.name,
                "path": str(path),
                "size": size,
                "content": pretty,
                "truncated": truncated,
            }
        except Exception as exc:  # noqa: BLE001
            self.logger.exception("XML önizleme hatası: %s", target_path)
            return {"ok": False, "message": str(exc)}

    def scan_archive(self, root_path: str, profile: str = VendorProfile.AUTO.value) -> dict[str, object]:
        repaired_root = str(repair_windows_path(root_path))
        can_scan, _, message = can_scan_archive(self.project_root, repaired_root)
        if not can_scan:
            raise RuntimeError(message)
        self.logger.info("Tarama başlatıldı. root=%s repaired=%s profile=%s", root_path, repaired_root, profile)
        summary = scan_archive(Path(repaired_root), VendorProfile(profile))
        result = self._finalize_scan(summary)
        self.logger.info(
            "Tarama tamamlandı. mükellef=%s dönem=%s hata=%s",
            result["dashboard"]["toplamFirma"],
            result["dashboard"]["toplamDonem"],
            result["dashboard"]["kritikHata"],
        )
        return result

    def export_excel_report(self, selected_year: str | None = None) -> str | None:
        if not self.last_summary:
            self.logger.warning("Excel raporu istendi ancak aktif tarama verisi yok.")
            return None
        filtered_rows = filter_export_rows(self.last_rows, selected_year)
        report_path = export_excel_report(self.last_summary, filtered_rows, get_reports_dir())
        self.logger.info("Excel raporu oluşturuldu: %s", report_path)
        return str(report_path)

    def export_json_report(self, selected_year: str | None = None) -> str | None:
        if not self.last_summary:
            self.logger.warning("JSON raporu istendi ancak aktif tarama verisi yok.")
            return None
        filtered_rows = filter_export_rows(self.last_rows, selected_year)
        report_path = export_json_report(self.last_summary, filtered_rows, self.last_dashboard, get_reports_dir())
        self.logger.info("JSON raporu oluşturuldu: %s", report_path)
        return str(report_path)

    def export_pdf_report(self, selected_year: str | None = None) -> str | None:
        if not self.last_summary:
            self.logger.warning("PDF raporu istendi ancak aktif tarama verisi yok.")
            return None
        filtered_rows = filter_export_rows(self.last_rows, selected_year)
        report_path = export_pdf_report(self.last_summary, filtered_rows, get_reports_dir())
        self.logger.info("PDF raporu oluşturuldu: %s", report_path)
        return str(report_path)

    def _start_background_job(self, kind: str, target, *args: object) -> bool:
        with self._job_lock:
            if self._job_state["aktif"]:
                return False
            self._cancel_requested = False
            self._job_state = idle_job_state()
            self._job_state.update(
                {
                    "aktif": True,
                    "islemTuru": kind,
                    "asama": "İş hazırlanıyor",
                    "mesaj": "Kuyruk oluşturuluyor...",
                    "detay": str(args[0]) if args else "",
                    "baslangicZamani": time.time(),
                }
            )
        self._worker = threading.Thread(target=target, args=args, daemon=True)
        self._worker.start()
        return True

    def _run_quick_discover_job(self, root_path: str) -> None:
        try:
            repaired_root = str(repair_windows_path(root_path))
            self.logger.info("Arka plan hızlı keşif başladı. root=%s repaired=%s", root_path, repaired_root)
            self._set_job_progress(
                asama="Hızlı keşif başlatıldı",
                mesaj=DISCOVERY_MESSAGES[0],
                detay="Kök klasör yapısı okunuyor.",
                yuzde=6,
                son_islem=repaired_root,
            )

            def progress(event: dict[str, object]) -> None:
                scanned_dirs = int(event.get("scanned_dirs", 0))
                candidates = int(event.get("candidate_count", 0))
                phase_index = min(int(event.get("phase_index", 0)), len(DISCOVERY_MESSAGES) - 1)
                message = DISCOVERY_MESSAGES[phase_index]
                percent = min(72, 10 + phase_index * 12 + min(scanned_dirs // 12, 18))
                self._set_job_progress(
                    asama="Aday kökler hazırlanıyor",
                    mesaj=message,
                    detay=f"{scanned_dirs} klasör tarandı, {candidates} aday kök üretildi.",
                    yuzde=percent,
                    taranan_klasor=scanned_dirs,
                    aday_sayisi=candidates,
                    son_islem=str(event.get("current_path", root_path)),
                    log_message=f"Keşif: {Path(str(event.get('current_path', root_path))).name}",
                )

            candidates = discover_archives(Path(repaired_root), progress_callback=progress, cancel_callback=self._is_cancel_requested)
            result = {"baslangicKlasoru": repaired_root, "adaylar": candidates, "bulundu": bool(candidates)}
            self._finish_job(success=True, result_key="kesifSonucu", result=result, final_message="Aday kök listesi hazır.")
            self._set_job_progress(
                asama="Hızlı keşif tamamlandı",
                mesaj="Aday arşiv kökleri hazır",
                detay=f"{len(candidates)} aday kök bulundu.",
                yuzde=100,
                aday_sayisi=len(candidates),
                son_islem="Aday listesi ekrana aktarıldı.",
            )
        except Exception as exc:  # noqa: BLE001
            if str(exc) == "DISCOVERY_CANCELLED":
                self.logger.info("Arka plan hızlı keşif kullanıcı tarafından iptal edildi.")
                self._finish_job(success=False, error="İşlem kullanıcı tarafından iptal edildi.", final_message="Hızlı keşif iptal edildi.", cancelled=True)
                return
            self.logger.exception("Arka plan hızlı keşif hatası")
            self._finish_job(success=False, error=str(exc), final_message="Hızlı keşif sırasında hata oluştu.")

    def _run_scan_job(self, root_path: str, profile: str) -> None:
        try:
            repaired_root = str(repair_windows_path(root_path))
            can_scan, _, message = can_scan_archive(self.project_root, repaired_root)
            if not can_scan:
                raise RuntimeError(message)
            self.logger.info("Arka plan tarama başladı. root=%s repaired=%s profile=%s", root_path, repaired_root, profile)
            self._set_job_progress(
                asama="Detay denetim başlatıldı",
                mesaj=SCAN_MESSAGES[0],
                detay="Tarama kuyruğu hazırlanıyor.",
                yuzde=8,
                son_islem=repaired_root,
            )

            def progress(event: dict[str, object]) -> None:
                scanned_files = int(event.get("scanned_files", 0))
                total_files = int(event.get("total_files", 0))
                taxpayers = int(event.get("taxpayer_count", 0))
                periods = int(event.get("period_count", 0))
                phase_index = min(int(event.get("phase_index", 0)), len(SCAN_MESSAGES) - 1)
                message = SCAN_MESSAGES[phase_index]
                percent = min(94, 14 + phase_index * 14 + min(scanned_files // 8, 24))
                detail = f"{scanned_files} dosya işlendi"
                if total_files:
                    detail += f", {total_files} dosya görüldü"
                if taxpayers or periods:
                    detail += f", {taxpayers} mükellef, {periods} dönem"
                self._set_job_progress(
                    asama="Derin denetim çalışıyor",
                    mesaj=message,
                    detay=detail + ".",
                    yuzde=percent,
                    taranan_klasor=int(event.get("visited_dirs", 0)),
                    mukellef_sayisi=taxpayers,
                    donem_sayisi=periods,
                    son_islem=str(event.get("current_path", root_path)),
                    log_message=f"Tarama: {Path(str(event.get('current_path', root_path))).name}",
                )

            summary = scan_archive(Path(repaired_root), VendorProfile(profile), progress_callback=progress, cancel_callback=self._is_cancel_requested)
            result = self._finalize_scan(summary)
            self._finish_job(success=True, result_key="taramaVerisi", result=result, final_message="Denetim sonuçları hazır.")
            self._set_job_progress(
                asama="Detay denetim tamamlandı",
                mesaj="Sonuç ekranı hazır",
                detay=f"{len(summary.taxpayers)} mükellef ve {len(summary.period_buckets)} dönem işlendi.",
                yuzde=100,
                mukellef_sayisi=len(summary.taxpayers),
                donem_sayisi=len(summary.period_buckets),
                son_islem="Dashboard ve toplu kontrol ekranı güncellendi.",
            )
        except Exception as exc:  # noqa: BLE001
            if str(exc) == "SCAN_CANCELLED":
                self.logger.info("Arka plan tarama kullanıcı tarafından iptal edildi.")
                self._finish_job(success=False, error="İşlem kullanıcı tarafından iptal edildi.", final_message="Detay denetim iptal edildi.", cancelled=True)
                return
            self.logger.exception("Arka plan tarama hatası")
            self._finish_job(success=False, error=str(exc), final_message="Detay denetimde hata oluştu.")

    def _run_scan_job_fast(self, root_path: str, profile: str) -> None:
        try:
            repaired_root = str(repair_windows_path(root_path))
            can_scan, _, message = can_scan_archive(self.project_root, repaired_root)
            if not can_scan:
                raise RuntimeError(message)
            archive_path = Path(repaired_root)
            year_root_map = collect_archive_year_roots(archive_path)
            archive_years = sorted(year_root_map.keys(), reverse=True)
            primary_year = archive_years[0] if archive_years else None
            year_file_totals = {year: count_supported_files_in_roots(year_root_map.get(year, [archive_path])) for year in archive_years}
            cached_result = load_scan_cache(self.project_root, repaired_root, profile)
            cached_ready_years = sorted(
                {row_year for row_year in extract_ready_years_from_result(cached_result) if primary_year is None or row_year != primary_year},
                reverse=True,
            )
            self.logger.info("Hizli tarama modu basladi. root=%s repaired=%s profile=%s years=%s cached=%s", root_path, repaired_root, profile, archive_years, cached_ready_years)

            def build_year_progress(
                *,
                active_year: int | None,
                completed_years: list[int],
                waiting_years: list[int],
                active_scanned: int = 0,
            ) -> dict[str, object]:
                payload: dict[str, object] = {}
                completed_set = set(completed_years)
                waiting_set = set(waiting_years)
                for year in archive_years:
                    total_files_for_year = max(0, int(year_file_totals.get(year, 0)))
                    if year in completed_set:
                        payload[str(year)] = {
                            "toplamDosya": total_files_for_year,
                            "islenenDosya": total_files_for_year,
                            "yuzde": 100.0,
                            "durum": "ready",
                        }
                    elif active_year == year:
                        processed = min(active_scanned, total_files_for_year) if total_files_for_year else active_scanned
                        progress_value = round((processed / total_files_for_year) * 100, 1) if total_files_for_year else 0.0
                        payload[str(year)] = {
                            "toplamDosya": total_files_for_year,
                            "islenenDosya": processed,
                            "yuzde": progress_value,
                            "durum": "active",
                        }
                    else:
                        payload[str(year)] = {
                            "toplamDosya": total_files_for_year,
                            "islenenDosya": 0,
                            "yuzde": 0.0,
                            "durum": "queued" if year in waiting_set or year not in completed_set else "ready",
                        }
                return payload

            self._set_job_progress(
                asama="Detay denetim baslatildi",
                mesaj=f"{primary_year} hizli gorunum hazirlaniyor..." if primary_year else SCAN_MESSAGES[0],
                detay="Aktif yil taraniyor. Gecmis yillar onbellekten yuklenecek.",
                yuzde=8,
                son_islem=repaired_root,
                tum_yillar=archive_years,
                aktif_yil=primary_year,
                tamamlanan_yillar=cached_ready_years,
                bekleyen_yillar=[],
                yil_ilerleme=build_year_progress(active_year=primary_year, completed_years=cached_ready_years, waiting_years=[], active_scanned=0),
            )

            def progress(
                event: dict[str, object],
                current_year: int | None,
                stage_label: str,
                base_percent: int,
                percent_span: int,
                waiting_years: list[int],
                completed_years: list[int],
            ) -> None:
                scanned_files = int(event.get("scanned_files", 0))
                total_files = int(event.get("total_files", 0))
                taxpayers = int(event.get("taxpayer_count", 0))
                periods = int(event.get("period_count", 0))
                phase_index = min(int(event.get("phase_index", 0)), len(SCAN_MESSAGES) - 1)
                percent = min(96, base_percent + min(percent_span, phase_index * 6 + min(scanned_files // 10, percent_span)))
                detail = f"{scanned_files} dosya islendi"
                if total_files:
                    detail += f", {total_files} dosya goruldu"
                if taxpayers or periods:
                    detail += f", {taxpayers} mukellef, {periods} donem"
                if current_year and waiting_years:
                    detail += f". {current_year} bitince {', '.join(str(item) for item in waiting_years)} taranacak"
                self._set_job_progress(
                    asama=stage_label,
                    mesaj=f"{current_year} taraniyor..." if current_year else SCAN_MESSAGES[phase_index],
                    detay=detail + ".",
                    yuzde=percent,
                    taranan_klasor=int(event.get("visited_dirs", 0)),
                    mukellef_sayisi=taxpayers,
                    donem_sayisi=periods,
                    son_islem=str(event.get("current_path", root_path)),
                    log_message=f"Tarama: {Path(str(event.get('current_path', root_path))).name}",
                    tum_yillar=archive_years,
                    aktif_yil=current_year,
                    bekleyen_yillar=waiting_years,
                    tamamlanan_yillar=completed_years,
                    yil_ilerleme=build_year_progress(
                        active_year=current_year,
                        completed_years=completed_years,
                        waiting_years=waiting_years,
                        active_scanned=scanned_files,
                    ),
                )

            if not primary_year:
                summary = scan_archive(
                    archive_path,
                    VendorProfile(profile),
                    progress_callback=lambda event: progress(event, None, "Derin denetim calisiyor", 14, 80, [], []),
                    cancel_callback=self._is_cancel_requested,
                    search_roots=[archive_path],
                )
                result = self._finalize_scan(summary)
                save_scan_cache(self.project_root, repaired_root, profile, result)
                self._finish_job(success=True, result_key="taramaVerisi", result=result, final_message="Denetim sonuclari hazir.")
                return

            completed_years: list[int] = list(cached_ready_years)

            primary_summary = scan_archive(
                archive_path,
                VendorProfile(profile),
                progress_callback=lambda event: progress(event, primary_year, "Aktif yil hazirlaniyor", 14, 78, [], completed_years),
                cancel_callback=self._is_cancel_requested,
                included_years={primary_year},
                search_roots=year_root_map.get(primary_year, [archive_path]),
            )
            completed_years = [year for year in completed_years if year != primary_year]
            completed_years.insert(0, primary_year)
            result = self._finalize_scan(primary_summary)
            result = merge_result_with_cache(result, cached_result, excluded_years={primary_year})
            result = apply_ready_years_to_result(result, completed_years)
            result = apply_demo_access_to_result(self.project_root, result)
            self._store_last_result(result)
            save_scan_cache(self.project_root, repaired_root, profile, result)
            self._publish_partial_result(result)
            self._set_job_progress(
                asama="Aktif yil hazir",
                mesaj=f"{primary_year} hazir",
                detay="Aktif yil kartlari ekrana alindi. Gecmis yillar icin sagdaki butonu kullanabilirsiniz.",
                yuzde=100,
                mukellef_sayisi=result["dashboard"]["toplamFirma"],
                donem_sayisi=result["dashboard"]["toplamDonem"],
                son_islem=f"{primary_year} ekrana alindi.",
                tum_yillar=archive_years,
                tamamlanan_yillar=completed_years,
                yil_ilerleme=build_year_progress(
                    active_year=None,
                    completed_years=completed_years,
                    waiting_years=[],
                    active_scanned=0,
                ),
            )

            self._finish_job(success=True, result_key="taramaVerisi", result=result, final_message="Denetim sonuclari hazir.")
            self._set_job_progress(
                asama="Detay denetim tamamlandi",
                mesaj="Sonuc ekrani hazir",
                detay=f"{result['dashboard']['toplamFirma']} mukellef ve {result['dashboard']['toplamDonem']} donem hazir.",
                yuzde=100,
                mukellef_sayisi=result["dashboard"]["toplamFirma"],
                donem_sayisi=result["dashboard"]["toplamDonem"],
                son_islem="Dashboard ve toplu kontrol ekrani guncellendi.",
                tum_yillar=archive_years,
                tamamlanan_yillar=completed_years,
                yil_ilerleme=build_year_progress(
                    active_year=None,
                    completed_years=completed_years,
                    waiting_years=[],
                    active_scanned=0,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            if str(exc) == "SCAN_CANCELLED":
                self.logger.info("Hizli tarama modu kullanici tarafindan iptal edildi.")
                self._finish_job(success=False, error="Islem kullanici tarafindan iptal edildi.", final_message="Detay denetim iptal edildi.", cancelled=True)
                return
            self.logger.exception("Hizli tarama modu hatasi")
            self._finish_job(success=False, error=str(exc), final_message="Detay denetimde hata olustu.")

    def _run_history_scan_job(self, root_path: str, profile: str) -> None:
        try:
            repaired_root = str(repair_windows_path(root_path))
            can_scan, _, message = can_scan_archive(self.project_root, repaired_root)
            if not can_scan:
                raise RuntimeError(message)
            archive_path = Path(repaired_root)
            year_root_map = collect_archive_year_roots(archive_path)
            archive_years = sorted(year_root_map.keys(), reverse=True)
            if len(archive_years) <= 1:
                cached_result = load_scan_cache(self.project_root, repaired_root, profile)
                self._finish_job(success=True, result_key="taramaVerisi", result=cached_result or {"dashboard": empty_dashboard(), "donemler": [], "teknik_ozet": {}, "sistemDurumu": self.get_system_status()}, final_message="Taranacak gecmis yil bulunmuyor.")
                return

            primary_year = archive_years[0]
            background_years = archive_years[1:]
            year_file_totals = {year: count_supported_files_in_roots(year_root_map.get(year, [archive_path])) for year in archive_years}
            cached_result = load_scan_cache(self.project_root, repaired_root, profile)
            current_result = cached_result or {"dashboard": empty_dashboard(), "donemler": [], "teknik_ozet": {}, "sistemDurumu": self.get_system_status()}
            completed_years = sorted(
                {row_year for row_year in extract_ready_years_from_result(current_result) if row_year != primary_year},
                reverse=True,
            )
            waiting_years = [year for year in background_years if year not in completed_years]

            def build_year_progress(active_year: int | None, done_years: list[int], queue_years: list[int], active_scanned: int = 0) -> dict[str, object]:
                payload: dict[str, object] = {}
                done_set = set(done_years)
                queue_set = set(queue_years)
                for year in archive_years:
                    total_files_for_year = max(0, int(year_file_totals.get(year, 0)))
                    if year in done_set:
                        payload[str(year)] = {"toplamDosya": total_files_for_year, "islenenDosya": total_files_for_year, "yuzde": 100.0, "durum": "ready"}
                    elif year == active_year:
                        processed = min(active_scanned, total_files_for_year) if total_files_for_year else active_scanned
                        yuzde = round((processed / total_files_for_year) * 100, 1) if total_files_for_year else 0.0
                        payload[str(year)] = {"toplamDosya": total_files_for_year, "islenenDosya": processed, "yuzde": yuzde, "durum": "active"}
                    else:
                        payload[str(year)] = {"toplamDosya": total_files_for_year, "islenenDosya": 0, "yuzde": 0.0, "durum": "queued" if year in queue_set else "ready"}
                return payload

            self._set_job_progress(
                asama="Gecmis yillar taraniyor",
                mesaj="Gecmis yillar taramasi basladi...",
                detay="Onbellek guncellenecek.",
                yuzde=8,
                son_islem=repaired_root,
                tum_yillar=archive_years,
                aktif_yil=waiting_years[0] if waiting_years else None,
                bekleyen_yillar=waiting_years,
                tamamlanan_yillar=completed_years,
                yil_ilerleme=build_year_progress(waiting_years[0] if waiting_years else None, completed_years, waiting_years, 0),
            )

            merged_result = current_result
            for index, year in enumerate(waiting_years):
                remaining = waiting_years[index + 1 :]

                def progress(event: dict[str, object], current_year: int = year, waiting: list[int] = remaining) -> None:
                    scanned_files = int(event.get("scanned_files", 0))
                    total_files = int(event.get("total_files", 0))
                    taxpayers = int(event.get("taxpayer_count", 0))
                    periods = int(event.get("period_count", 0))
                    detail = f"{scanned_files} dosya islendi"
                    if total_files:
                        detail += f", {total_files} dosya goruldu"
                    if taxpayers or periods:
                        detail += f", {taxpayers} mukellef, {periods} donem"
                    self._set_job_progress(
                        asama="Gecmis yillar taraniyor",
                        mesaj=f"{current_year} taraniyor...",
                        detay=detail + ".",
                        yuzde=min(96, 18 + index * 18 + min(scanned_files // 8, 16)),
                        taranan_klasor=int(event.get("visited_dirs", 0)),
                        mukellef_sayisi=merged_result["dashboard"].get("toplamFirma", 0),
                        donem_sayisi=merged_result["dashboard"].get("toplamDonem", 0),
                        son_islem=str(event.get("current_path", root_path)),
                        log_message=f"Tarama: {Path(str(event.get('current_path', root_path))).name}",
                        tum_yillar=archive_years,
                        aktif_yil=current_year,
                        bekleyen_yillar=[current_year, *waiting],
                        tamamlanan_yillar=completed_years,
                        yil_ilerleme=build_year_progress(current_year, completed_years, [current_year, *waiting], scanned_files),
                    )

                year_summary = scan_archive(
                    archive_path,
                    VendorProfile(profile),
                    progress_callback=progress,
                    cancel_callback=self._is_cancel_requested,
                    included_years={year},
                    search_roots=year_root_map.get(year, [archive_path]),
                )
                year_result = self._finalize_scan(year_summary)
                merged_result = merge_result_with_cache(year_result, merged_result)
                if year in extract_result_years(year_result):
                    completed_years.append(year)
                completed_years = sorted(set(completed_years), reverse=True)
                merged_result = apply_ready_years_to_result(merged_result, completed_years)
                merged_result = apply_demo_access_to_result(self.project_root, merged_result)
                self._store_last_result(merged_result)
                save_scan_cache(self.project_root, repaired_root, profile, merged_result)
                self._publish_partial_result(merged_result)

            final_completed_years = sorted(set(extract_ready_years_from_result(merged_result)), reverse=True)
            merged_result = apply_ready_years_to_result(merged_result, final_completed_years)
            merged_result = apply_demo_access_to_result(self.project_root, merged_result)
            self._set_job_progress(
                asama="Gecmis yillar tamamlandi",
                mesaj="Gecmis yillar guncellendi",
                detay="Onbellek yenilendi.",
                yuzde=100,
                mukellef_sayisi=merged_result["dashboard"]["toplamFirma"],
                donem_sayisi=merged_result["dashboard"]["toplamDonem"],
                son_islem="Gecmis yil taramasi tamamlandi.",
                tum_yillar=archive_years,
                tamamlanan_yillar=final_completed_years,
                yil_ilerleme=build_year_progress(None, final_completed_years, [], 0),
            )
            self._finish_job(success=True, result_key="taramaVerisi", result=merged_result, final_message="Gecmis yillar onbellege alindi.")
        except Exception as exc:  # noqa: BLE001
            if str(exc) == "SCAN_CANCELLED":
                self.logger.info("Gecmis yil taramasi kullanici tarafindan iptal edildi.")
                self._finish_job(success=False, error="Islem kullanici tarafindan iptal edildi.", final_message="Gecmis yil taramasi iptal edildi.", cancelled=True)
                return
            self.logger.exception("Gecmis yil taramasi hatasi")
            self._finish_job(success=False, error=str(exc), final_message="Gecmis yil taramasinda hata olustu.")

    def _run_selected_years_scan_job(self, root_path: str, profile: str, years: list[int]) -> None:
        try:
            repaired_root = str(repair_windows_path(root_path))
            archive_path = Path(repaired_root)
            year_root_map = collect_archive_year_roots(archive_path)
            archive_years = sorted(year_root_map.keys(), reverse=True)
            target_years = [year for year in years if year in archive_years]
            if not target_years:
                raise RuntimeError("Secilen yillar arsivde bulunamadi.")
            year_file_totals = {year: count_supported_files_in_roots(year_root_map.get(year, [archive_path])) for year in archive_years}
            cached_result = load_scan_cache(self.project_root, repaired_root, profile)
            merged_result = cached_result or {"dashboard": empty_dashboard(), "donemler": [], "teknik_ozet": {}, "sistemDurumu": self.get_system_status()}
            completed_years = sorted(set(extract_ready_years_from_result(merged_result)) - set(target_years), reverse=True)

            def build_year_progress(active_year: int | None, done_years: list[int], queue_years: list[int], active_scanned: int = 0) -> dict[str, object]:
                payload: dict[str, object] = {}
                done_set = set(done_years)
                queue_set = set(queue_years)
                for year in archive_years:
                    total_files_for_year = max(0, int(year_file_totals.get(year, 0)))
                    if year in done_set:
                        payload[str(year)] = {"toplamDosya": total_files_for_year, "islenenDosya": total_files_for_year, "yuzde": 100.0, "durum": "ready"}
                    elif year == active_year:
                        processed = min(active_scanned, total_files_for_year) if total_files_for_year else active_scanned
                        yuzde = round((processed / total_files_for_year) * 100, 1) if total_files_for_year else 0.0
                        payload[str(year)] = {"toplamDosya": total_files_for_year, "islenenDosya": processed, "yuzde": yuzde, "durum": "active"}
                    else:
                        payload[str(year)] = {"toplamDosya": total_files_for_year, "islenenDosya": 0, "yuzde": 0.0, "durum": "queued" if year in queue_set else "ready"}
                return payload

            self._set_job_progress(
                asama="Secili yillar taraniyor",
                mesaj=f"{target_years[0]} taraniyor...",
                detay="Secilen yillar guncellenecek.",
                yuzde=8,
                son_islem=repaired_root,
                tum_yillar=archive_years,
                aktif_yil=target_years[0],
                bekleyen_yillar=target_years,
                tamamlanan_yillar=completed_years,
                yil_ilerleme=build_year_progress(target_years[0], completed_years, target_years, 0),
            )

            for index, year in enumerate(target_years):
                remaining = target_years[index + 1 :]

                def progress(event: dict[str, object], current_year: int = year, waiting: list[int] = remaining) -> None:
                    scanned_files = int(event.get("scanned_files", 0))
                    total_files = int(event.get("total_files", 0))
                    self._set_job_progress(
                        asama="Secili yillar taraniyor",
                        mesaj=f"{current_year} taraniyor...",
                        detay=f"{scanned_files} dosya islendi, {total_files} dosya goruldu.",
                        yuzde=min(96, 15 + index * 20 + min(scanned_files // 8, 18)),
                        taranan_klasor=int(event.get("visited_dirs", 0)),
                        mukellef_sayisi=merged_result["dashboard"].get("toplamFirma", 0),
                        donem_sayisi=merged_result["dashboard"].get("toplamDonem", 0),
                        son_islem=str(event.get("current_path", root_path)),
                        log_message=f"Tarama: {Path(str(event.get('current_path', root_path))).name}",
                        tum_yillar=archive_years,
                        aktif_yil=current_year,
                        bekleyen_yillar=[current_year, *waiting],
                        tamamlanan_yillar=completed_years,
                        yil_ilerleme=build_year_progress(current_year, completed_years, [current_year, *waiting], scanned_files),
                    )

                year_summary = scan_archive(
                    archive_path,
                    VendorProfile(profile),
                    progress_callback=progress,
                    cancel_callback=self._is_cancel_requested,
                    included_years={year},
                    search_roots=year_root_map.get(year, [archive_path]),
                )
                year_result = self._finalize_scan(year_summary)
                merged_result = merge_result_with_cache(year_result, merged_result, excluded_years={year})
                if year in extract_result_years(year_result):
                    completed_years.append(year)
                completed_years = sorted(set(completed_years), reverse=True)
                merged_result = apply_ready_years_to_result(merged_result, completed_years)
                merged_result = apply_demo_access_to_result(self.project_root, merged_result)
                self._store_last_result(merged_result)
                save_scan_cache(self.project_root, repaired_root, profile, merged_result)
                self._publish_partial_result(merged_result)

            final_completed_years = sorted(set(extract_ready_years_from_result(merged_result)), reverse=True)
            merged_result = apply_ready_years_to_result(merged_result, final_completed_years)
            merged_result = apply_demo_access_to_result(self.project_root, merged_result)
            self._set_job_progress(
                asama="Secili yillar tamamlandi",
                mesaj="Secili yillar guncellendi",
                detay="Secilen yillar hazir.",
                yuzde=100,
                mukellef_sayisi=merged_result["dashboard"]["toplamFirma"],
                donem_sayisi=merged_result["dashboard"]["toplamDonem"],
                son_islem="Secili yil taramasi tamamlandi.",
                tum_yillar=archive_years,
                tamamlanan_yillar=final_completed_years,
                yil_ilerleme=build_year_progress(None, final_completed_years, [], 0),
            )
            self._finish_job(success=True, result_key="taramaVerisi", result=merged_result, final_message="Secili yillar guncellendi.")
        except Exception as exc:  # noqa: BLE001
            if str(exc) == "SCAN_CANCELLED":
                self._finish_job(success=False, error="Islem kullanici tarafindan iptal edildi.", final_message="Secili yil taramasi iptal edildi.", cancelled=True)
                return
            self.logger.exception("Secili yil taramasi hatasi")
            self._finish_job(success=False, error=str(exc), final_message="Secili yil taramasinda hata olustu.")

    def _finalize_scan(self, summary: ScanSummary) -> dict[str, object]:
        self.last_summary = summary
        return self._rebuild_last_result()

    def _store_last_result(self, result: dict[str, object]) -> None:
        self.last_rows = list(result.get("donemler", []))
        self.last_dashboard = dict(result.get("dashboard", empty_dashboard()))

    def _rebuild_last_result(self) -> dict[str, object]:
        if not self.last_summary:
            return {"dashboard": empty_dashboard(), "donemler": [], "teknik_ozet": {}, "sistemDurumu": self.get_system_status()}
        summary_dict = summary_to_dict(self.last_summary)
        rows = build_period_rows(self.last_summary)
        rows = apply_gap_and_override_rules(rows, self.project_root)
        dashboard = build_dashboard(self.last_summary, rows)
        result = {"dashboard": dashboard, "donemler": rows, "teknik_ozet": summary_dict, "sistemDurumu": self.get_system_status()}
        result = apply_demo_access_to_result(self.project_root, result)
        self.last_rows = list(result.get("donemler", []))
        self.last_dashboard = dict(result.get("dashboard", empty_dashboard()))
        return result

    def _set_job_progress(
        self,
        *,
        asama: str,
        mesaj: str,
        detay: str,
        yuzde: int,
        taranan_klasor: int | None = None,
        aday_sayisi: int | None = None,
        mukellef_sayisi: int | None = None,
        donem_sayisi: int | None = None,
        son_islem: str | None = None,
        log_message: str | None = None,
        tum_yillar: list[int] | None = None,
        aktif_yil: int | None = None,
        bekleyen_yillar: list[int] | None = None,
        tamamlanan_yillar: list[int] | None = None,
        yil_ilerleme: dict[str, object] | None = None,
    ) -> None:
        with self._job_lock:
            self._job_state["asama"] = asama
            self._job_state["mesaj"] = mesaj
            self._job_state["detay"] = detay
            self._job_state["yuzde"] = yuzde
            self._job_state["gecenSureSaniye"] = round(time.time() - float(self._job_state["baslangicZamani"]), 1)
            if taranan_klasor is not None:
                self._job_state["tarananKlasor"] = taranan_klasor
            if aday_sayisi is not None:
                self._job_state["adaySayisi"] = aday_sayisi
            if mukellef_sayisi is not None:
                self._job_state["mukellefSayisi"] = mukellef_sayisi
            if donem_sayisi is not None:
                self._job_state["donemSayisi"] = donem_sayisi
            if son_islem is not None:
                self._job_state["sonIslem"] = son_islem
            if tum_yillar is not None:
                self._job_state["tumYillar"] = list(tum_yillar)
            if aktif_yil is not None:
                self._job_state["aktifYil"] = aktif_yil
            if bekleyen_yillar is not None:
                self._job_state["bekleyenYillar"] = list(bekleyen_yillar)
            if tamamlanan_yillar is not None:
                self._job_state["tamamlananYillar"] = list(tamamlanan_yillar)
            if yil_ilerleme is not None:
                self._job_state["yilIlerleme"] = dict(yil_ilerleme)
            if log_message:
                self._job_state["loglar"].appendleft(log_message)

    def _publish_partial_result(self, result: dict[str, object]) -> None:
        with self._job_lock:
            self._job_state["taramaVerisi"] = result

    def _finish_job(
        self,
        *,
        success: bool,
        final_message: str,
        result_key: str | None = None,
        result: dict[str, object] | None = None,
        error: str = "",
        cancelled: bool = False,
    ) -> None:
        with self._job_lock:
            self._job_state["aktif"] = False
            self._job_state["tamamlandi"] = True
            self._job_state["basarili"] = success
            self._job_state["iptalEdildi"] = cancelled
            self._job_state["hata"] = error
            self._job_state["gecenSureSaniye"] = round(time.time() - float(self._job_state["baslangicZamani"]), 1)
            self._job_state["asama"] = "Tamamlandi" if success else "Durduruldu"
            self._job_state["mesaj"] = "Tarama tamamlandi." if success else (error or final_message or "Islem durduruldu.")
            self._job_state["detay"] = final_message
            self._job_state["yuzde"] = 100 if success else self._job_state.get("yuzde", 0)
            self._job_state["aktifYil"] = None
            self._job_state["bekleyenYillar"] = []
            if result_key and result is not None:
                self._job_state[result_key] = result
            if final_message:
                self._job_state["loglar"].appendleft(final_message)

    def _is_cancel_requested(self) -> bool:
        with self._job_lock:
            return self._cancel_requested


def idle_job_state() -> dict[str, object]:
    return {
        "aktif": False,
        "tamamlandi": False,
        "basarili": True,
        "islemTuru": "idle",
        "asama": "Beklemede",
        "mesaj": "Hazır",
        "detay": "",
        "yuzde": 0,
        "tarananKlasor": 0,
        "adaySayisi": 0,
        "mukellefSayisi": 0,
        "donemSayisi": 0,
        "gecenSureSaniye": 0,
        "sonIslem": "",
        "loglar": deque(maxlen=6),
        "hata": "",
        "iptalIstenmis": False,
        "iptalEdildi": False,
        "baslangicZamani": 0.0,
        "tumYillar": [],
        "aktifYil": None,
        "bekleyenYillar": [],
        "tamamlananYillar": [],
        "yilIlerleme": {},
    }


def collect_archive_years(root_path: Path) -> list[int]:
    return sorted(collect_archive_year_roots(root_path).keys(), reverse=True)


def collect_archive_year_roots(root_path: Path) -> dict[int, list[Path]]:
    year_roots: dict[int, list[Path]] = {}
    years: set[int] = set()
    for current_root, dir_names, _ in os.walk(root_path, topdown=True):
        current_path = Path(current_root)
        matched_dirs: list[str] = []
        for directory_name in list(dir_names):
            match = DATE_RANGE_PATTERN.fullmatch(directory_name)
            if not match:
                continue
            try:
                start = datetime.strptime(match.group("start"), "%d.%m.%Y")
            except ValueError:
                continue
            years.add(start.year)
            matched_dirs.append(directory_name)
            year_roots.setdefault(start.year, []).append(current_path / directory_name)
        if matched_dirs:
            dir_names[:] = [name for name in dir_names if name not in matched_dirs]
    return {year: roots for year, roots in year_roots.items() if roots}


def count_supported_files_in_roots(roots: list[Path]) -> int:
    total = 0
    for root in roots:
        if not root.exists():
            continue
        for current_root, _, file_names in os.walk(root):
            current_path = Path(current_root)
            total += sum(1 for file_name in file_names if (current_path / file_name).suffix.lower() in {".xml", ".zip", ".xslt", ".xsd", ".sch"})
    return total


def get_scan_cache_dir(base_dir: Path) -> Path:
    target = get_runtime_scan_cache_dir()
    target.mkdir(parents=True, exist_ok=True)
    return target


def get_scan_cache_path(base_dir: Path, root_path: str, profile: str) -> Path:
    digest = hashlib.sha1(f"{repair_windows_path(root_path)}|{profile}".encode("utf-8"), usedforsecurity=False).hexdigest()[:16]
    return get_scan_cache_dir(base_dir) / f"{digest}.json"


def load_scan_cache(base_dir: Path, root_path: str, profile: str) -> dict[str, Any] | None:
    target = get_scan_cache_path(base_dir, root_path, profile)
    if not target.exists():
        return None
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return None
    result = payload.get("result")
    if not isinstance(result, dict):
        return None
    return result


def load_latest_scan_cache_result(base_dir: Path) -> dict[str, Any] | None:
    cache_dir = get_scan_cache_dir(base_dir)
    if not cache_dir.exists():
        return None
    latest_file: Path | None = None
    latest_mtime = -1.0
    for candidate in cache_dir.glob("*.json"):
        try:
            mtime = candidate.stat().st_mtime
        except OSError:
            continue
        if mtime > latest_mtime:
            latest_mtime = mtime
            latest_file = candidate
    if latest_file is None:
        return None
    try:
        payload = json.loads(latest_file.read_text(encoding="utf-8"))
    except Exception:
        return None
    result = payload.get("result")
    if not isinstance(result, dict):
        return None
    dashboard = result.get("dashboard")
    if isinstance(dashboard, dict):
        saved_at = str(payload.get("saved_at", "")).strip()
        if saved_at:
            dashboard["sonTarama"] = saved_at.replace("T", " ")
    return result


def save_scan_cache(base_dir: Path, root_path: str, profile: str, result: dict[str, Any]) -> Path:
    target = get_scan_cache_path(base_dir, root_path, profile)
    payload = {
        "root_path": str(repair_windows_path(root_path)),
        "profile": profile,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "years": sorted(extract_ready_years_from_result(result), reverse=True),
        "result": result,
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def extract_result_years(result: dict[str, Any] | None) -> set[int]:
    if not result:
        return set()
    rows = result.get("donemler", [])
    years = set()
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            year = row.get("yil")
            if isinstance(year, int):
                years.add(year)
    return years


def extract_ready_years_from_result(result: dict[str, Any] | None) -> set[int]:
    return set(extract_result_years(result))


def apply_ready_years_to_result(result: dict[str, Any], ready_years: list[int] | set[int]) -> dict[str, Any]:
    dashboard = dict(result.get("dashboard", empty_dashboard()))
    available_years = extract_result_years(result)
    dashboard["hazirYillar"] = sorted(
        {
            int(year)
            for year in ready_years
            if int(year) >= 2000 and int(year) in available_years
        },
        reverse=True,
    )
    result["dashboard"] = dashboard
    return result


def tail_text(path: Path, line_count: int = 1) -> str:
    if not path.exists():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return ""
    if not lines:
        return ""
    return " | ".join(lines[-line_count:])


def relaxed_path_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    cleaned = re.sub(r"[^a-z0-9]+", "", stripped.casefold().replace("?", ""))
    return cleaned


def repair_windows_path(raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.exists():
        return candidate

    normalized_raw = str(raw_path).strip().replace("/", "\\")
    drive_match = re.match(r"^(?P<drive>[A-Za-z]:)\\(?P<rest>.*)$", normalized_raw)
    if not drive_match:
        return candidate

    drive_root = Path(f"{drive_match.group('drive')}\\")
    if not drive_root.exists():
        return candidate

    current = drive_root
    rest = drive_match.group("rest")
    if not rest:
        return current

    for part in [item for item in rest.split("\\") if item]:
        direct = current / part
        if direct.exists():
            current = direct
            continue
        try:
            entries = list(current.iterdir())
        except OSError:
            return direct
        relaxed_part = relaxed_path_key(part)
        exact_relaxed = next((entry for entry in entries if relaxed_path_key(entry.name) == relaxed_part), None)
        if exact_relaxed is not None:
            current = exact_relaxed
            continue
        partial_relaxed = next((entry for entry in entries if relaxed_part and relaxed_part in relaxed_path_key(entry.name)), None)
        if partial_relaxed is not None:
            current = partial_relaxed
            continue
        fuzzy_relaxed = max(
            entries,
            key=lambda entry: SequenceMatcher(None, relaxed_part, relaxed_path_key(entry.name)).ratio(),
            default=None,
        )
        if fuzzy_relaxed is not None:
            ratio = SequenceMatcher(None, relaxed_part, relaxed_path_key(fuzzy_relaxed.name)).ratio()
            if ratio >= 0.6:
                current = fuzzy_relaxed
                continue
        current = direct
    return current


def build_transition_map(summary: ScanSummary) -> dict[str, dict[str, Any]]:
    records_by_taxpayer: dict[str, list[FileRecord]] = {}
    for record in summary.records:
        if not record.canonical_taxpayer_key:
            continue
        records_by_taxpayer.setdefault(record.canonical_taxpayer_key, []).append(record)

    transition_map: dict[str, dict[str, Any]] = {}
    for taxpayer_key, records in records_by_taxpayer.items():
        info = detect_taxpayer_transition(records)
        if info:
            transition_map[taxpayer_key] = info
    return transition_map


def detect_taxpayer_transition(records: list[FileRecord]) -> dict[str, Any] | None:
    roots: dict[str, dict[str, Any]] = {}
    tasfiye_hint = False

    for record in records:
        root_info = extract_archive_root_info(record)
        if not root_info:
            continue
        entry = roots.setdefault(
            root_info["label"],
            {
                "label": root_info["label"],
                "start": root_info["start"],
                "end": root_info["end"],
                "is_partial": root_info["is_partial"],
                "months": set(),
                "paths": set(),
            },
        )
        if record.period_month is not None:
            entry["months"].add(int(record.period_month))
        entry["paths"].add(str(record.file_path.parent))
        lowered_path = str(record.file_path).casefold()
        lowered_name = " ".join(
            value.casefold()
            for value in (record.company_name_from_path, record.xml_metadata.company_name, record.file_name)
            if value
        )
        if (
            "tasfiye" in lowered_path
            or "tasfiye" in lowered_name
            or "tas.h" in lowered_path
            or "tas h" in lowered_name
            or "tasf" in lowered_path
            or "tasf" in lowered_name
        ):
            tasfiye_hint = True

    partial_roots = sorted((entry for entry in roots.values() if entry["is_partial"]), key=lambda item: item["start"])
    if not partial_roots:
        return None

    transition_root = partial_roots[0]
    full_roots = sorted(
        (
            entry
            for entry in roots.values()
            if not entry["is_partial"] and entry["start"].year == transition_root["start"].year
        ),
        key=lambda item: item["start"],
    )
    primary_root = full_roots[0] if full_roots else sorted(roots.values(), key=lambda item: item["start"])[0]

    if not full_roots:
        transition_kind = "tasfiye" if tasfiye_hint else "kurulus"
    else:
        transition_kind = "tasfiye" if tasfiye_hint else "gecis"

    label_map = {
        "tasfiye": "Tasfiye",
        "gecis": "Geçiş",
        "kurulus": "Dönem İçi Kuruluş",
    }

    return {
        "kind": transition_kind,
        "label": label_map[transition_kind],
        "transitionDate": transition_root["start"].strftime("%d.%m.%Y"),
        "transitionYear": transition_root["start"].year,
        "transitionMonth": transition_root["start"].month,
        "transitionDay": transition_root["start"].day,
        "primaryRoot": primary_root["label"],
        "transitionRoot": transition_root["label"],
        "primaryMonths": sorted(primary_root["months"]),
        "transitionMonths": sorted(transition_root["months"]),
    }


def extract_archive_root_info(record: FileRecord) -> dict[str, Any] | None:
    for part in record.relative_path.parts:
        match = DATE_RANGE_PATTERN.fullmatch(part)
        if not match:
            continue
        try:
            start = datetime.strptime(match.group("start"), "%d.%m.%Y")
            end = datetime.strptime(match.group("end"), "%d.%m.%Y")
        except ValueError:
            return None
        return {
            "label": part,
            "start": start,
            "end": end,
            "is_partial": not (start.day == 1 and start.month == 1),
        }
    return None


def detect_transition_role(
    transition: dict[str, Any] | None,
    period: PeriodBucket,
    related_records: list[FileRecord],
) -> dict[str, Any]:
    if not transition or period.period_year != transition["transitionYear"] or period.period_month is None:
        return {"role": "", "label": "", "risk": "", "summary": [], "actions": [], "allow_transition_duplicates": False}

    root_labels = {
        root_info["label"]
        for root_info in (extract_archive_root_info(record) for record in related_records)
        if root_info
    }
    transition_root = transition["transitionRoot"]
    primary_root = transition["primaryRoot"]
    transition_month = int(transition["transitionMonth"])

    if period.period_month < transition_month:
        return {"role": "pre", "label": "", "risk": "", "summary": [], "actions": [], "allow_transition_duplicates": False}

    if period.period_month == transition_month:
        if transition["kind"] == "kurulus":
            return {
                "role": "transition",
                "label": transition["label"],
                "risk": "LOW",
                "summary": ["Firma bu ay içinde kurulmuş görünüyor. İlk dönem başlangıcı ay ortasında olabilir."],
                "actions": ["Kuruluş ayına ait başlangıç dosyalarını ve ilk berat setini kontrol edin."],
                "allow_transition_duplicates": False,
            }
        if transition["kind"] == "tasfiye" and primary_root == transition_root:
            return {
                "role": "transition",
                "label": transition["label"],
                "risk": "LOW",
                "summary": ["Tasfiye klasörü bu ay başlıyor. Sonraki dönemler tasfiye klasöründen devam etmelidir."],
                "actions": ["Tasfiye başlangıç ayındaki dosyaların ve beratların tam olduğunu kontrol edin."],
                "allow_transition_duplicates": False,
            }
        if primary_root in root_labels and transition_root in root_labels:
            return {
                "role": "transition",
                "label": transition["label"],
                "risk": "LOW",
                "summary": [f"{transition['label']} tespit edildi. Bu ay eski ve yeni klasör birlikte izleniyor."],
                "actions": ["Geçiş ayındaki iki klasörün de tam ve onaylı olduğundan emin olun."],
                "allow_transition_duplicates": True,
            }
        if transition_root in root_labels:
            return {
                "role": "post",
                "label": transition["label"],
                "risk": "MEDIUM",
                "summary": [f"{transition['label']} başlangıç ayı görünüyor ancak önceki klasör görünmüyor."],
                "actions": ["Tasfiye veya devir öncesi klasör kayıtlarını da kontrol edin."],
                "allow_transition_duplicates": False,
            }
        return {
            "role": "pre",
            "label": transition["label"],
            "risk": "MEDIUM",
            "summary": [f"{transition['label']} başlangıç ayı görünüyor ancak sonraki klasör görünmüyor."],
            "actions": ["Yeni klasörün oluştuğunu ve aynı ayın devam setinin geldiğini doğrulayın."],
            "allow_transition_duplicates": False,
        }

    if transition_root in root_labels:
        return {
            "role": "post",
            "label": transition["label"],
            "risk": "",
            "summary": [],
            "actions": [],
            "allow_transition_duplicates": False,
        }

    return {
        "role": "missing_post",
        "label": transition["label"],
        "risk": "HIGH",
        "summary": [f"{transition['label']} sonrası dönem bu klasörde devam etmiyor."],
        "actions": ["Geçiş sonrası klasörde ilgili ayın dosyalarını ve GİB onaylı suretlerini kontrol edin."],
        "allow_transition_duplicates": False,
    }


def build_period_rows(summary: ScanSummary) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    taxpayer_lookup = {taxpayer.taxpayer_key: taxpayer for taxpayer in summary.taxpayers}
    transition_map = build_transition_map(summary)
    accountant_map = build_accountant_fallback_map(summary.records)

    for period in summary.period_buckets:
        taxpayer = taxpayer_lookup.get(period.company_key)
        related_records = find_related_records(summary.records, period)
        transition = transition_map.get(period.company_key)
        transition_state = detect_transition_role(transition, period, related_records)
        diagnostics = analyze_period(period, related_records, transition_state)
        metadata = collect_period_metadata(period)
        month_label = f"{period.period_month or 0:02d}"
        fallback_vkn = taxpayer.vkn_or_tckn if taxpayer else period.company_key
        accountant_name = (
            (taxpayer.accountant_name if taxpayer else "")
            or metadata["accountant"]
            or accountant_map.get(fallback_vkn, "")
        )
        rows.append(
            {
                "id": f"{period.company_key}-{period.period_year}-{month_label}",
                "firmaAnahtari": taxpayer.vkn_or_tckn if taxpayer and taxpayer.vkn_or_tckn else period.company_key,
                "firma": taxpayer.display_name if taxpayer else period.company_key,
                "resmiUnvan": taxpayer.official_name if taxpayer else period.company_key,
                "vkn": taxpayer.vkn_or_tckn if taxpayer else period.company_key,
                "yil": period.period_year or 0,
                "ay": month_label,
                "profil": "Klasör Taraması",
                "aramaMetni": taxpayer.search_text if taxpayer else "",
                "maliMusavir": accountant_name,
                "gonderimTarihi": metadata["creation_date"],
                "imzaTarihi": metadata["signing_time"],
                "gibOnayTarihi": metadata["gib_approval_date"],
                "donemBaslangic": metadata["period_start"],
                "donemBitis": metadata["period_end"],
                "klasorYolu": metadata["folder_path"],
                "kontroller": build_control_rows(period, diagnostics),
                "yevmiye": diagnostics["statuses"]["JOURNAL_BOOK"],
                "kebir": diagnostics["statuses"]["LEDGER_BOOK"],
                "yevmiyeBerat": diagnostics["statuses"]["JOURNAL_BERAT"],
                "kebirBerat": diagnostics["statuses"]["LEDGER_BERAT"],
                "gibOnayliBerat": diagnostics["gib_status"],
                "defterRaporu": diagnostics["statuses"]["DEFTER_RAPORU"],
                "envanterVar": diagnostics["inventory_present"],
                "gibEnvanterVar": bool(period.documents.get(DocumentType.GIB_APPROVED_INVENTORY_BERAT)),
                "durum": diagnostics["overall_status"],
                "risk": diagnostics["risk"],
                "ozet": diagnostics["summary"],
                "aksiyonlar": diagnostics["actions"],
                "ozelDurumTipi": taxpayer.special_case_kind if taxpayer else "",
                "ozelDurum": taxpayer.special_case_label if taxpayer else "",
                "dosyalar": flatten_files(period),
                "topluPaketler": flatten_supporting_files(related_records, {DocumentType.AGGREGATE_PACKAGE}),
                "yardimciDosyalar": flatten_supporting_files(related_records, {DocumentType.AUXILIARY, DocumentType.UNKNOWN}),
                "sorunlar": build_issue_rows(period, diagnostics),
                "loglar": build_period_logs(summary, diagnostics),
                "gecisTipi": transition["kind"] if transition else "",
                "gecisEtiketi": transition_state["label"] if transition_state["role"] else "",
                "gecisRolu": transition_state["role"],
                "gecisTarihi": transition["transitionDate"] if transition else "",
                "arsivKokleri": sorted(
                    {
                        root_info["label"]
                        for root_info in (extract_archive_root_info(record) for record in related_records)
                        if root_info
                    }
                ),
            }
        )
    return sorted(rows, key=lambda item: (item["firma"].casefold(), item["yil"], item["ay"]))


def build_dashboard(summary: ScanSummary, rows: list[dict[str, Any]]) -> dict[str, Any]:
    risk_counter = Counter(row["risk"] for row in rows)
    taxpayers: list[dict[str, Any]] = []
    rows_by_taxpayer: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        rows_by_taxpayer.setdefault((row["firma"], row["vkn"]), []).append(row)
    for taxpayer in summary.taxpayers:
        taxpayer_rows = rows_by_taxpayer.get((taxpayer.display_name, taxpayer.vkn_or_tckn), [])
        years = sorted({row["yil"] for row in taxpayer_rows if row["yil"]}, reverse=True)
        for year in years:
            yearly_rows = [row for row in taxpayer_rows if row["yil"] == year]
            taxpayers.append(build_taxpayer_card(taxpayer, yearly_rows, year))
    taxpayers.sort(key=lambda item: (status_group_rank(item.get("durumGrubu", "")), item["gosterimAdi"].casefold(), -item["yil"]))
    transition_firms = {row["vkn"] for row in rows if row.get("gecisRolu") or row.get("ozelDurumTipi")}
    ready_years = sorted({row["yil"] for row in rows if row.get("yil")}, reverse=True)
    return {
        "profil": "Klasör Taraması",
        "arsivKlasoru": str(summary.root_path),
        "sonTarama": summary.scan_finished_at.replace("T", " "),
        "hazirYillar": ready_years,
        "toplamFirma": len(summary.taxpayers),
        "gecisFirmaSayisi": len(transition_firms),
        "toplamDonem": len(summary.period_buckets),
        "eksikDonem": len([row for row in rows if row["durum"] != "Tam"]),
        "kritikHata": risk_counter["CRITICAL"] + risk_counter["HIGH"],
        "genelSkor": 100 if not rows else max(0, 100 - sum(risk_penalty(row["risk"]) for row in rows)),
        "riskDagilimi": {
            "OK": risk_counter["OK"],
            "LOW": risk_counter["LOW"],
            "MEDIUM": risk_counter["MEDIUM"],
            "HIGH": risk_counter["HIGH"],
            "CRITICAL": risk_counter["CRITICAL"],
        },
        "sonOzet": [
            {"id": row["id"], "firma": row["firma"], "donem": f"{row['yil']}/{row['ay']}", "sorun": row["ozet"][0], "risk": row["risk"]}
            for row in rows[:10]
        ],
        "ilerleme": {
            "asama": "Tarama tamamlandı",
            "yuzde": 100,
            "islenenDosya": summary.scanned_files,
            "toplamDosya": summary.total_files,
            "bulunanMukellef": len(summary.taxpayers),
            "hataSayisi": len([log for log in summary.logs if log.level == "ERROR"]),
        },
        "mukellefKartlari": taxpayers,
        "islemGunlugu": [
            {"saat": entry.timestamp.replace("T", " "), "seviye": entry.level, "mesaj": f"{entry.message} {entry.context}".strip()}
            for entry in summary.logs[-20:]
        ],
    }


def merge_result_with_cache(
    primary_result: dict[str, Any],
    cached_result: dict[str, Any] | None,
    *,
    excluded_years: set[int] | None = None,
) -> dict[str, Any]:
    if not cached_result:
        return primary_result
    excluded_years = excluded_years or set()
    primary_rows = [row for row in primary_result.get("donemler", []) if isinstance(row, dict)]
    cached_rows = [
        row for row in cached_result.get("donemler", [])
        if isinstance(row, dict) and int(row.get("yil", 0) or 0) not in excluded_years
    ]
    merged_rows_map: dict[str, dict[str, Any]] = {}
    for row in cached_rows:
        merged_rows_map[str(row.get("id", ""))] = row
    for row in primary_rows:
        merged_rows_map[str(row.get("id", ""))] = row
    merged_rows = sorted(
        merged_rows_map.values(),
        key=lambda item: (str(item.get("firma", "")).casefold(), int(item.get("yil", 0) or 0), str(item.get("ay", ""))),
    )

    primary_cards = [card for card in primary_result.get("dashboard", {}).get("mukellefKartlari", []) if isinstance(card, dict)]
    cached_cards = [
        card for card in cached_result.get("dashboard", {}).get("mukellefKartlari", [])
        if isinstance(card, dict) and int(card.get("yil", 0) or 0) not in excluded_years
    ]
    merged_cards_map: dict[str, dict[str, Any]] = {}
    for card in cached_cards:
        merged_cards_map[str(card.get("id", ""))] = card
    for card in primary_cards:
        merged_cards_map[str(card.get("id", ""))] = card
    merged_cards = sorted(
        merged_cards_map.values(),
        key=lambda item: (status_group_rank(str(item.get("durumGrubu", ""))), str(item.get("gosterimAdi", "")).casefold(), -int(item.get("yil", 0) or 0)),
    )
    primary_ready_years = extract_ready_years_from_result(primary_result)
    cached_ready_years = {
        year for year in extract_ready_years_from_result(cached_result)
        if year not in excluded_years
    }
    merged_ready_years = sorted(primary_ready_years | cached_ready_years, reverse=True)

    dashboard = rebuild_dashboard_snapshot(
        primary_result.get("dashboard", empty_dashboard()),
        merged_rows,
        merged_cards,
        merged_ready_years,
    )
    return {
        "dashboard": dashboard,
        "donemler": merged_rows,
        "teknik_ozet": primary_result.get("teknik_ozet", {}),
        "sistemDurumu": primary_result.get("sistemDurumu"),
    }


def rebuild_dashboard_snapshot(
    base_dashboard: dict[str, Any],
    rows: list[dict[str, Any]],
    cards: list[dict[str, Any]],
    ready_years: list[int] | None = None,
) -> dict[str, Any]:
    risk_counter = Counter(str(row.get("risk", "OK")) for row in rows)
    unique_firms = {(str(row.get("firma", "")), str(row.get("vkn", ""))) for row in rows}
    transition_firms = {str(row.get("vkn", "")) for row in rows if row.get("gecisRolu") or row.get("ozelDurumTipi")}
    dashboard = dict(base_dashboard)
    dashboard["toplamFirma"] = len(unique_firms)
    dashboard["toplamDonem"] = len(rows)
    dashboard["gecisFirmaSayisi"] = len(transition_firms)
    dashboard["eksikDonem"] = len([row for row in rows if row.get("durum") != "Tam"])
    dashboard["kritikHata"] = risk_counter["CRITICAL"] + risk_counter["HIGH"]
    dashboard["genelSkor"] = 100 if not rows else max(0, 100 - sum(risk_penalty(str(row.get("risk", "OK"))) for row in rows))
    dashboard["riskDagilimi"] = {
        "OK": risk_counter["OK"],
        "LOW": risk_counter["LOW"],
        "MEDIUM": risk_counter["MEDIUM"],
        "HIGH": risk_counter["HIGH"],
        "CRITICAL": risk_counter["CRITICAL"],
    }
    dashboard["sonOzet"] = [
        {"id": row["id"], "firma": row["firma"], "donem": f"{row['yil']}/{row['ay']}", "sorun": row["ozet"][0], "risk": row["risk"]}
        for row in rows[:10]
    ]
    derived_ready_years = {
        int(row.get("yil", 0) or 0)
        for row in rows
        if int(row.get("yil", 0) or 0) >= 2000
    }
    dashboard["hazirYillar"] = sorted(set(ready_years or derived_ready_years), reverse=True)
    dashboard["mukellefKartlari"] = cards
    return dashboard


def build_taxpayer_card(taxpayer: TaxpayerSummary, taxpayer_rows: list[dict[str, Any]], year: int) -> dict[str, Any]:
    accountant_name = taxpayer.accountant_name or next((row["maliMusavir"] for row in taxpayer_rows if row.get("maliMusavir")), "")
    row_map = {int(row["ay"]): row for row in taxpayer_rows}
    months = []
    for month in range(1, 13):
        row = row_map.get(month)
        months.append(
            {
                "ayNo": f"{month:02d}",
                "ayAd": month_name(month),
                "durumRengi": month_color(row["risk"], row.get("gecisRolu", "")) if row else "gray",
                "kisaDurum": month_short_status(row) if row else "Yok",
                "ozet": row["ozet"][0] if row else "Bu ay için kayıt bulunmadı.",
                "risk": row["risk"] if row else "LOW",
                "donemId": row["id"] if row else "",
                "envanterVar": bool(row.get("envanterVar")) if row else False,
                "gibEnvanterVar": bool(row.get("gibEnvanterVar")) if row else False,
                "gecisRolu": row.get("gecisRolu", "") if row else "",
                "gecisEtiketi": row.get("gecisEtiketi", "") if row else "",
                "ozelDurumTipi": row.get("ozelDurumTipi", "") if row else "",
                "araDonemAtlamasi": bool(row.get("araDonemAtlamasi")) if row else False,
                "kullaniciIstisnasi": bool(row.get("kullaniciIstisnasi")) if row else False,
            }
        )

    unresolved_rows = [row for row in taxpayer_rows if not is_user_approved_gap(row)]
    risk = highest_risk([row["risk"] for row in unresolved_rows]) if unresolved_rows else "OK"
    transition_rows = [row for row in taxpayer_rows if row.get("gecisRolu") or row.get("ozelDurumTipi")]
    durum_grubu = taxpayer_status_group(taxpayer_rows)
    return {
        "id": f"{taxpayer.taxpayer_key}-{year}",
        "firmaAnahtari": taxpayer.vkn_or_tckn or taxpayer.taxpayer_key,
        "gosterimAdi": taxpayer.display_name,
        "resmiUnvan": taxpayer.official_name or taxpayer.display_name,
        "vknTckn": taxpayer.vkn_or_tckn,
        "yil": year,
        "profil": "Klasör Taraması",
        "aramaMetni": taxpayer.search_text,
        "maliMusavir": accountant_name,
        "genelRisk": risk,
        "eksikDonemSayisi": len([row for row in taxpayer_rows if row["durum"] != "Tam" and not is_user_approved_gap(row)]),
        "kritikSorunSayisi": len([row for row in taxpayer_rows if row["risk"] in {"HIGH", "CRITICAL"} and not is_user_approved_gap(row)]),
        "onayliIstisnaSayisi": len([row for row in taxpayer_rows if is_user_approved_gap(row)]),
        "envanterVar": any(bool(row.get("envanterVar")) for row in taxpayer_rows),
        "gibEnvanterVar": any(bool(row.get("gibEnvanterVar")) for row in taxpayer_rows),
        "envanterDonemSayisi": len([row for row in taxpayer_rows if bool(row.get("envanterVar"))]),
        "sonTarama": taxpayer_rows[-1]["gonderimTarihi"] if taxpayer_rows else "",
        "donemler": months,
        "klasorYolu": taxpayer.root_paths[0] if taxpayer.root_paths else "",
        "ozelDurum": taxpayer.special_case_label or (transition_rows[0]["gecisEtiketi"] if transition_rows else ""),
        "ozelDurumTipi": taxpayer.special_case_kind,
        "gecisFirma": bool(transition_rows),
        "durumGrubu": durum_grubu,
    }


def apply_demo_access_to_result(base_dir: Path, result: dict[str, Any]) -> dict[str, Any]:
    license_state = evaluate_license(base_dir)
    dashboard = dict(result.get("dashboard", empty_dashboard()))
    cards = [dict(card) for card in dashboard.get("mukellefKartlari", []) if isinstance(card, dict)]
    rows = [dict(row) for row in result.get("donemler", []) if isinstance(row, dict)]
    system_status = dict(result.get("sistemDurumu", {}) or {})

    if license_state.get("valid"):
        dashboard["mukellefKartlari"] = [mark_card_unlocked(card) for card in cards]
        result["dashboard"] = dashboard
        result["donemler"] = [mark_row_unlocked(row) for row in rows]
        if system_status:
            system_status["lisans"] = license_state
            result["sistemDurumu"] = system_status
        return result

    ordered_firms: list[tuple[str, str]] = []
    seen_keys: set[str] = set()
    for card in cards:
        firm_key = extract_firm_key(card)
        if not firm_key or firm_key in seen_keys:
            continue
        seen_keys.add(firm_key)
        ordered_firms.append((firm_key, str(card.get("gosterimAdi", "")).strip() or firm_key))

    demo_state = register_demo_firms(base_dir, str(license_state.get("device_code") or ""), ordered_firms)
    unlocked_keys = set(str(key) for key in demo_state.get("registered_keys", []))

    locked_firms: set[str] = set()
    unlocked_cards = []
    for card in cards:
        firm_key = extract_firm_key(card)
        if firm_key and firm_key in unlocked_keys:
            unlocked_cards.append(mark_card_unlocked(card))
            continue
        if firm_key:
            locked_firms.add(firm_key)
        unlocked_cards.append(mask_card_for_demo(card))

    unlocked_rows = []
    for row in rows:
        firm_key = extract_firm_key(row)
        if firm_key and firm_key in unlocked_keys:
            unlocked_rows.append(mark_row_unlocked(row))
            continue
        unlocked_rows.append(mask_row_for_demo(row))

    license_state["demo"] = demo_state
    dashboard["mukellefKartlari"] = unlocked_cards
    dashboard["demoKilitliFirma"] = len(locked_firms)
    dashboard["demoAcikFirma"] = int(demo_state.get("used_count", 0) or 0)
    result["dashboard"] = dashboard
    result["donemler"] = unlocked_rows
    if system_status:
        system_status["lisans"] = license_state
        result["sistemDurumu"] = system_status
    return result


def extract_firm_key(item: dict[str, Any]) -> str:
    return str(
        item.get("firmaAnahtari")
        or item.get("vkn")
        or item.get("vknTckn")
        or item.get("id")
        or ""
    ).strip().upper()


def demo_lock_message() -> str:
    return "Demo Modunda sadece 4 firma tam acilir. Tum detaylar icin Pro Modu etkinlestirin."


def mark_row_unlocked(row: dict[str, Any]) -> dict[str, Any]:
    row["demoLocked"] = False
    row["demoMessage"] = ""
    return row


def mask_row_for_demo(row: dict[str, Any]) -> dict[str, Any]:
    row["demoLocked"] = True
    row["demoMessage"] = demo_lock_message()
    row["klasorYolu"] = ""
    row["gonderimTarihi"] = ""
    row["imzaTarihi"] = ""
    row["gibOnayTarihi"] = ""
    row["kontroller"] = []
    row["dosyalar"] = []
    row["topluPaketler"] = []
    row["yardimciDosyalar"] = []
    row["sorunlar"] = []
    row["loglar"] = []
    row["aksiyonlar"] = ["Pro Modu etkinlestirin."]
    row["ozet"] = [row.get("ozelDurum") or row.get("gecisEtiketi") or "Detaylar kilitli."]
    return row


def mark_card_unlocked(card: dict[str, Any]) -> dict[str, Any]:
    card["demoLocked"] = False
    card["demoMessage"] = ""
    card["donemler"] = [mark_month_unlocked(dict(month)) for month in card.get("donemler", []) if isinstance(month, dict)]
    return card


def mask_card_for_demo(card: dict[str, Any]) -> dict[str, Any]:
    card["demoLocked"] = True
    card["demoMessage"] = demo_lock_message()
    card["klasorYolu"] = ""
    card["donemler"] = [mask_month_for_demo(dict(month)) for month in card.get("donemler", []) if isinstance(month, dict)]
    return card


def mark_month_unlocked(month: dict[str, Any]) -> dict[str, Any]:
    month["demoLocked"] = False
    month["demoMessage"] = ""
    return month


def mask_month_for_demo(month: dict[str, Any]) -> dict[str, Any]:
    month["demoLocked"] = True
    month["demoMessage"] = demo_lock_message()
    if month.get("donemId"):
        month["donemId"] = ""
        month["ozet"] = "Detaylar Pro Modu ile acilir."
    return month


def taxpayer_status_group(taxpayer_rows: list[dict[str, Any]]) -> str:
    if any(row["risk"] in {"HIGH", "CRITICAL"} and not is_user_approved_gap(row) for row in taxpayer_rows):
        return "red"
    if any((row.get("gecisRolu") or row.get("ozelDurumTipi") or row["risk"] in {"LOW", "MEDIUM"}) and not is_user_approved_gap(row) for row in taxpayer_rows):
        return "yellow"
    return "green"


def status_group_rank(value: str) -> int:
    return {"red": 0, "yellow": 1, "green": 2}.get(value, 3)


def get_period_overrides_path(base_dir: Path) -> Path:
    return base_dir / PERIOD_OVERRIDE_FILENAME


def load_period_overrides(base_dir: Path) -> dict[str, dict[str, str]]:
    target = get_period_overrides_path(base_dir)
    if not target.exists():
        return {}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    result: dict[str, dict[str, str]] = {}
    for key, value in data.items():
        if not isinstance(value, dict):
            continue
        if not bool(value.get("approved")):
            continue
        result[str(key)] = {
            "approved": "true",
            "note": str(value.get("note", "")).strip(),
            "updated_at": str(value.get("updated_at", "")).strip(),
        }
    return result


def save_period_override(base_dir: Path, period_id: str, approved: bool, note: str = "") -> Path:
    target = get_period_overrides_path(base_dir)
    data: dict[str, Any] = {}
    if target.exists():
        try:
            loaded = json.loads(target.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except Exception:
            data = {}
    if approved:
        data[period_id] = {
            "approved": True,
            "note": note.strip(),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
    else:
        data.pop(period_id, None)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def apply_gap_and_override_rules(rows: list[dict[str, Any]], base_dir: Path) -> list[dict[str, Any]]:
    enriched = list(rows)
    groups: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault((row["vkn"], int(row["yil"])), []).append(row)

    for group_rows in groups.values():
        month_map = {int(row["ay"]): row for row in group_rows if str(row.get("ay", "")).isdigit()}
        if len(month_map) < 2:
            continue
        present_months = sorted(month_map)
        first_month = present_months[0]
        last_month = present_months[-1]
        for month in range(first_month + 1, last_month):
            if month in month_map:
                continue
            prev_row = month_map.get(month - 1)
            next_row = month_map.get(month + 1)
            special_transition = any(
                row and (row.get("ozelDurumTipi") or row.get("gecisRolu"))
                for row in (prev_row, next_row)
            )
            enriched.append(build_gap_row(group_rows[0], month, special_transition))

    overrides = load_period_overrides(base_dir)
    for row in enriched:
        row["kullaniciIstisnasi"] = False
        row["kullaniciIstisnaNotu"] = ""
        row["kullaniciIstisnaTarihi"] = ""
        override = overrides.get(str(row["id"]))
        if override:
            row["kullaniciIstisnasi"] = True
            row["kullaniciIstisnaNotu"] = override.get("note", "")
            row["kullaniciIstisnaTarihi"] = override.get("updated_at", "")
    return sorted(enriched, key=lambda item: (item["firma"].casefold(), item["yil"], item["ay"]))


def build_gap_row(seed_row: dict[str, Any], month: int, special_transition: bool) -> dict[str, Any]:
    month_label = f"{month:02d}"
    summary = (
        ["Bu ara donem gorunmuyor. Gecis veya ozel durum nedeniyle kontrol edin."]
        if special_transition
        else ["Donem atlamasi var. Onceki donem mevcut, sonraki donem de devam ediyor."]
    )
    action = (
        ["Gecis, tasfiye veya kurulus kaydini kontrol edin."]
        if special_transition
        else ["Eksik ara donemi kaynak arsivden veya berat indirme adimindan tamamlayin."]
    )
    risk = "MEDIUM" if special_transition else "HIGH"
    issue_title = "Ara donem kontrolu" if special_transition else "Donem atlamasi"
    return {
        "id": f"GAP-{seed_row['vkn']}-{seed_row['yil']}-{month_label}",
        "firma": seed_row["firma"],
        "resmiUnvan": seed_row["resmiUnvan"],
        "vkn": seed_row["vkn"],
        "yil": seed_row["yil"],
        "ay": month_label,
        "profil": seed_row["profil"],
        "aramaMetni": seed_row.get("aramaMetni", ""),
        "maliMusavir": seed_row.get("maliMusavir", ""),
        "gonderimTarihi": "",
        "imzaTarihi": "",
        "gibOnayTarihi": "",
        "donemBaslangic": "",
        "donemBitis": "",
        "klasorYolu": seed_row.get("klasorYolu", ""),
        "kontroller": [],
        "yevmiye": "Eksik",
        "kebir": "Eksik",
        "yevmiyeBerat": "Eksik",
        "kebirBerat": "Eksik",
        "gibOnayliBerat": "Eksik",
        "defterRaporu": "Eksik",
        "durum": "İncelenmeli" if special_transition else "Bozuk",
        "risk": risk,
        "ozet": summary,
        "aksiyonlar": action,
        "ozelDurumTipi": "",
        "ozelDurum": "Gecis nedeniyle normal olabilir" if special_transition else "Ara donem eksik",
        "dosyalar": [],
        "topluPaketler": [],
        "yardimciDosyalar": [],
        "sorunlar": [
            {
                "id": f"GAP-ISSUE-{seed_row['vkn']}-{seed_row['yil']}-{month_label}",
                "risk": risk,
                "baslik": issue_title,
                "aciklama": summary[0],
                "ilgiliDosya": f"{seed_row['yil']}/{month_label}",
                "onerilenIslem": action[0],
            }
        ],
        "loglar": [],
        "gecisTipi": "gecis-kontrol" if special_transition else "",
        "gecisEtiketi": "Gecis Kontrolu" if special_transition else "",
        "gecisRolu": "transition" if special_transition else "",
        "gecisTarihi": "",
        "arsivKokleri": seed_row.get("arsivKokleri", []),
        "araDonemAtlamasi": True,
    }


def is_user_approved_gap(row: dict[str, Any]) -> bool:
    return bool(row.get("araDonemAtlamasi") and row.get("kullaniciIstisnasi"))


def filter_export_rows(rows: list[dict[str, Any]], selected_year: str | None) -> list[dict[str, Any]]:
    filtered = [row for row in rows if not bool(row.get("demoLocked"))]
    if not selected_year or selected_year == "Tüm Yıllar":
        return filtered
    return [row for row in filtered if str(row.get("yil", "")) == str(selected_year)]


def build_accountant_fallback_map(records: list[FileRecord]) -> dict[str, str]:
    accountants_by_vkn: dict[str, list[str]] = {}
    for record in records:
        accountant = record.xml_metadata.accountant_name.strip()
        if not accountant:
            continue
        vkn = record.canonical_vkn or record.vkn_from_path or record.xml_metadata.identifier.strip()
        if not vkn:
            continue
        accountants_by_vkn.setdefault(vkn, []).append(accountant)
    return {
        vkn: Counter(values).most_common(1)[0][0]
        for vkn, values in accountants_by_vkn.items()
        if values
    }


def flatten_files(period: PeriodBucket) -> list[dict[str, Any]]:
    items = []
    for document_type, files in period.documents.items():
        for index, file in enumerate(dedupe_equivalent_files(files), start=1):
            items.append(
                {
                    "id": f"{period.company_key}-{period.period_year}-{period.period_month}-{document_type.value}-{index}",
                    "etiket": document_type_label(document_type),
                    "dosyaAdi": file.file_name,
                    "yol": str(file.file_path),
                    "boyut": f"{round(file.size / 1024, 1)} KB",
                    "hash": file.sha256[:12],
                    "kaynak": file.source_type.value.upper(),
                    "belgeTipi": document_type.value,
                    "olusturmaTarihi": file.xml_metadata.creation_date,
                    "imzaTarihi": file.xml_metadata.signing_time,
                    "durum": file_status(file, files),
                }
            )
    return items[:24]


def find_related_records(records: list[FileRecord], period: PeriodBucket) -> list[FileRecord]:
    related: list[FileRecord] = []
    for record in records:
        same_period = record.period_year == period.period_year and record.period_month == period.period_month
        same_taxpayer = record.canonical_taxpayer_key == period.company_key or record.canonical_vkn == period.company_key or record.vkn_from_path == period.company_key
        if same_period and same_taxpayer:
            related.append(record)
    return related


def flatten_supporting_files(records: list[FileRecord], document_types: set[DocumentType]) -> list[dict[str, Any]]:
    items = []
    matching = [record for record in records if record.document_type in document_types and not record.is_system_artifact]
    for index, file in enumerate(matching, start=1):
        items.append(
            {
                "id": f"support-{file.document_type.value}-{index}",
                "etiket": document_type_label(file.document_type),
                "dosyaAdi": file.file_name,
                "yol": str(file.file_path),
                "boyut": f"{round(file.size / 1024, 1)} KB",
                "kaynak": file.source_type.value.upper(),
            }
        )
    return items[:24]


def build_control_rows(period: PeriodBucket, diagnostics: dict[str, Any]) -> list[dict[str, Any]]:
    controls: list[dict[str, Any]] = []
    entries = [
        (DocumentType.JOURNAL_BOOK, "Yevmiye Defteri", "Y / Yevmiye XML ve ZIP seti"),
        (DocumentType.LEDGER_BOOK, "Kebir Defteri", "K / Kebir XML ve ZIP seti"),
        (DocumentType.JOURNAL_BERAT, "Yevmiye Beratı", "YB berat dosyaları"),
        (DocumentType.LEDGER_BERAT, "Kebir Beratı", "KB berat dosyaları"),
        (DocumentType.GIB_APPROVED_JOURNAL_BERAT, "GİB Yevmiye Beratı", "GİB onaylı YB XML ve ZIP seti"),
        (DocumentType.GIB_APPROVED_LEDGER_BERAT, "GİB Kebir Beratı", "GİB onaylı KB XML ve ZIP seti"),
        (DocumentType.DEFTER_RAPORU, "Defter Raporu", "DR XML ve ZIP seti"),
    ]
    if any(
        period.documents.get(document_type)
        for document_type in (
            DocumentType.INVENTORY_BOOK,
            DocumentType.INVENTORY_BERAT,
            DocumentType.GIB_APPROVED_INVENTORY_BERAT,
        )
    ):
        entries.extend(
            [
                (DocumentType.INVENTORY_BOOK, "Envanter Defteri", "E / Envanter XML ve ZIP seti"),
                (DocumentType.INVENTORY_BERAT, "Envanter Beratı", "EB berat dosyaları"),
                (DocumentType.GIB_APPROVED_INVENTORY_BERAT, "GİB Envanter Beratı", "GİB onaylı EB XML ve ZIP seti"),
            ]
        )
    for document_type, label, description in entries:
        files = dedupe_equivalent_files(period.documents.get(document_type, []))
        xml_count = len([file for file in files if file.source_type.value == "xml"])
        zip_count = len([file for file in files if file.source_type.value == "zip"])
        controls.append(
            {
                "id": document_type.value,
                "etiket": label,
                "aciklama": description,
                "durum": diagnostics["statuses"].get(document_type.value) or diagnostics["gib_status"],
                "xmlAdet": xml_count,
                "zipAdet": zip_count,
                "beklenenAdet": 2,
                "dosyaYollari": [str(file.file_path) for file in files],
            }
        )
    return controls


def analyze_period(period: PeriodBucket, related_records: list[FileRecord], transition_state: dict[str, Any] | None = None) -> dict[str, Any]:
    allow_transition_duplicates = bool(transition_state and transition_state.get("allow_transition_duplicates"))
    inventory_types = (
        DocumentType.INVENTORY_BOOK,
        DocumentType.INVENTORY_BERAT,
        DocumentType.GIB_APPROVED_INVENTORY_BERAT,
    )
    statuses = {
        document_type.value: evaluate_document_status(period.documents.get(document_type, []), allow_transition_duplicates=allow_transition_duplicates)
        for document_type in (
            DocumentType.JOURNAL_BOOK,
            DocumentType.LEDGER_BOOK,
            DocumentType.INVENTORY_BOOK,
            DocumentType.JOURNAL_BERAT,
            DocumentType.LEDGER_BERAT,
            DocumentType.INVENTORY_BERAT,
            DocumentType.GIB_APPROVED_JOURNAL_BERAT,
            DocumentType.GIB_APPROVED_LEDGER_BERAT,
            DocumentType.GIB_APPROVED_INVENTORY_BERAT,
            DocumentType.DEFTER_RAPORU,
        )
    }
    gib_statuses = [statuses[DocumentType.GIB_APPROVED_JOURNAL_BERAT.value], statuses[DocumentType.GIB_APPROVED_LEDGER_BERAT.value]]
    gib_status = "Tam" if all(status == "Tam" for status in gib_statuses) else highest_status(gib_statuses)
    inventory_present = any(period.documents.get(document_type) for document_type in inventory_types)

    missing = [
        document_type.value
        for document_type in (
            DocumentType.JOURNAL_BOOK,
            DocumentType.LEDGER_BOOK,
            DocumentType.JOURNAL_BERAT,
            DocumentType.LEDGER_BERAT,
            DocumentType.GIB_APPROVED_JOURNAL_BERAT,
            DocumentType.GIB_APPROVED_LEDGER_BERAT,
        )
        if not period.documents.get(document_type)
    ]
    inventory_missing = [
        document_type.value
        for document_type in inventory_types
        if inventory_present and not period.documents.get(document_type)
    ]
    duplicates = [
        document_type.value
        for document_type, files in period.documents.items()
        if (
            has_duplicate(dedupe_equivalent_files(files), allow_transition_duplicates=allow_transition_duplicates)
            and not (allow_transition_duplicates and document_type in {
                DocumentType.JOURNAL_BOOK,
                DocumentType.LEDGER_BOOK,
                DocumentType.INVENTORY_BOOK,
                DocumentType.JOURNAL_BERAT,
                DocumentType.LEDGER_BERAT,
                DocumentType.INVENTORY_BERAT,
                DocumentType.GIB_APPROVED_JOURNAL_BERAT,
                DocumentType.GIB_APPROVED_LEDGER_BERAT,
                DocumentType.GIB_APPROVED_INVENTORY_BERAT,
                DocumentType.DEFTER_RAPORU,
            })
        )
    ]
    parse_errors = [file.file_name for files in period.documents.values() for file in files if file.parse_status != "ok"]
    package_warnings = validate_aggregate_packages(related_records)

    score = 0
    summary: list[str] = []
    actions: list[str] = []

    if missing:
        summary.extend([f"{friendly_missing_name(item)} eksik." for item in missing])
        actions.append("Eksik belge setlerini kaynak sistem veya arşivden tamamlayın.")
        score += 5 if any(item in {"JOURNAL_BOOK", "LEDGER_BOOK"} for item in missing) else 0
        score += 4 if any(item.startswith("GIB_APPROVED") for item in missing) else 0
        score += max(len(missing) - 2, 0)
    if inventory_missing:
        summary.extend([f"{friendly_missing_name(item)} eksik." for item in inventory_missing])
        actions.append("Envanter dosyaları varsa XML, berat ve GİB onaylı suret setini birlikte kontrol edin.")
        score += 2 if any(item == "INVENTORY_BOOK" for item in inventory_missing) else 0
        score += 2 if any(item == "INVENTORY_BERAT" for item in inventory_missing) else 0
        score += 3 if any(item == "GIB_APPROVED_INVENTORY_BERAT" for item in inventory_missing) else 0
    if duplicates:
        summary.extend([f"{friendly_missing_name(item)} için tekrar dosya var." for item in duplicates])
        actions.append("Tekrar dosyaları temizleyip tek geçerli set bırakın.")
        score += 2 * len(duplicates)
    if parse_errors:
        summary.append(f"{len(parse_errors)} dosyada okuma veya ZIP içerik sorunu var.")
        actions.append("Bozuk XML/ZIP dosyalarını yeniden üretin veya yeniden indirin.")
        score += 3 + len(parse_errors)
    if statuses["DEFTER_RAPORU"] == "Eksik":
        summary.append("Defter raporu bulunamadı.")
        actions.append("Defter raporu dosyasını da arşive ekleyin.")
    if package_warnings:
        summary.extend([warning["message"] for warning in package_warnings])
        actions.append("Toplu paket içeriklerini çekirdek dosya setiyle karşılaştırın.")
    if transition_state and transition_state.get("summary"):
        summary.extend(transition_state["summary"])
        actions.extend(transition_state.get("actions", []))
        if transition_state.get("risk") == "LOW":
            score = max(score, 1)
        elif transition_state.get("risk") == "MEDIUM":
            score = max(score, 4)
        elif transition_state.get("risk") == "HIGH":
            score = max(score, 8)
        elif transition_state.get("risk") == "CRITICAL":
            score = max(score, 12)

    if score == 0:
        risk = "OK"
        overall_status = "Tam"
    elif score <= 2:
        risk = "LOW"
        overall_status = "İncelenmeli"
    elif score <= 5:
        risk = "MEDIUM"
        overall_status = "İncelenmeli"
    elif score <= 9:
        risk = "HIGH"
        overall_status = "Bozuk" if parse_errors else "İncelenmeli"
    else:
        risk = "CRITICAL"
        overall_status = "Bozuk" if parse_errors or any(item in {"JOURNAL_BOOK", "LEDGER_BOOK"} for item in missing) else "İncelenmeli"

    if not summary:
        summary = ["GİB onaylı berat seti ve temel dosyalar tamam."]
    if not actions:
        actions = ["Ek işlem gerekmiyor."]

    return {
        "statuses": statuses,
        "gib_status": gib_status,
        "inventory_present": inventory_present,
        "missing": missing,
        "inventory_missing": inventory_missing,
        "duplicates": duplicates,
        "parse_errors": parse_errors,
        "package_warnings": package_warnings,
        "risk": risk,
        "overall_status": overall_status,
        "summary": summary,
        "actions": actions,
        "transition": transition_state or {},
    }


def validate_aggregate_packages(records: list[FileRecord]) -> list[dict[str, str]]:
    expected_members = {
        "YEVMIYELER.ZIP": {DocumentType.JOURNAL_BOOK},
        "KEBIRLER.ZIP": {DocumentType.LEDGER_BOOK},
        "BERATLAR.ZIP": {DocumentType.JOURNAL_BERAT, DocumentType.LEDGER_BERAT, DocumentType.DEFTER_RAPORU},
    }
    warnings: list[dict[str, str]] = []
    for record in records:
        if record.document_type is not DocumentType.AGGREGATE_PACKAGE:
            continue
        expected = expected_members.get(record.file_name.upper())
        if not expected:
            continue
        actual = {
            classify_document(Path(entry_name).name)
            for entry_name in record.package_entries
            if Path(entry_name).suffix.lower() == ".xml"
        }
        missing_types = expected - actual
        if missing_types:
            missing_labels = ", ".join(
                friendly_missing_name(document_type_name(item))
                for item in sorted(missing_types, key=document_type_name)
            )
            warnings.append(
                {
                    "file_name": record.file_name,
                    "message": f"{record.file_name} içinde {missing_labels} görünmüyor.",
                }
            )
    return warnings


def document_type_name(value: Any) -> str:
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def evaluate_document_status(files: list[FileRecord], *, allow_transition_duplicates: bool = False) -> str:
    normalized_files = dedupe_equivalent_files(files)
    if not normalized_files:
        return "Eksik"
    if has_duplicate(normalized_files, allow_transition_duplicates=allow_transition_duplicates):
        return "Tekrar"
    if any(file.parse_status != "ok" for file in normalized_files):
        return "Bozuk"
    return "Tam"


def has_duplicate(files: list[FileRecord], *, allow_transition_duplicates: bool = False) -> bool:
    if allow_transition_duplicates:
        root_buckets: dict[str, list[FileRecord]] = {}
        for file in files:
            root_info = extract_archive_root_info(file)
            root_key = root_info["label"] if root_info else "NO_ROOT"
            root_buckets.setdefault(root_key, []).append(file)
        for root_files in root_buckets.values():
            sequence_counter = Counter((file.source_type.value, sequence_token(file.file_name)) for file in root_files)
            if any(count > 1 for count in sequence_counter.values()):
                return True
        return False
    sequence_counter = Counter((file.source_type.value, sequence_token(file.file_name)) for file in files)
    return any(count > 1 for count in sequence_counter.values())


def dedupe_equivalent_files(files: list[FileRecord]) -> list[FileRecord]:
    unique: dict[tuple[str, str, str], FileRecord] = {}
    for file in files:
        key = (file.file_name.upper(), file.source_type.value, file.sha256)
        unique.setdefault(key, file)
    return list(unique.values())


def sequence_token(file_name: str) -> str:
    stem = Path(file_name).stem
    if "-" not in stem:
        return stem.upper()
    return stem.rsplit("-", 1)[-1].upper()


def highest_status(statuses: list[str]) -> str:
    priority = ["Tam", "İncelenmeli", "Eksik", "Tekrar", "Bozuk"]
    return max(statuses, key=lambda item: priority.index(item))


def collect_period_metadata(period: PeriodBucket) -> dict[str, str]:
    files = [file for items in period.documents.values() for file in items]
    xml_files = [file for file in files if file.xml_metadata]
    gib_files = [
        file
        for document_type in (
            DocumentType.GIB_APPROVED_JOURNAL_BERAT,
            DocumentType.GIB_APPROVED_LEDGER_BERAT,
            DocumentType.GIB_APPROVED_INVENTORY_BERAT,
        )
        for file in period.documents.get(document_type, [])
    ]

    def first_value(attribute: str) -> str:
        for file in xml_files:
            value = getattr(file.xml_metadata, attribute, "")
            if value:
                return value
        return ""

    def first_gib_value(attribute: str) -> str:
        for file in gib_files:
            value = getattr(file.xml_metadata, attribute, "")
            if value:
                return value
        return ""

    return {
        "accountant": first_value("accountant_name"),
        "creation_date": first_value("creation_date"),
        "signing_time": first_value("signing_time"),
        "gib_approval_date": first_gib_value("creation_date"),
        "period_start": first_value("period_start"),
        "period_end": first_value("period_end"),
        "folder_path": str(files[0].file_path.parent) if files else "",
    }


def build_issue_rows(period: PeriodBucket, diagnostics: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    base_id = f"{period.company_key}-{period.period_year}-{period.period_month}"
    transition = diagnostics.get("transition") or {}
    if transition.get("role") in {"transition", "missing_post", "pre", "post"} and transition.get("label"):
        risk = transition.get("risk") or ("LOW" if transition.get("role") == "transition" else "MEDIUM")
        transition_summary = transition.get("summary") or [f"{transition['label']} durumu algılandı."]
        description = transition_summary[0]
        issues.append(
            {
                "id": f"{base_id}-transition",
                "risk": risk,
                "baslik": transition["label"],
                "aciklama": description,
                "ilgiliDosya": transition.get("role", ""),
                "onerilenIslem": (transition.get("actions") or ["Geçiş klasörlerini birlikte kontrol edin."])[0],
            }
        )
    all_missing = list(diagnostics.get("missing", [])) + list(diagnostics.get("inventory_missing", []))
    for index, missing_item in enumerate(all_missing, start=1):
        issues.append(
            {
                "id": f"{base_id}-missing-{index}",
                "risk": diagnostics["risk"],
                "baslik": "Eksik belge seti",
                "aciklama": f"{friendly_missing_name(missing_item)} bu dönem için bulunamadı.",
                "ilgiliDosya": missing_item,
                "onerilenIslem": "Kaynak klasörü, berat indirme adımı ve arşiv eşleşmesini kontrol edin.",
            }
        )
    for index, duplicate_item in enumerate(diagnostics["duplicates"], start=1):
        issues.append(
            {
                "id": f"{base_id}-duplicate-{index}",
                "risk": "MEDIUM" if diagnostics["risk"] == "LOW" else diagnostics["risk"],
                "baslik": "Tekrar dosya",
                "aciklama": f"{friendly_missing_name(duplicate_item)} için birden fazla dosya bulundu.",
                "ilgiliDosya": duplicate_item,
                "onerilenIslem": "Geçerli dosyayı bırakıp tekrar kayıtları ayırın.",
            }
        )
    for index, parse_item in enumerate(diagnostics["parse_errors"], start=1):
        issues.append(
            {
                "id": f"{base_id}-parse-{index}",
                "risk": "HIGH",
                "baslik": "Bozuk dosya",
                "aciklama": f"{parse_item} okunurken hata veya beklenmeyen ZIP içeriği algılandı.",
                "ilgiliDosya": parse_item,
                "onerilenIslem": "Dosyayı yeniden üretin veya GİB/onaylı kaynaktan tekrar alın.",
            }
        )
    for index, warning in enumerate(diagnostics["package_warnings"], start=1):
        issues.append(
            {
                "id": f"{base_id}-package-{index}",
                "risk": "LOW",
                "baslik": "Toplu paket içeriği eksik",
                "aciklama": warning["message"],
                "ilgiliDosya": warning["file_name"],
                "onerilenIslem": "Toplu paket içeriğini dönem içindeki XML setiyle karşılaştırın.",
            }
        )
    return issues


def build_period_logs(summary: ScanSummary, diagnostics: dict[str, Any]) -> list[dict[str, str]]:
    logs = [
        {
            "saat": summary.scan_finished_at.replace("T", " "),
            "seviye": "INFO" if diagnostics["risk"] == "OK" else "WARNING",
            "mesaj": "Dönem taraması tamamlandı.",
        }
    ]
    if diagnostics["parse_errors"]:
        logs.append(
            {
                "saat": summary.scan_finished_at.replace("T", " "),
                "seviye": "ERROR",
                "mesaj": f"{len(diagnostics['parse_errors'])} dosyada parse sorunu var.",
            }
        )
    if diagnostics["package_warnings"]:
        logs.append(
            {
                "saat": summary.scan_finished_at.replace("T", " "),
                "seviye": "WARNING",
                "mesaj": f"{len(diagnostics['package_warnings'])} toplu paket içeriği uyarısı var.",
            }
        )
    return logs


def file_status(file: FileRecord, siblings: list[FileRecord]) -> str:
    if file.parse_status != "ok":
        return "Bozuk"
    if has_duplicate(siblings):
        return "Tekrar"
    return "Bulundu"


def risk_penalty(risk: str) -> int:
    return {"OK": 0, "LOW": 1, "MEDIUM": 3, "HIGH": 6, "CRITICAL": 10}.get(risk, 0)


def friendly_missing_name(value: str) -> str:
    mapping = {
        "JOURNAL_BOOK": "Yevmiye defteri",
        "LEDGER_BOOK": "Kebir defteri",
        "INVENTORY_BOOK": "Envanter defteri",
        "JOURNAL_BERAT": "Yevmiye beratı",
        "LEDGER_BERAT": "Kebir beratı",
        "INVENTORY_BERAT": "Envanter beratı",
        "GIB_APPROVED_JOURNAL_BERAT": "GİB onaylı yevmiye beratı",
        "GIB_APPROVED_LEDGER_BERAT": "GİB onaylı kebir beratı",
        "GIB_APPROVED_INVENTORY_BERAT": "GİB onaylı envanter beratı",
        "DEFTER_RAPORU": "Defter raporu",
    }
    return mapping.get(value, value)


def document_type_label(document_type: DocumentType) -> str:
    mapping = {
        DocumentType.JOURNAL_BOOK: "Y XML/ZIP",
        DocumentType.LEDGER_BOOK: "K XML/ZIP",
        DocumentType.INVENTORY_BOOK: "E XML/ZIP",
        DocumentType.JOURNAL_BERAT: "YB XML/ZIP",
        DocumentType.LEDGER_BERAT: "KB XML/ZIP",
        DocumentType.INVENTORY_BERAT: "EB XML/ZIP",
        DocumentType.GIB_APPROVED_JOURNAL_BERAT: "GİB YB XML/ZIP",
        DocumentType.GIB_APPROVED_LEDGER_BERAT: "GİB KB XML/ZIP",
        DocumentType.GIB_APPROVED_INVENTORY_BERAT: "GİB EB XML/ZIP",
        DocumentType.DEFTER_RAPORU: "DR XML/ZIP",
        DocumentType.AGGREGATE_PACKAGE: "Toplu Paket",
        DocumentType.AUXILIARY: "Yardımcı Dosya",
        DocumentType.UNKNOWN: "Bilinmeyen",
    }
    return mapping.get(document_type, document_type.value)


def highest_risk(values: list[str]) -> str:
    order = ["OK", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
    if not values:
        return "LOW"
    return max(values, key=lambda item: order.index(item))


def month_color(risk: str, transition_role: str = "") -> str:
    if transition_role == "transition":
        return "amber"
    return {"OK": "green", "LOW": "yellow", "MEDIUM": "yellow", "HIGH": "red", "CRITICAL": "red"}.get(risk, "gray")


def month_short_status(row: dict[str, Any]) -> str:
    role = row.get("gecisRolu", "")
    if role == "transition":
        return "Geçiş"
    if role == "post":
        return "Devam"
    return row["durum"]


def month_name(month: int) -> str:
    names = {
        1: "Ocak",
        2: "Şubat",
        3: "Mart",
        4: "Nisan",
        5: "Mayıs",
        6: "Haziran",
        7: "Temmuz",
        8: "Ağustos",
        9: "Eylül",
        10: "Ekim",
        11: "Kasım",
        12: "Aralık",
    }
    return names[month]


def empty_dashboard() -> dict[str, Any]:
    return {
        "profil": "Genel",
        "arsivKlasoru": "",
        "hazirYillar": [],
        "sonTarama": "Henüz tarama yapılmadı",
        "toplamFirma": 0,
        "toplamDonem": 0,
        "eksikDonem": 0,
        "kritikHata": 0,
        "genelSkor": 0,
        "riskDagilimi": {"OK": 0, "LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0},
        "sonOzet": [],
        "ilerleme": {"asama": "Arşiv klasörü bekleniyor", "yuzde": 0, "islenenDosya": 0, "toplamDosya": 0, "bulunanMukellef": 0, "hataSayisi": 0},
        "mukellefKartlari": [],
        "islemGunlugu": [],
    }
