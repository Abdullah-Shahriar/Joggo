"use client";

import { useMemo, useState } from "react";

import { formatDateOnly } from "@/lib/format";
import type { ActivityDayItem } from "@/lib/types";

const LEVEL_CLASSES: readonly string[] = [
  "bg-bg border-border", // 0
  "bg-[#E6F4F1] border-[#CBEAE3]", // 1
  "bg-[#99D5CB] border-[#7EC6BA]", // 2
  "bg-[#2D9A8F] border-[#218278]", // 3
  "bg-[#0F766E] border-[#0D5F59]", // 4
];

function getLevel(total: number, maxVal: number): number {
  if (total <= 0) return 0;
  if (maxVal <= 4) return Math.min(4, total);
  const ratio = total / maxVal;
  if (ratio <= 0.25) return 1;
  if (ratio <= 0.5) return 2;
  if (ratio <= 0.75) return 3;
  return 4;
}

const WEEKDAY_LABELS = ["", "Mon", "", "Wed", "", "Fri", ""];
const SHORT_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function ActivityHeatmap({
  data,
  title = "Activity overview",
  subtitle = "Daily documents, reviews, drafts, and support messages over the last 13 weeks.",
  fullWidth = false,
}: {
  data: ActivityDayItem[];
  title?: string;
  subtitle?: string;
  fullWidth?: boolean;
}) {
  const [activeDay, setActiveDay] = useState<ActivityDayItem | null>(null);

  const { weeks, monthLabels, maxVal, totalEvents } = useMemo(() => {
    const max = Math.max(1, ...data.map((d) => d.total));
    const sum = data.reduce((acc, d) => acc + d.total, 0);

    const padded: Array<ActivityDayItem | null> = [];
    if (data.length > 0) {
      const firstDate = new Date(`${data[0].date}T00:00:00Z`);
      const leadPad = firstDate.getUTCDay();
      for (let i = 0; i < leadPad; i++) padded.push(null);
    }
    for (const item of data) padded.push(item);
    while (padded.length % 7 !== 0) padded.push(null);

    const cols: Array<Array<ActivityDayItem | null>> = [];
    for (let i = 0; i < padded.length; i += 7) {
      cols.push(padded.slice(i, i + 7));
    }

    const months: Array<{ col: number; label: string }> = [];
    let lastMonth = -1;
    cols.forEach((col, colIdx) => {
      const firstValid = col.find((c) => c !== null);
      if (!firstValid) return;
      const m = new Date(`${firstValid.date}T00:00:00Z`).getUTCMonth();
      if (m !== lastMonth) {
        months.push({ col: colIdx, label: SHORT_MONTHS[m] });
        lastMonth = m;
      }
    });

    return { weeks: cols, monthLabels: months, maxVal: max, totalEvents: sum };
  }, [data]);

  const monthByCol = useMemo(() => {
    const map = new Map<number, string>();
    monthLabels.forEach((m) => map.set(m.col, m.label));
    return map;
  }, [monthLabels]);

  return (
    <section
      aria-label={title}
      className={fullWidth ? "w-full px-4 py-8 sm:px-6 sm:py-10 lg:px-10" : "border-y border-border py-6"}
    >
      <div
        className={
          fullWidth
            ? "mx-auto w-full max-w-7xl rounded-xl border border-[#D1D5DB] bg-bg p-4 shadow-[0_4px_16px_rgba(17,24,39,0.08)] sm:p-6"
            : "w-full rounded-lg border border-[#D1D5DB] bg-bg p-4 shadow-[0_3px_12px_rgba(17,24,39,0.07)] sm:p-5"
        }
      >
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <div>
            <h2 className="text-lg font-semibold text-text">{title}</h2>
            <p className="mt-0.5 text-[15px] text-text-muted">{subtitle}</p>
          </div>
          <span className="rounded border border-border bg-bg-subtle px-2.5 py-1 text-xs font-medium text-text-muted shadow-[0_1px_2px_rgba(17,24,39,0.05)]">
            {totalEvents} total event{totalEvents === 1 ? "" : "s"} in the last 91 days
          </span>
        </div>

        <div className="mt-5 overflow-x-auto pb-2">
          <div className={fullWidth ? "flex w-full min-w-[540px] flex-col gap-2" : "inline-flex flex-col gap-1.5"}>
            {/* Month headers */}
            <div
              className={
                fullWidth
                  ? "grid gap-1.5 pl-8 text-xs font-medium text-text-muted sm:pl-9"
                  : "flex items-center gap-1.5 pl-9 text-[11px] text-text-muted"
              }
              style={
                fullWidth
                  ? { gridTemplateColumns: `repeat(${weeks.length}, minmax(0, 1fr))` }
                  : undefined
              }
            >
              {weeks.map((_, colIdx) => (
                <span key={colIdx} className={fullWidth ? "text-left" : "w-4 shrink-0 text-left"}>
                  {monthByCol.get(colIdx) || ""}
                </span>
              ))}
            </div>

            <div className="flex w-full gap-1.5 sm:gap-2">
              {/* Weekday labels */}
              <div className="flex w-7 shrink-0 flex-col justify-between py-0.5 text-[11px] text-text-muted">
                {WEEKDAY_LABELS.map((lbl, idx) => (
                  <span key={idx} className={fullWidth ? "h-4 leading-4 sm:h-5 sm:leading-5" : "h-4 leading-4"}>
                    {lbl}
                  </span>
                ))}
              </div>

              {/* Grid columns */}
              <div
                className={fullWidth ? "grid flex-1 gap-1.5" : "flex gap-1.5"}
                style={
                  fullWidth
                    ? { gridTemplateColumns: `repeat(${weeks.length}, minmax(0, 1fr))` }
                    : undefined
                }
                role="grid"
                aria-label="Daily activity graph"
              >
                {weeks.map((week, colIdx) => (
                  <div
                    key={colIdx}
                    role="row"
                    className="flex flex-col gap-1.5"
                  >
                    {week.map((cell, rowIdx) => {
                      if (!cell) {
                        return (
                          <span
                            key={rowIdx}
                            className={fullWidth ? "h-4 w-full sm:h-5" : "h-4 w-4"}
                            aria-hidden="true"
                          />
                        );
                      }
                      const lvl = getLevel(cell.total, maxVal);
                      const isSelected = activeDay?.date === cell.date;
                      return (
                        <button
                          key={cell.date}
                          type="button"
                          onMouseEnter={() => setActiveDay(cell)}
                          onFocus={() => setActiveDay(cell)}
                          onClick={() => setActiveDay(cell)}
                          aria-label={`${formatDateOnly(`${cell.date}T00:00:00Z`)}: ${cell.total} events (${cell.documents_uploaded} documents, ${cell.reviews_and_marks} reviews, ${cell.generations_completed} drafts, ${cell.comments_and_help} support messages)`}
                          className={`${fullWidth ? "h-4 w-full sm:h-5" : "h-4 w-4"} rounded-[4px] border shadow-[0_1px_2px_rgba(17,24,39,0.10)] transition-all hover:scale-[1.06] hover:shadow-[0_2px_6px_rgba(15,118,110,0.22)] ${LEVEL_CLASSES[lvl]} ${
                            isSelected ? "ring-2 ring-accent ring-offset-1 shadow-[0_2px_6px_rgba(15,118,110,0.28)]" : ""
                          }`}
                        />
                      );
                    })}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Live tooltip / detail strip + legend */}
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs">
          <div aria-live="polite" className="min-h-[20px] text-text">
            {activeDay ? (
              <span>
                <strong className="font-semibold">
                  {formatDateOnly(`${activeDay.date}T00:00:00Z`)}
                </strong>
                {" · "}
                {activeDay.documents_uploaded} document{activeDay.documents_uploaded === 1 ? "" : "s"},{" "}
                {activeDay.reviews_and_marks} review{activeDay.reviews_and_marks === 1 ? "" : "s"},{" "}
                {activeDay.generations_completed} draft{activeDay.generations_completed === 1 ? "" : "s"},{" "}
                {activeDay.comments_and_help} comment{activeDay.comments_and_help === 1 ? "" : "s"}{" "}
                <span className="text-text-muted">({activeDay.total} total)</span>
              </span>
            ) : (
              <span className="text-text-muted">
                Hover or tap any box to see daily counts for documents, reviews, drafts, and comments.
              </span>
            )}
          </div>

          <div className="flex items-center gap-1.5 text-[11px] text-text-muted">
            <span>Less</span>
            {LEVEL_CLASSES.map((cls, idx) => (
              <span
                key={idx}
                aria-hidden="true"
                className={`inline-block h-3.5 w-3.5 rounded-[3px] border shadow-[0_1px_2px_rgba(17,24,39,0.10)] ${cls}`}
              />
            ))}
            <span>More</span>
          </div>
        </div>
      </div>
    </section>
  );
}
