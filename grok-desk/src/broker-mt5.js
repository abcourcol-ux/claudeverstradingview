// Exécution réelle via MetaTrader 5 (Axi) — démo par défaut, réel seulement avec MT5_ALLOW_LIVE=YES_REAL_MONEY.
// Lance mt5/mt5_bridge.py (Python + paquet MetaTrader5, Windows) et lui parle en JSON ligne par ligne.
import { spawn } from 'child_process';
import { fileURLToPath } from 'url';
import { createInterface } from 'readline';

export function parseSymbolMap(s) {
  return Object.fromEntries((s || '').split(',').map((p) => p.split(':').map((x) => x.trim())).filter(([a, b]) => a && b).map(([a, b]) => [a.toUpperCase(), b]));
}

// Volume en lots à partir d'un nombre d'actions, arrondi au pas inférieur et borné.
export function sharesToLots(shares, info) {
  const raw = shares / (info.contract_size || 1);
  const step = info.volume_step || 1;
  const lots = Math.floor(raw / step + 1e-9) * step;
  const clamped = Math.min(lots, info.volume_max ?? lots);
  const decimals = (String(step).split('.')[1] || '').length;
  return Number(clamped.toFixed(decimals));
}

export function createMt5Broker(cfg, { spawnFn = spawn } = {}) {
  const bridgePath = fileURLToPath(new URL('../mt5/mt5_bridge.py', import.meta.url));
  const python = cfg.python || (process.platform === 'win32' ? 'python' : 'python3');
  const symbols = parseSymbolMap(cfg.symbolMap);
  let proc, rl, nextId = 1;
  const pending = new Map();

  function start() {
    proc = spawnFn(python, [bridgePath], { stdio: ['pipe', 'pipe', 'inherit'], env: process.env });
    rl = createInterface({ input: proc.stdout });
    rl.on('line', (line) => {
      let msg;
      try { msg = JSON.parse(line); } catch { return; }
      const p = pending.get(msg.id);
      if (!p) return;
      pending.delete(msg.id);
      msg.ok ? p.resolve(msg.result) : p.reject(new Error(msg.error));
    });
    proc.on('exit', (code) => {
      for (const p of pending.values()) p.reject(new Error(`pont MT5 arrêté (code ${code})`));
      pending.clear();
      proc = null;
    });
    proc.on('error', (e) => { for (const p of pending.values()) p.reject(e); pending.clear(); });
  }

  const call = (cmd, args = {}) => new Promise((resolve, reject) => {
    if (!proc) start();
    const id = nextId++;
    const timer = setTimeout(() => { pending.delete(id); reject(new Error(`MT5 ${cmd} : délai dépassé`)); }, 30_000);
    pending.set(id, { resolve: (v) => { clearTimeout(timer); resolve(v); }, reject: (e) => { clearTimeout(timer); reject(e); } });
    proc.stdin.write(JSON.stringify({ id, cmd, ...args }) + '\n');
  });

  const mapSymbol = (ticker) => {
    const s = symbols[ticker.toUpperCase()];
    if (!s) throw new Error(`${ticker} n'a pas d'équivalent MT5 dans MT5_SYMBOLS (ex. ${ticker}:NVIDIA+)`);
    return s;
  };

  return {
    name: 'mt5',
    tradable: (ticker) => Boolean(symbols[ticker.toUpperCase()]),
    mapSymbol,
    async connect() { return call('init'); },
    account: () => call('account'),
    symbolInfo: (ticker) => call('symbol', { symbol: mapSymbol(ticker) }),
    listSymbols: (filter) => call('symbols', { filter }),
    rates: (ticker, timeframe = 'M5', count = 1500) => call('rates', { symbol: mapSymbol(ticker), timeframe, count }),

    // Ouvre une position au marché avec stop et objectif attachés côté serveur.
    async open(plan, check, maxEntryDistancePct) {
      const symbol = mapSymbol(plan.ticker);
      const info = await call('symbol', { symbol });
      const side = plan.direction === 'long' ? 'buy' : 'sell';
      const px = side === 'buy' ? info.ask : info.bid;
      const entry = Number(plan.entry);
      const drift = (Math.abs(px - entry) / entry) * 100;
      if (drift > maxEntryDistancePct) throw new Error(`prix MT5 ${px} trop loin de l'entrée prévue ${entry} (${drift.toFixed(2)} %)`);
      const volume = sharesToLots(check.shares, info);
      if (volume < info.volume_min) throw new Error(`taille ${check.shares} unités < minimum MT5 (${info.volume_min} lot × ${info.contract_size})`);
      const r = await call('open', { symbol, side, volume, sl: Number(plan.stop), tp: Number(plan.target), comment: `GrokDesk ${plan.ticker}` });
      return { ...r, symbol, lots: volume, shares: volume * (info.contract_size || 1) };
    },
    positions: () => call('positions'),
    close: (ticket, comment) => call('close', { ticket, comment }),
    closed: (ticket) => call('closed', { ticket }),
    stop() { proc?.stdin.end(); },
  };
}
