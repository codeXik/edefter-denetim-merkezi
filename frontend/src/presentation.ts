import type { DurumTipi, RiskLevel } from "./types";

export function riskTone(risk: RiskLevel) {
  switch (risk) {
    case "OK":
      return "ok" as const;
    case "LOW":
    case "MEDIUM":
      return "warning" as const;
    case "HIGH":
    case "CRITICAL":
      return "danger" as const;
  }
}

export function riskLabel(risk: RiskLevel) {
  switch (risk) {
    case "OK":
      return "Temiz";
    case "LOW":
      return "Dikkat";
    case "MEDIUM":
      return "İncelenmeli";
    case "HIGH":
      return "Yüksek Risk";
    case "CRITICAL":
      return "Kritik";
  }
}

export function riskIcon(risk: RiskLevel) {
  switch (risk) {
    case "OK":
      return "✓";
    case "LOW":
    case "MEDIUM":
      return "!";
    case "HIGH":
    case "CRITICAL":
      return "✕";
  }
}

export function statusTone(value: string) {
  if (value === "Bulundu" || value === "OK" || value === "Tam") {
    return "ok" as const;
  }
  if (value === "Eksik" || value === "İncelenmeli" || value === "Tekrar" || value === "MEDIUM") {
    return "warning" as const;
  }
  if (value === "Bozuk" || value === "Eşleşmedi" || value === "HIGH" || value === "CRITICAL") {
    return "danger" as const;
  }
  return "neutral" as const;
}

export function statusIcon(value: DurumTipi) {
  if (value === "Tam") {
    return "✓";
  }
  if (value === "İncelenmeli" || value === "Tekrar") {
    return "!";
  }
  return "✕";
}

export function statusClass(value: DurumTipi) {
  if (value === "Tam") {
    return "ok";
  }
  if (value === "İncelenmeli" || value === "Tekrar") {
    return "warning";
  }
  return "danger";
}

export function validYear(value: number) {
  const upperBound = new Date().getFullYear() + 1;
  return value >= 2000 && value <= upperBound;
}
