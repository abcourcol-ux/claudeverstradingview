// Sources de données : Yahoo Finance (gratuit, sans clé) ou un marché simulé pour --mock.
const UA = { 'User-Agent': 'Mozilla/5.0 (GrokDesk)' };

export function yahooProvider() {
  return {
    async intraday(symbol) {
      const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?interval=5m&range=5d&includePrePost=false`;
      const r = await fetch(url, { headers: UA });
      if (!r.ok) throw new Error(`Yahoo HTTP ${r.status}`);
      const res = (await r.json()).chart?.result?.[0];
      if (!res?.timestamp) throw new Error('pas de données');
      const q = res.indicators.quote[0];
      const bars = res.timestamp
        .map((t, i) => ({ t, o: q.open[i], h: q.high[i], l: q.low[i], c: q.close[i], v: q.volume[i] }))
        .filter((b) => b.c != null && b.v != null);
      return { bars, prevClose: res.meta?.previousClose ?? res.meta?.chartPreviousClose };
    },
    async lastPrice(symbol) {
      const { bars } = await this.intraday(symbol);
      return bars.at(-1)?.c;
    },
    async news(symbol) {
      const r = await fetch(`https://feeds.finance.yahoo.com/rss/2.0/headline?s=${encodeURIComponent(symbol)}&region=US&lang=en-US`, { headers: UA });
      if (!r.ok) return [];
      const xml = await r.text();
      return [...xml.matchAll(/<item>([\s\S]*?)<\/item>/g)].slice(0, 8).map(([, it]) => ({
        title: decode(tag(it, 'title')), date: tag(it, 'pubDate'), source: 'Yahoo Finance',
      }));
    },
  };
}

const tag = (s, t) => (s.match(new RegExp(`<${t}>(?:<!\\[CDATA\\[)?([\\s\\S]*?)(?:\\]\\]>)?</${t}>`)) || [])[1]?.trim() || '';
const decode = (s) => s.replace(/&amp;/g, '&').replace(/&quot;/g, '"').replace(/&#39;|&apos;/g, "'").replace(/&lt;/g, '<').replace(/&gt;/g, '>');

// Marché simulé : 5 jours de bougies 5 min, avec deux titres en volume anormal aujourd'hui.
export function mockProvider(watchlist, now = new Date(), seed = 42) {
  let s = seed;
  const rnd = () => ((s = (s * 16807) % 2147483647) / 2147483647);
  const hot = new Set(watchlist.slice(1, 3));
  const data = {};
  const end = Math.floor(now.getTime() / 300_000) * 300;
  for (const sym of watchlist) {
    let price = 20 + rnd() * 400;
    const bars = [];
    const baseVol = 50_000 + rnd() * 400_000;
    // 4 jours précédents (78 bougies chacun), puis aujourd'hui jusqu'à "maintenant".
    for (let d = 4; d >= 0; d--) {
      const n = d === 0 ? 24 : 78;
      const start = end - d * 86_400 - 23 * 300; // même heure d'ouverture chaque jour
      for (let i = 0; i < n; i++) {
        const isHot = d === 0 && hot.has(sym);
        const drift = isHot ? 0.0015 : 0;
        const o = price;
        price = price * (1 + drift + (rnd() - 0.5) * 0.004);
        const c = price;
        const hi = Math.max(o, c) * (1 + rnd() * 0.002);
        const lo = Math.min(o, c) * (1 - rnd() * 0.002);
        const v = Math.round(baseVol * (0.6 + rnd()) * (isHot ? 3.2 + (i === n - 1 ? 3 : 0) : 1));
        bars.push({ t: start + i * 300, o, h: hi, l: lo, c, v });
      }
    }
    data[sym] = { bars, prevClose: bars[bars.length - 25].c };
  }
  return {
    async intraday(sym) { if (!data[sym]) throw new Error('inconnu'); return data[sym]; },
    async lastPrice(sym) { return data[sym]?.bars.at(-1).c; },
    async news(sym) {
      return hot.has(sym)
        ? [{ title: `${sym} jumps after raising full-year guidance, analysts lift targets`, date: now.toUTCString(), source: 'mock' },
          { title: `Options activity surges in ${sym} as call volume doubles`, date: now.toUTCString(), source: 'mock' }]
        : [{ title: `${sym} trades in line with the market`, date: now.toUTCString(), source: 'mock' }];
    },
    _data: data,
  };
}

// Source TradingView Desktop : passe par le pont CDP de ce repo (port 9222).
// Le desk pilote ton graphique (symbole + UT 5 min) et lit aussi le tableau de l'indicateur "Grok Desk".
export async function tradingviewProvider({ timeframe = '5', count = 500, studyFilter = 'Grok Desk' } = {}) {
  const core = await import('../../src/core/index.js');
  const yahoo = yahooProvider();
  let lock = Promise.resolve();
  let current = null;
  let tfSet = false;
  const exclusive = (fn) => { const p = lock.then(fn, fn); lock = p.catch(() => {}); return p; };
  const load = async (sym) => {
    if (current !== sym) { await core.chart.setSymbol({ symbol: sym }); current = sym; }
    if (!tfSet) { await core.chart.setTimeframe({ timeframe }); tfSet = true; }
  };
  const readSignal = async () => {
    try {
      const t = await core.data.getPineTables({ study_filter: studyFilter });
      const rows = t.studies?.[0]?.tables?.[0]?.rows || [];
      return Object.fromEntries(rows.map((r) => r.split(' | ')).filter((c) => c.length >= 2).map(([k, ...v]) => [k.trim(), v.join(' | ').trim()]));
    } catch { return null; }
  };
  return {
    name: 'tradingview',
    intraday: (sym) => exclusive(async () => {
      await load(sym);
      const o = await core.data.getOhlcv({ count });
      const bars = o.bars.map((b) => ({ t: b.time, o: b.open, h: b.high, l: b.low, c: b.close, v: b.volume }));
      return { bars, prevClose: null, tv: await readSignal() };
    }),
    lastPrice: (sym) => exclusive(async () => { await load(sym); return (await core.data.getQuote({})).last; }),
    news: (sym) => yahoo.news(sym), // TradingView n'expose pas les news via CDP : Yahoo RSS en complément
    snapshot: (sym) => exclusive(async () => {
      await load(sym);
      const r = await core.capture.captureScreenshot({ region: 'chart', filename: `grokdesk_${sym}_${Date.now()}` });
      return r.file_path || r.path || r.filePath || null;
    }),
  };
}
