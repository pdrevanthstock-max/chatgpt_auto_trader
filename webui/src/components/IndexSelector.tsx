import type { IndexInfo, IndexSelection } from "../api/types";

interface Props {
  indices: IndexInfo[];
  selection: IndexSelection;
  disabled?: boolean;
  onChange: (symbols: string[]) => void;
}

export function IndexSelector({ indices, selection, disabled, onChange }: Props) {
  const selected = new Set(selection.symbols);
  const allSymbols = indices.map((item) => item.symbol);
  const toggle = (symbol: string) => {
    const next = new Set(selected);
    next.has(symbol) ? next.delete(symbol) : next.add(symbol);
    onChange([...next].sort());
  };
  return (
    <section className="panel" aria-labelledby="index-title">
      <div className="panel-heading">
        <div><p className="eyebrow">Entry universe</p><h2 id="index-title">Indices</h2></div>
        <span className={selection.pause_new_entries ? "status paused" : "status active"}>
          {selection.pause_new_entries ? "Pause New Entries" : `${selection.symbols.length} selected`}
        </span>
      </div>
      <label className="index-option all-option">
        <input type="checkbox" checked={selection.is_all} disabled={disabled}
          onChange={() => onChange(selection.is_all ? [] : allSymbols)} />
        <span><strong>All indices</strong><small>Default scan universe</small></span>
      </label>
      <div className="index-grid">
        {indices.map((index) => (
          <label className="index-option" key={index.symbol}>
            <input type="checkbox" checked={selected.has(index.symbol)} disabled={disabled}
              onChange={() => toggle(index.symbol)} />
            <span><strong>{index.display_name}</strong><small>{index.symbol} · Lot {index.lot_size}</small></span>
            <em className={index.runtime_connected && index.permission === "TRADABLE" ? "badge tradable" : "badge observe"}>
              {index.runtime_connected
                ? (index.permission === "TRADABLE" ? "Connected · tradable" : "Connected · observe only")
                : (index.permission === "TRADABLE" ? "Approved · feed pending" : "Observe only · feed pending")}
            </em>
          </label>
        ))}
      </div>
      <p className="hint">Changes apply to the next scan. NIFTY is connected now; other selected indices remain non-executable until their feeds are validated. Existing positions remain under one-second risk and exit monitoring.</p>
    </section>
  );
}
