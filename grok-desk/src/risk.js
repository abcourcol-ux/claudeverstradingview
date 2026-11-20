// Règles dures du Gestionnaire de risque. L'IA commente, mais c'est ce code qui a le dernier mot :
// un plan qui viole une règle est refusé, quoi qu'en disent les autres bots (Chef compris).
import { round } from './scanner.js';

export function evaluatePlan(plan, metrics, journal, rules, status) {
  const v = [];
  const dir = plan?.direction;
  const entry = Number(plan?.entry), stop = Number(plan?.stop), target = Number(plan?.target);
  if (dir !== 'long' && dir !== 'short') return { ok: false, violations: ['aucune direction (long/short) proposée'] };
  if (![entry, stop, target].every((x) => Number.isFinite(x) && x > 0)) return { ok: false, violations: ['entrée/stop/objectif manquants ou invalides'] };
  if (dir === 'long' && !(stop < entry && entry < target)) v.push('long : il faut stop < entrée < objectif');
  if (dir === 'short' && !(target < entry && entry < stop)) v.push('short : il faut objectif < entrée < stop');

  const riskPerShare = Math.abs(entry - stop);
  const rewardPerShare = Math.abs(target - entry);
  const rr = riskPerShare ? rewardPerShare / riskPerShare : 0;
  const stopPct = (riskPerShare / entry) * 100;
  if (rr < rules.minRR) v.push(`ratio gain/risque ${round(rr)} < ${rules.minRR} minimum`);
  if (stopPct > rules.maxStopPct) v.push(`stop à ${round(stopPct)} % de l'entrée (> ${rules.maxStopPct} % max)`);
  // Règle du desk : or/argent → SL ≥ minStopPips pips (50 pips fixe, validé sept.–nov.) ; actions → SL ≥ stopAtrMult × ATR 5 min
  const pipRule = (rules.pipSymbols ?? ['XAUUSD', 'XAGUSD']).includes(String(plan.ticker || '').toUpperCase());
  const minStop = pipRule ? (rules.minStopPips ?? 0) * (rules.pipSize ?? 0.1) : (rules.stopAtrMult ?? 0.5) * (metrics?.atr5m || 0);
  if (minStop > 0 && riskPerShare < minStop - 1e-9) v.push(`stop trop serré : ${round(riskPerShare)} $ < minimum ${round(minStop)} $ (${pipRule ? `${rules.minStopPips ?? 0} pips` : `${rules.stopAtrMult ?? 0.5} × ATR 5 min`})`);
  if (metrics?.price) {
    const dist = (Math.abs(entry - metrics.price) / metrics.price) * 100;
    if (dist > rules.maxEntryDistancePct) v.push(`entrée à ${round(dist)} % du prix actuel (> ${rules.maxEntryDistancePct} %)`);
  }

  const open = journal.positions.filter((p) => p.status !== 'closed');
  if (open.length >= rules.maxOpenPositions) v.push(rules.maxOpenPositions === 1 ? `un trade est déjà en cours (${open.map((p) => p.ticker).join(', ')}) : jamais deux trades en même temps` : `déjà ${open.length} positions ouvertes (max ${rules.maxOpenPositions})`);
  if (open.some((p) => p.ticker === plan.ticker)) v.push(`déjà une position sur ${plan.ticker}`);
  if (journal.tradesToday >= rules.maxTradesPerDay) v.push(`quota de ${rules.maxTradesPerDay} trades/jour atteint`);
  const lossLimit = (rules.capital * rules.dailyLossLimitPct) / 100;
  if (journal.realizedPnl <= -lossLimit) v.push(`perte du jour ${round(journal.realizedPnl)} $ ≥ limite ${round(lossLimit)} $ : desk coupé`);
  if (status?.open) {
    if (status.minutesSinceOpen < rules.noEntryFirstMinutes) v.push(`pas d'entrée dans les ${rules.noEntryFirstMinutes} premières minutes`);
    if (status.minutesToClose < rules.noEntryLastMinutes) v.push(`pas d'entrée à moins de ${rules.noEntryLastMinutes} min de la clôture`);
  }

  const riskBudget = (rules.capital * rules.riskPerTradePct) / 100;
  let shares = riskPerShare ? Math.floor(riskBudget / riskPerShare) : 0;
  const maxNotional = (rules.capital * rules.maxPositionPct) / 100;
  if (shares * entry > maxNotional) shares = Math.floor(maxNotional / entry);
  if (shares < 1) v.push('taille calculée < 1 unité (action/once)');

  return {
    ok: v.length === 0, violations: v, rr: round(rr), stopPct: round(stopPct), shares,
    riskUsd: round(shares * riskPerShare), rewardUsd: round(shares * rewardPerShare), notional: round(shares * entry),
  };
}
