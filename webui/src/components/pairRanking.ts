export type DiagnosticRow = Record<string, unknown>;

const TRADABLE = new Set(["NIFTY", "BANKNIFTY", "FINNIFTY"]);

export function rowIndex(row: DiagnosticRow): string {
  return String(row.index_symbol ?? row.index ?? row.symbol ?? "UNASSIGNED").toUpperCase();
}

export function rowNumber(row: DiagnosticRow, ...keys: string[]): number | null {
  for (const key of keys) {
    if (row[key] === undefined || row[key] === null || row[key] === "") continue;
    const value = Number(row[key]);
    if (Number.isFinite(value)) return value;
  }
  return null;
}

function rowTime(row: DiagnosticRow): number {
  const value = Date.parse(String(row.timestamp ?? ""));
  return Number.isFinite(value) ? value : -Infinity;
}

export function latestRowsByIndex(rows: DiagnosticRow[]): Record<string, DiagnosticRow[]> {
  const grouped: Record<string, DiagnosticRow[]> = {};
  for (const row of rows) (grouped[rowIndex(row)] ??= []).push(row);
  const result: Record<string, DiagnosticRow[]> = {};
  for (const [index, indexRows] of Object.entries(grouped)) {
    const newest = [...indexRows].sort((a, b) => rowTime(b) - rowTime(a))[0];
    const cycle = String(newest?.cycle_id ?? "");
    const latest = cycle ? indexRows.filter(row => String(row.cycle_id ?? "") === cycle) : indexRows;
    const ranked = latest.filter(row => rowNumber(row, "rank", "position") !== null);
    result[index] = ranked.length ? ranked : latest;
  }
  return result;
}

export function independentRanking(rows: DiagnosticRow[], top: number): DiagnosticRow[] {
  return [...rows]
    .filter(row => String(row.result ?? row.verdict ?? row.status ?? "").toUpperCase() !== "WAIT")
    .sort((a, b) => (rowNumber(a, "rank", "position") ?? Infinity) - (rowNumber(b, "rank", "position") ?? Infinity))
    .slice(0, top);
}

function isPass(row: DiagnosticRow): boolean {
  return String(row.result ?? row.verdict ?? row.status ?? "").toUpperCase() === "PASS";
}

function economicSort(a: DiagnosticRow, b: DiagnosticRow): number {
  const pass = Number(isPass(b)) - Number(isPass(a));
  if (pass) return pass;
  const projected = (rowNumber(b, "projected_net", "projected_net_pnl") ?? -Infinity)
    - (rowNumber(a, "projected_net", "projected_net_pnl") ?? -Infinity);
  if (projected) return projected;
  const confidence = (rowNumber(b, "confidence", "strategy_confidence") ?? -Infinity)
    - (rowNumber(a, "confidence", "strategy_confidence") ?? -Infinity);
  return confidence || rowIndex(a).localeCompare(rowIndex(b));
}

export function globalRanking(rows: DiagnosticRow[]): {
  rows: DiagnosticRow[];
  hasExecutableWinner: boolean;
} {
  const tradable = rows.filter(row => TRADABLE.has(rowIndex(row)));
  const hasExecutableWinner = tradable.some(isPass);
  if (hasExecutableWinner) {
    return { rows: [...tradable].sort(economicSort).slice(0, 5), hasExecutableWinner };
  }
  const bestByIndex = Object.values(
    tradable.reduce<Record<string, DiagnosticRow[]>>((groups, row) => {
      (groups[rowIndex(row)] ??= []).push(row); return groups;
    }, {}),
  ).map(group => [...group].sort(economicSort)[0]);
  return { rows: bestByIndex.sort(economicSort).slice(0, 5), hasExecutableWinner };
}

export function formatIstTimestamp(value: unknown): string {
  if (!value) return "—";
  const parsed = new Date(String(value));
  if (Number.isNaN(parsed.getTime())) return "—";
  const parts = new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata", day: "2-digit", month: "short", year: "numeric",
    hour: "numeric", minute: "2-digit", second: "2-digit", hour12: true,
  }).formatToParts(parsed);
  const part = (type: string) => parts.find(item => item.type === type)?.value ?? "";
  return `${part("day")} ${part("month")} ${part("year")}, ${Number(part("hour"))}:${part("minute")}:${part("second")} ${part("dayPeriod").toLowerCase()}`;
}
