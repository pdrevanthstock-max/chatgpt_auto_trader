import { describe, expect, it } from "vitest";
import { formatIstTimestamp, globalRanking, independentRanking, latestRowsByIndex } from "./pairRanking";

describe("pair ranking read model", () => {
  it("keeps the latest cycle, removes WAIT rows, sorts rank before Top N", () => {
    const rows = [
      { index: "NIFTY", cycle_id: "old", timestamp: "2026-07-17T09:00:00+05:30", rank: 1 },
      { index: "NIFTY", cycle_id: "new", timestamp: "2026-07-17T09:01:00+05:30", result: "WAIT" },
      { index: "NIFTY", cycle_id: "new", timestamp: "2026-07-17T09:01:00+05:30", rank: 2, result: "FAIL" },
      { index: "NIFTY", cycle_id: "new", timestamp: "2026-07-17T09:01:00+05:30", rank: 1, result: "PASS" },
    ];
    const latest = latestRowsByIndex(rows);
    expect(independentRanking(latest.NIFTY, 5).map(row => row.rank)).toEqual([1, 2]);
  });

  it("ranks eligible candidates first and falls back to best rejection per index", () => {
    const passFirst = globalRanking([
      { index: "NIFTY", result: "FAIL", projected_net: 900, confidence: 99 },
      { index: "BANKNIFTY", result: "PASS", projected_net: 100, confidence: 70 },
      { index: "FINNIFTY", result: "PASS", projected_net: 120, confidence: 60 },
    ]);
    expect(passFirst.rows.map(row => row.index)).toEqual(["FINNIFTY", "BANKNIFTY", "NIFTY"]);
    expect(passFirst.hasExecutableWinner).toBe(true);

    const rejections = globalRanking([
      { index: "NIFTY", result: "FAIL", projected_net: -20, reason: "DUAL_DECAY" },
      { index: "NIFTY", result: "FAIL", projected_net: -50, reason: "STALE_PRICE" },
      { index: "BANKNIFTY", result: "FAIL", projected_net: -10, reason: "INSUFFICIENT_CAPITAL" },
    ]);
    expect(rejections.hasExecutableWinner).toBe(false);
    expect(rejections.rows).toHaveLength(2);
  });

  it("formats visible timestamps in IST", () => {
    expect(formatIstTimestamp("2026-07-17T04:00:05Z")).toBe("17 Jul 2026, 9:30:05 am");
  });
});
