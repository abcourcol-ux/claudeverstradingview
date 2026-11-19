// Publication vers le tableau de bord mobile (app Lovable + base Supabase / Lovable Cloud).
// Tout passe par la fonction Edge "desk-sync", protégée par un secret partagé (DESK_SYNC_SECRET).
// Une panne du tableau de bord ne bloque jamais le desk : erreurs journalisées, rien de plus.
export function createDashboard({ url, secret, log = console.warn, fetchFn = (...a) => fetch(...a) } = {}) {
  if (!url || !secret) return null;
  let failures = 0;
  async function call(action, data) {
    try {
      const r = await fetchFn(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'x-desk-secret': secret },
        body: JSON.stringify({ action, data }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status} ${(await r.text()).slice(0, 200)}`);
      failures = 0;
      return await r.json();
    } catch (e) {
      if (failures++ % 20 === 0) log(`[dashboard] ${action} : ${e.message}`);
      return null;
    }
  }
  const strip = (s) => String(s).replace(/<[^>]+>/g, '').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
  return {
    message: (bot, text) => call('message', { bot, text: strip(text) }),
    round: (r, status) => call('round', {
      ny_time: status?.hhmm, focus: r.focus, decision: r.decision, quiet: Boolean(r.quiet),
      plan: r.plan ? { direction: r.plan.direction, entry: r.plan.entry, stop: r.plan.stop, target: r.plan.target } : null,
      risk: r.riskCheck ? { ok: r.riskCheck.ok, approved: r.riskCheck.approved, rr: r.riskCheck.rr, shares: r.riskCheck.shares, risk_usd: r.riskCheck.riskUsd, violations: r.riskCheck.violations } : null,
      error: r.error ?? null,
    }),
    positions: (list) => call('positions', list.map((p) => ({
      id: p.id, ticker: p.ticker, direction: p.direction, status: p.status, shares: p.shares, entry: p.entry, stop: p.stop,
      target: p.target, exit: p.exit, pnl: p.pnl, reason: p.reason ?? null, broker: p.broker ?? 'paper', ticket: p.ticket ?? null,
      created_at: p.createdAt, filled_at: p.filledAt,
    }))),
    status: (s) => call('status', s),
    async commands() { return (await call('commands', {}))?.commands ?? []; },
    commandDone: (id, result) => call('command_done', { id, result }),
  };
}
