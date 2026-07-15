import { useEffect, useState } from "react";
import { api } from "./api/client";
import type {
  ActivePositionView, CapitalSnapshot, DiagnosticSnapshot, IndexUniverseResponse,
  PerformancePeriod, PerformanceSnapshot, RuntimeEvent, RuntimeSnapshot, TradeRow
} from "./api/types";
import { ActivePosition } from "./components/ActivePosition";
import { ActivityConsole } from "./components/ActivityConsole";
import { CapitalPanel } from "./components/CapitalPanel";
import { IndexSelector } from "./components/IndexSelector";
import { PairDiagnostics } from "./components/PairDiagnostics";
import { PerformanceCards } from "./components/PerformanceCards";
import { TradeJournal } from "./components/TradeJournal";
import { EngineControls } from "./components/EngineControls";

export default function App() {
  const [universe, setUniverse] = useState<IndexUniverseResponse | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [period, setPeriod] = useState<PerformancePeriod>("today");
  const [performance, setPerformance] = useState<PerformanceSnapshot | null>(null);
  const [position, setPosition] = useState<ActivePositionView | null>(null);
  const [trades, setTrades] = useState<TradeRow[]>([]);
  const [capital, setCapital] = useState<CapitalSnapshot | null>(null);
  const [diagnostics, setDiagnostics] = useState<DiagnosticSnapshot | null>(null);
  const [events, setEvents] = useState<string[]>(["Web UI loaded in PAPER-safe mode."]);
  const [runtime, setRuntime] = useState<RuntimeSnapshot | null>(null);
  const [connected, setConnected] = useState(false);
  const [engineBusy, setEngineBusy] = useState(false);

  useEffect(() => {
    Promise.all([api.indices(), api.performance("today"), api.activePosition(), api.trades(), api.capital(), api.diagnostics(), api.runtime()])
      .then(([nextUniverse, nextPerformance, nextPosition, nextTrades, nextCapital, nextDiagnostics, nextRuntime]) => {
        setUniverse(nextUniverse);
        setPerformance(nextPerformance);
        setPosition(nextPosition);
        setTrades(nextTrades);
        setCapital(nextCapital);
        setDiagnostics(nextDiagnostics);
        setRuntime(nextRuntime);
        setEvents(current => [...current, "Server-backed dashboard snapshot loaded."]);
      })
      .catch((nextError: Error) => setError(nextError.message));
  }, []);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let retry: number | undefined;
    let disposed = false;
    const connect = () => {
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      socket = new WebSocket(`${protocol}//${window.location.host}/api/events`);
      socket.onopen = () => setConnected(true);
      socket.onmessage = message => {
        const event = JSON.parse(message.data) as RuntimeEvent;
        setRuntime(event.runtime);
        setPosition(event.position);
        setDiagnostics(event.diagnostics);
        if (event.runtime.activity.length > 0) setEvents(event.runtime.activity);
      };
      socket.onclose = () => {
        setConnected(false);
        if (!disposed) retry = window.setTimeout(connect, 1500);
      };
      socket.onerror = () => socket?.close();
    };
    connect();
    return () => {
      disposed = true;
      if (retry !== undefined) window.clearTimeout(retry);
      socket?.close();
    };
  }, []);

  useEffect(() => {
    const refresh = () => Promise.all([api.performance(period), api.trades(), api.capital()])
      .then(([nextPerformance, nextTrades, nextCapital]) => {
        setPerformance(nextPerformance); setTrades(nextTrades); setCapital(nextCapital);
      }).catch((nextError: Error) => setError(nextError.message));
    const timer = window.setInterval(refresh, 5000);
    return () => window.clearInterval(timer);
  }, [period]);

  const changePeriod = async (next: PerformancePeriod) => {
    setPeriod(next);
    setError("");
    try { setPerformance(await api.performance(next)); }
    catch (nextError) { setError(nextError instanceof Error ? nextError.message : "P&L query failed"); }
  };

  const updateSelection = async (symbols: string[]) => {
    if (!universe) return;
    setSaving(true);
    setError("");
    try {
      const selection = await api.updateSelection(symbols, universe.selection.version);
      setUniverse({ ...universe, selection });
      setEvents(current => [...current, selection.pause_new_entries ? "New entries paused by index selection." : `Index selection updated: ${selection.symbols.join(", ")}.`]);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Selection update failed");
    } finally { setSaving(false); }
  };

  const startDiagnostics = async (top: 5 | 10) => {
    try {
      setDiagnostics(await api.startDiagnostics(top));
      setEvents(current => [...current, `Pair capture started (Top ${top}).`]);
    } catch (nextError) { setError(nextError instanceof Error ? nextError.message : "Diagnostic capture failed"); }
  };

  const stopDiagnostics = async () => {
    try {
      setDiagnostics(await api.stopDiagnostics());
      setEvents(current => [...current, "Pair capture stopped."]);
    } catch (nextError) { setError(nextError instanceof Error ? nextError.message : "Diagnostic stop failed"); }
  };

  const startEngine = async () => {
    setEngineBusy(true); setError("");
    try { setRuntime(await api.startEngine()); }
    catch (nextError) { setError(nextError instanceof Error ? nextError.message : "Engine start failed"); }
    finally { setEngineBusy(false); }
  };

  const stopEngine = async () => {
    setEngineBusy(true); setError("");
    try { setRuntime(await api.stopEngine()); }
    catch (nextError) { setError(nextError instanceof Error ? nextError.message : "Engine stop failed"); }
    finally { setEngineBusy(false); }
  };

  const adjustCapital = async (target: number, note: string) => {
    try { setCapital(await api.adjustPaperTarget(target, note)); }
    catch (nextError) { setError(nextError instanceof Error ? nextError.message : "Capital adjustment failed"); }
  };

  return <main>
    <header className="app-header"><div><p className="eyebrow">PAPER validation workspace</p><h1>AutoTrader Control Center</h1></div><span className="paper-lock">PAPER · Broker writes disabled</span></header>
    {error && <div className="error" role="alert">{error}</div>}
    {runtime && <EngineControls runtime={runtime} busy={engineBusy} onStart={startEngine} onStop={stopEngine} />}
    {!universe ? <section className="panel">Loading server-backed dashboard…</section> :
      <IndexSelector indices={universe.indices} selection={universe.selection} disabled={saving} onChange={updateSelection} />}
    <section className="dashboard-grid">
      {performance && <PerformanceCards snapshot={performance} period={period} onPeriodChange={changePeriod} />}
      <ActivePosition position={position} />
    </section>
    {diagnostics && <PairDiagnostics diagnostics={diagnostics} onStart={startDiagnostics} onStop={stopDiagnostics} />}
    <ActivityConsole events={events} connected={connected} />
    <TradeJournal trades={trades} />
    {capital && <CapitalPanel capital={capital} engineRunning={runtime?.state === "RUNNING"} onAdjust={adjustCapital} />}
  </main>;
}
