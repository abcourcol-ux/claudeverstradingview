// Carte de prise de position (format demandé par l'utilisateur) :
//   [🟢 MAINTENANT / 🔴 TROP TARD] / [INDICE] / [ACHAT / VENTE]
//   fourchette d'entrée, SL, TP1, TP2, TP final, type de risque (5 niveaux) + probabilité estimée, commentaire.
//
// La probabilité est une ESTIMATION à partir d'un modèle simple, jamais une garantie :
//   base = taux de réussite mesuré en backtest pour ce R:R (sinon seuil de rentabilité 1/(1+R:R) + 5 pts)
//   + alignement de la structure multi-UT (biais pondéré dans le sens du trade)
//   − pénalités : prix étendu loin du VWAP, annonce économique proche, contre-tendance de fond.
import { round } from './scanner.js';

export const RISK_LEVELS = [
  { min: 0.62, label: 'Peu risqué', icon: '🟢' },
  { min: 0.54, label: 'Risque modéré', icon: '🟡' },
  { min: 0.46, label: 'Risque moyen', icon: '🟠' },
  { min: 0.38, label: 'Risqué', icon: '🔴' },
  { min: -Infinity, label: 'Très risqué', icon: '⛔' },
];

export function estimateProbability({ rr, backtestWinRate, biasAligned = 0, extended = false, newsSoon = false, againstHtf = false }) {
  let p = Number.isFinite(backtestWinRate) ? backtestWinRate : 1 / (1 + rr) + 0.05;
  p += 0.12 * Math.max(-1, Math.min(1, biasAligned)); // biasAligned ∈ [-1, 1] : -1 = tout contre, +1 = tout avec
  if (extended) p -= 0.06;
  if (newsSoon) p -= 0.08;
  if (againstHtf) p -= 0.06;
  return Math.min(0.8, Math.max(0.15, p));
}

export const riskLevel = (p) => RISK_LEVELS.find((l) => p >= l.min);

// Construit le plan : fourchette d'entrée ± 0,25 ATR, TP1 = 1R, TP2 = 2R, TP final = cible structurelle (sinon 3R).
// slPips : SL fixe en pips (or : 1 pip = 0,10 $ → pipSize 0.1), prioritaire sur `stop`.
export function buildSignal({ symbol, direction, entry, stop, finalTarget, atr, price, decimals = 2, slPips, pipSize = 0.1, pending = false, ...ctx }) {
  const dir = direction === 'long' ? 1 : -1;
  if (Number.isFinite(slPips)) stop = entry - dir * slPips * pipSize;
  const r = Math.abs(entry - stop);
  const band = 0.25 * (atr || r * 0.2);
  const tp1 = entry + dir * r;
  const tp2 = entry + dir * 2 * r;
  let tpFinal = Number.isFinite(finalTarget) && dir * (finalTarget - tp2) > 0 ? finalTarget : entry + dir * 3 * r;
  const rrFinal = Math.abs(tpFinal - entry) / r;
  const zone = [entry - band, entry + band].sort((a, b) => a - b);
  // Trop tard : le prix a quitté la fourchette dans le sens du trade (ou a déjà touché TP1 / le stop).
  const late = Number.isFinite(price) && (dir * (price - (dir === 1 ? zone[1] : zone[0])) > 0 || dir * (price - tp1) >= 0 || dir * (stop - price) >= 0);
  const p = estimateProbability({ rr: 2, ...ctx });
  const f = (x) => round(x, decimals).toFixed(decimals);
  return {
    symbol, direction, late: pending ? false : late, pending, probability: p, risk: riskLevel(p), rrFinal: round(rrFinal),
    zone: zone.map(f), stop: f(stop), tp1: f(tp1), tp2: f(tp2), tpFinal: f(tpFinal), be: f(entry),
    slPips: Math.round(r / pipSize), pipsPerR: Math.round(r / pipSize),
  };
}

export function formatSignal(sig, comment = '') {
  const lines = [
    `${sig.pending ? '⏳ EN ATTENTE' : sig.late ? '🔴 TROP TARD' : '🟢 MAINTENANT'} | ${sig.symbol} | ${sig.direction === 'long' ? '📈 ACHAT' : '📉 VENTE'}`,
    '',
    `Entrée : ${sig.zone[0]} – ${sig.zone[1]}`,
    `SL : ${sig.stop}  (${sig.slPips} pips)`,
    `BE : ${sig.be}  (SL remonté à l'entrée dès TP1)`,
    `TP1 : ${sig.tp1}  (1R · ${sig.pipsPerR} pips)`,
    `TP2 : ${sig.tp2}  (2R · ${2 * sig.pipsPerR} pips)`,
    `TP final : ${sig.tpFinal}  (${sig.rrFinal}R · ${Math.round(sig.rrFinal * sig.pipsPerR)} pips)`,
    `Risque : ${sig.risk.icon} ${sig.risk.label} — réussite estimée ${Math.round(sig.probability * 100)} %`,
  ];
  if (comment) lines.push('', `💬 ${comment}`);
  lines.push('', 'Estimation statistique, pas une garantie ni un conseil financier.');
  return lines.join('\n');
}
