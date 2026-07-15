import { useState } from "react";
import type { DiagnosticSnapshot } from "../api/types";

interface Props { diagnostics: DiagnosticSnapshot; onStart: (top: 5 | 10) => void; onStop: () => void; }

export function PairDiagnostics({ diagnostics, onStart, onStop }: Props) {
  const [top, setTop] = useState<5 | 10>(diagnostics.top_count);
  const columns = [...new Set(diagnostics.rows.flatMap(row => Object.keys(row)))];
  return <section className="panel" aria-labelledby="diagnostic-title">
    <div className="panel-heading"><div><p className="eyebrow">Diagnostics</p><h2 id="diagnostic-title">Pair inspector</h2></div><span className={diagnostics.capturing ? "status active" : "status paused"}>{diagnostics.capturing ? "Capturing" : "Capture off"}</span></div>
    <div className="toolbar"><label>Top <select value={top} disabled={diagnostics.capturing} onChange={event => setTop(Number(event.target.value) as 5 | 10)}><option value={5}>5</option><option value={10}>10</option></select></label>
      {!diagnostics.capturing ? <button className="primary" onClick={() => onStart(top)}>Start capture</button> : <button className="danger" onClick={onStop}>Stop capture</button>}
      <a className="button-link" href="/api/diagnostics/download?format=csv">CSV</a><a className="button-link" href="/api/diagnostics/download?format=json">JSON</a>
    </div>
    <p className="warning">NIFTY scanner feed is connected. Captured rows appear after the next eligible completed-candle scan; additional index feeds remain pending and non-executable.</p>
    {diagnostics.rows.length === 0 ? <p className="empty-state">No captured scan rows. Start capture to collect subsequent scans.</p> : <div className="table-wrap"><table><thead><tr>{columns.map(column => <th key={column}>{column}</th>)}</tr></thead><tbody>{diagnostics.rows.map((row, index) => <tr key={index}>{columns.map(column => <td key={column}>{String(row[column] ?? "")}</td>)}</tr>)}</tbody></table></div>}
  </section>;
}
