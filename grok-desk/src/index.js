#!/usr/bin/env node
// Grok Desk — six bots Grok qui débattent dans un groupe Telegram pendant la séance de New York.
// Usage : node grok-desk/src/index.js [--mock] [--dry-run] [--once] [--source yahoo|tradingview] [--focus NVDA]
import { fileURLToPath } from 'url';
import { loadConfig, loadEnvFile } from './config.js';
import { marketStatus, nextOpen } from './market-hours.js';
import { createGrok, createMockGrok } from './grok.js';
import { createTelegram, escapeHtml } from './telegram.js';
import { createJournal } from './journal.js';
import { mockProvider, tradingviewProvider, yahooProvider } from './providers.js';
import { runRound, askChef } from './debate.js';

const args = process.argv.slice(2);
const flag = (n) => args.includes(`--${n}`);
const opt = (n) => { const i = args.indexOf(`--${n}`); return i >= 0 ? args[i + 1] : undefined; };

loadEnvFile(fileURLToPath(new URL('../.env', import.meta.url)));
const cfg = loadConfig(process.env, { mock: flag('mock') || undefined, dryRun: flag('dry-run') || undefined });
const source = opt('source') || process.env.DESK_SOURCE || 'yahoo';

const llm = cfg.mock ? createMockGrok() : createGrok(cfg.xai);
const tg = createTelegram(cfg.telegram, { dryRun: cfg.dryRun });
const journal = createJournal(cfg.journalPath, { persist: !cfg.mock });
const provider = cfg.mock ? mockProvider(cfg.watchlist)
  : source === 'tradingview' ? await tradingviewProvider({ timeframe: process.env.TV_TIMEFRAME || '5' })
  : yahooProvider();

const state = { paused: false, busy: false, lastRound: 0, wasOpen: null, lastQuiet: 0 };
const fmtCard = (p) => `${p.direction.toUpperCase()} ${p.ticker} ${p.shares} @ ${p.entry} · stop ${p.stop} · obj. ${p.target} · ${p.status}${p.pnl != null ? ` · ${p.pnl} $` : ''}`;

async function round(status, focusTicker) {
  if (state.busy) return;
  state.busy = true;
  try {
    const r = await runRound({ cfg, llm, tg, provider, journal, status, focusTicker });
    state.lastRound = Date.now();
    if (r.quiet && Date.now() - state.lastQuiet > 60 * 60_000) {
      state.lastQuiet = Date.now();
      await tg.send('scanner', `Calme plat : aucun volume inhabituel sur ${cfg.watchlist.length} titres. Je continue de surveiller.`);
    }
    console.log(`[round] ${status.hhmm} NY → ${r.focus ?? '-'} : ${r.decision}`);
  } catch (e) {
    console.error('[round]', e);
  } finally { state.busy = false; }
}

// Suivi des positions papier : remplissage, stop, objectif, expiration, sortie avant la clôture.
async function monitor(status) {
  for (const pos of journal.active()) {
    const price = await provider.lastPrice(pos.ticker).catch(() => null);
    if (!price) continue;
    if (status.open && status.minutesToClose <= cfg.risk.flattenMinutesBeforeClose) {
      if (pos.status === 'open') {
        const ev = journal.close(pos, price, 'clôture');
        await tg.send('chef', `Fin de séance : je coupe ${pos.ticker} à ${price.toFixed(2)} (${ev.pnl >= 0 ? '+' : ''}${ev.pnl} $). On ne garde rien la nuit.`);
      } else { pos.status = 'expired'; journal.save(); }
      continue;
    }
    for (const ev of journal.update(pos, price, new Date(), cfg.risk.pendingExpiryMinutes)) {
      if (ev.type === 'fill') await tg.send('planner', `${pos.ticker} exécuté à ${pos.entry}. Stop ${pos.stop}, objectif ${pos.target}. Le plan est en place.`);
      if (ev.type === 'expired') await tg.send('planner', `Ordre ${pos.ticker} @ ${pos.entry} jamais touché, je l'annule.`);
      if (ev.type === 'stop') await tg.send('risk', `STOP touché sur ${pos.ticker} à ${pos.stop} : ${ev.pnl} $. Perte encaissée, pas de vengeance. P&L du jour : ${journal.realizedPnl} $.`);
      if (ev.type === 'target') await tg.send('planner', `Objectif atteint sur ${pos.ticker} à ${pos.target} : +${ev.pnl} $. P&L du jour : ${journal.realizedPnl} $.`);
    }
  }
}

async function tick() {
  const status = marketStatus(new Date(), cfg.extraHolidays);
  journal.rollDay(status.date);
  if (state.wasOpen !== null && status.open !== state.wasOpen) {
    if (status.open) await tg.send('chef', `🔔 Cloche d'ouverture à New York. Le desk est en ligne : scan toutes les ${cfg.cycleMinutes} min sur ${cfg.watchlist.join(', ')}.`);
    else {
      const c = journal.state.closed;
      await tg.send('chef', `<b>🔕 Clôture — bilan du jour</b>\n${c.length ? c.map((p) => escapeHtml(fmtCard(p))).join('\n') : 'Aucun trade.'}\n<b>P&amp;L : ${journal.realizedPnl} $</b>`, { html: true });
    }
  }
  state.wasOpen = status.open;
  if (!status.open || state.paused) return;
  await monitor(status);
  if (Date.now() - state.lastRound >= cfg.cycleMinutes * 60_000) await round(status);
}

async function onCommand(cmd, arg) {
  const status = marketStatus(new Date(), cfg.extraHolidays);
  switch (cmd) {
    case 'status': {
      const nxt = status.open ? '' : ` Prochaine ouverture : ${nextOpen(new Date(), cfg.extraHolidays)?.toLocaleString('fr-FR', { timeZone: 'Europe/Paris' })} (Paris).`;
      return tg.send('chef', `Marché : ${status.open ? `ouvert (${status.hhmm} NY, clôture dans ${status.minutesToClose} min)` : status.reason}.${nxt} Desk ${state.paused ? 'en pause' : 'actif'}. Source : ${cfg.mock ? 'mock' : source}. Positions actives : ${journal.active().length}. P&L du jour : ${journal.realizedPnl} $.`);
    }
    case 'pause': state.paused = true; return tg.send('chef', 'Desk en pause. /resume pour reprendre.');
    case 'resume': state.paused = false; return tg.send('chef', 'On reprend.');
    case 'positions': {
      const a = journal.active();
      return tg.send('chef', a.length ? a.map(fmtCard).join('\n') : 'Aucune position active.');
    }
    case 'scan':
      if (!status.open && !cfg.mock) return tg.send('chef', `Marché fermé (${status.reason}). Le desk ne débat qu'en séance.`);
      return round(status, arg ? arg.toUpperCase() : null);
    case 'ask': return arg ? askChef({ llm, tg, journal, question: arg }) : tg.send('chef', 'Usage : /ask ta question');
    default:
      return tg.send('chef', 'Commandes : /status, /scan [TICKER], /positions, /pause, /resume, /ask question');
  }
}

console.log(`Grok Desk — source ${cfg.mock ? 'mock' : source}, modèle ${cfg.mock ? 'mock' : cfg.xai.model}, Telegram ${tg.live ? 'actif' : 'désactivé (console)'}`);

if (flag('once')) {
  // Un tour immédiat, même marché fermé (test) : on simule une heure de séance confortable.
  const s = marketStatus(new Date(), cfg.extraHolidays);
  const status = s.open ? s : { ...s, open: true, hhmm: 'test', minutesSinceOpen: 120, minutesToClose: 180 };
  journal.rollDay(status.date);
  await round(status, opt('focus')?.toUpperCase() || null);
  process.exit(0);
}

tg.poll(onCommand);
await tick();
setInterval(() => tick().catch((e) => console.error('[tick]', e)), 60_000);
