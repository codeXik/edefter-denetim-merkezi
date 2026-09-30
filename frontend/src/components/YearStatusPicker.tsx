import { useMemo, useState } from "react";

export type YearPickerStatus = "ready" | "active" | "queued";

export interface YearStatusItem {
  year: number;
  status: YearPickerStatus;
}

interface YearStatusPickerProps {
  selectedYear: string;
  yearOptions: number[];
  yearStatuses: YearStatusItem[];
  onYearChange: (value: string) => void;
  scanning?: boolean;
  includeAllOption?: boolean;
  allOptionLabel?: string;
  buttonClassName?: string;
}

export function YearStatusPicker({
  selectedYear,
  yearOptions,
  yearStatuses,
  onYearChange,
  scanning = false,
  includeAllOption = false,
  allOptionLabel = "T\u00fcm Y\u0131llar",
  buttonClassName = "",
}: YearStatusPickerProps) {
  const [open, setOpen] = useState(false);

  const orderedYears = useMemo(() => {
    const years = new Set<number>(yearOptions);
    for (const item of yearStatuses) {
      years.add(item.year);
    }
    return Array.from(years).sort((a, b) => b - a);
  }, [yearOptions, yearStatuses]);

  const statusMap = useMemo(
    () => new Map(yearStatuses.map((item) => [String(item.year), item.status])),
    [yearStatuses],
  );

  const currentStatus = statusMap.get(selectedYear);
  const currentLabel = selectedYear
    ? selectedYear === "T\u00fcm Y\u0131llar"
      ? allOptionLabel
      : `${selectedYear}${currentStatus === "ready" ? " \u2713" : currentStatus === "active" ? " \u2022" : ""}`
    : orderedYears[0]
      ? String(orderedYears[0])
      : "Y\u0131l";

  return (
    <div className="dashboard-year-picker">
      <button
        className={`dashboard-year-picker-button ${buttonClassName}`.trim()}
        onClick={() => setOpen((value) => !value)}
        type="button"
      >
        <span>{currentLabel}</span>
        <span aria-hidden="true">\u25be</span>
      </button>
      {open ? (
        <div className="dashboard-year-picker-menu">
          {includeAllOption ? (
            <button
              className={`dashboard-year-picker-item ${selectedYear === "T\u00fcm Y\u0131llar" ? "dashboard-year-picker-item-selected" : ""}`}
              onClick={() => {
                onYearChange("T\u00fcm Y\u0131llar");
                setOpen(false);
              }}
              type="button"
            >
              <span>{allOptionLabel}</span>
              <small>Haz\u0131r</small>
            </button>
          ) : null}
          {orderedYears.map((year) => {
            const status = statusMap.get(String(year)) ?? "queued";
            const disabled = status !== "ready";
            return (
              <button
                key={year}
                className={`dashboard-year-picker-item dashboard-year-picker-item-${status} ${
                  selectedYear === String(year) ? "dashboard-year-picker-item-selected" : ""
                }`}
                disabled={disabled}
                onClick={() => {
                  onYearChange(String(year));
                  setOpen(false);
                }}
                type="button"
              >
                <span>{year}</span>
                <small>
                  {status === "ready"
                    ? "Haz\u0131r \u2713"
                    : status === "active"
                      ? "Taran\u0131yor"
                      : scanning
                        ? "Bekliyor"
                        : "Taranmad\u0131"}
                </small>
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
