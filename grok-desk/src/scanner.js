// Le cœur chiffré du Scanner : volume relatif, pics de volume, VWAP, ATR — calculé en code, pas par l'IA.
import { nyParts } from './market-hours.js';

export function computeMetrics(symbol, bars, prevClose) {
  if (!bars?.length) return null;
  const withDay = bars.map((b) => {
    const p = nyParts(new Date(b.t * 1000));
    return { ...b, day: p.date, tod: p.minutes };
  });
  const days = [...new Set(withDay.map((b) => b.day))];
  const today = days[days.length - 1];
  const todayBars = withDay.filter((b) => b.day === today);
  const last = todayBars[todayBars.length - 1];
  const cumToday = todayBars.reduce((s, b) => s + b.v, 0);

  // Volume relatif : volume cumulé d'aujourd'hui vs moyenne des jours précédents à la même heure.
  const priorCums = days.slice(0, -1).map((d) => withDay.filter((b) => b.day === d && b.tod <= last.tod).reduce((s, b) => s + b.v, 0)).filter((v) => v > 0);
  const avgPrior = priorCums.length ? priorCums.reduce((a, b) => a + b, 0) / priorCums.length : 0;
  const relVolume = avgPrior ? cumToday / avgPrior : null;

  // Pic : dernière bougie 5 min vs moyenne des 20 précédentes.
  const prev20 = withDay.slice(-21, -1);
  const avg20 = prev20.length ? prev20.reduce((s, b) => s + b.v, 0) / prev20.length : 0;
  const barSpike = avg20 ? last.v / avg20 : null;

  const pv = todayBars.reduce((s, b) => s + ((b.h + b.l + b.c) / 3) * b.v, 0);
  const vwap = cumToday ? pv / cumToday : last.c;
  const recent = withDay.slice(-14);
  const atr5m = recent.reduce((s, b) => s + (b.h - b.l), 0) / recent.length;
  const ref = prevClose ?? withDay.filter((b) => b.day !== today).at(-1)?.c ?? todayBars[0].o;

  return {
    symbol,
    price: round(last.c),
    changePct: round(((last.c - ref) / ref) * 100),
    relVolume: relVolume && round(relVolume),
    barSpike: barSpike && round(barSpike),
    volumeToday: cumToday,
    dayHigh: round(Math.max(...todayBars.map((b) => b.h))),
    dayLow: round(Math.min(...todayBars.map((b) => b.l))),
    openPrice: round(todayBars[0].o),
    vwap: round(vwap),
    atr5m: round(atr5m),
    vsVwapPct: round(((last.c - vwap) / vwap) * 100),
    lastBars: todayBars.slice(-6).map((b) => ({ t: nyParts(new Date(b.t * 1000)).hhmm, o: round(b.o), h: round(b.h), l: round(b.l), c: round(b.c), v: b.v })),
  };
}

export async function scan(watchlist, provider, rules) {
  const all = [];
  for (const sym of watchlist) {
    try {
      const { bars, prevClose, tv } = await provider.intraday(sym);
      const m = computeMetrics(sym, bars, prevClose);
      if (m) all.push(tv && Object.keys(tv).length ? { ...m, tv } : m);
    } catch (e) {
      console.warn(`[scanner] ${sym}: ${e.message}`);
    }
  }
  const candidates = all
    .filter((m) => m.price >= rules.minPrice && ((m.relVolume ?? 0) >= rules.minRelVolume || (m.barSpike ?? 0) >= rules.minBarSpike || /LONG|SHORT|ACHAT|VENTE/.test(m.tv?.Signal || '')))
    .sort((a, b) => score(b) - score(a))
    .slice(0, rules.maxCandidates);
  return { all, candidates };
}

const score = (m) => (m.relVolume ?? 0) + 0.5 * (m.barSpike ?? 0) + Math.abs(m.changePct) / 2;
export const round = (x, d = 2) => (x == null ? x : Math.round(x * 10 ** d) / 10 ** d);
