import type { TradeRow } from "../api/types";

export type JournalPeriod = "today" | "yesterday" | "week" | "month" | "all";

function istDay(value: Date): { year: number; month: number; day: number; epoch: number } {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata", year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(value);
  const get = (type: string) => Number(parts.find(part => part.type === type)?.value);
  const year = get("year"); const month = get("month"); const day = get("day");
  return { year, month, day, epoch: Date.UTC(year, month - 1, day) };
}

export function filterTradesByPeriod(
  trades: TradeRow[],
  period: JournalPeriod,
  now = new Date(),
): TradeRow[] {
  if (period === "all") return [...trades];
  const current = istDay(now);
  const weekday = new Date(current.epoch).getUTCDay();
  const mondayOffset = (weekday + 6) % 7;
  const lower = period === "today"
    ? current.epoch
    : period === "yesterday"
      ? current.epoch - 86_400_000
      : period === "week"
        ? current.epoch - mondayOffset * 86_400_000
        : Date.UTC(current.year, current.month - 1, 1);
  const upper = period === "yesterday" ? current.epoch : current.epoch + 86_400_000;
  return trades.filter(trade => {
    if (!trade.entry_time) return false;
    const parsed = new Date(trade.entry_time);
    if (Number.isNaN(parsed.getTime())) return false;
    const epoch = istDay(parsed).epoch;
    return epoch >= lower && epoch < upper;
  });
}
