// Un tour de débat : Scanner → News → Planificateur ⇄ Risque → Sceptique → Chef.
import { PERSONAS } from './personas.js';
import { parseJson } from './grok.js';
import { scan } from './scanner.js';
import { evaluatePlan } from './risk.js';
import { escapeHtml } from './telegram.js';

const J = (x) => JSON.stringify(x, null, 1);

export async function runRound({ cfg, llm, tg, provider, journal, status, focusTicker = null, now = new Date(), broker = null }) {
  const transcript = [];
  const result = { decision: 'NONE', focus: null, plan: null, riskCheck: null };

  const speak = async (role, data, task, ctx) => {
    const user = `${data}\n\nDiscussion du tour jusqu'ici :\n${transcript.length ? transcript.join('\n') : '(tu ouvres le tour)'}\n\nTa mission maintenant : ${task}`;
    const raw = await llm.chat({ role, system: PERSONAS[role].system, user, json: true, ctx });
    const out = parseJson(raw) || { message: String(raw || '').slice(0, 600) };
    const msg = String(out.message || '').trim() || '…';
    transcript.push(`${PERSONAS[role].name} : ${msg}`);
    await tg.send(role, msg);
    return out;
  };

  // 1. SCANNER — les chiffres sont calculés en code, Grok choisit et commente.
  let { all, candidates } = await scan(cfg.watchlist, provider, cfg.scanner);
  if (focusTicker) {
    const forced = all.find((m) => m.symbol === focusTicker) || (await scan([focusTicker], provider, { ...cfg.scanner, minRelVolume: 0, minBarSpike: 0, minPrice: 0 })).all[0];
    if (forced) candidates = [forced, ...candidates.filter((c) => c.symbol !== focusTicker)];
  }
  if (!candidates.length) { result.quiet = true; return result; }

  const ctx = { candidates };
  const sc = await speak('scanner',
    `Heure NY : ${status.hhmm}. Métriques (volume relatif = cumul du jour / moyenne des jours précédents à la même heure ; barSpike = dernière bougie 5 min / moyenne 20 ; champ "tv" = lecture de l'indicateur TradingView Grok Desk si présent) :\n${J(candidates)}`,
    `présente les volumes inhabituels et choisis UN titre à débattre${focusTicker ? ` (l'utilisateur a demandé ${focusTicker})` : ''}.`, ctx);
  const focus = candidates.find((c) => c.symbol === String(sc.focus || '').toUpperCase()) || candidates[0];
  result.focus = focus.symbol;
  ctx.focus = focus;

  // 2. NEWS
  const headlines = await provider.news(focus.symbol).catch(() => []);
  const nw = await speak('news', `Titre : ${focus.symbol}\nDerniers titres d'actualité :\n${headlines.length ? headlines.map((h) => `- [${h.date}] ${h.title}`).join('\n') : '(aucun titre trouvé)'}`,
    'dis s\'il y a un catalyseur qui explique ce volume.', ctx);
  ctx.news = nw;

  // 3. PLANIFICATEUR ⇄ 4. RISQUE (une révision autorisée)
  const marketData = `Données ${focus.symbol} :\n${J(focus)}\nCatalyseur selon News : ${nw.catalyst ?? '?'} (confiance ${nw.confidence ?? '?'})\nRègles du desk : R:R ≥ ${cfg.risk.minRR}, stop ≤ ${cfg.risk.maxStopPct} % de l'entrée et ≥ 0,5 × ATR 5 min, entrée à ≤ ${cfg.risk.maxEntryDistancePct} % du prix, risque ${cfg.risk.riskPerTradePct} % du capital (${cfg.risk.capital} $).`;
  let plan, check, rk;
  for (let attempt = 0; attempt < 2; attempt++) {
    ctx.revision = attempt > 0;
    plan = await speak('planner', marketData,
      attempt === 0 ? 'propose le plan (entrée, stop, objectif) ou "none" si ça ne vaut rien.' : `le Risque a refusé pour : ${check.violations.join(' ; ') || rk?.message}. Corrige ton plan ou abandonne ("none").`, ctx);
    plan.ticker = focus.symbol;
    result.plan = plan;
    if (plan.direction !== 'long' && plan.direction !== 'short') {
      await tg.send('chef', `Pas de plan sur ${focus.symbol}, on passe. Prochain scan dans ${cfg.cycleMinutes} min.`);
      result.decision = 'NO_GO';
      return result;
    }
    check = evaluatePlan(plan, focus, journal, cfg.risk, status);
    ctx.riskCheck = check;
    rk = await speak('risk', `Plan : ${J({ direction: plan.direction, entry: plan.entry, stop: plan.stop, target: plan.target })}\nContrôle automatique : ${J(check)}`,
      check.ok ? 'le contrôle passe : valides-tu (APPROVE) ou refuses-tu (REJECT) quand même ?' : 'le contrôle a trouvé des violations : tu dois REFUSER (REJECT) et expliquer.', ctx);
    check.approved = check.ok && String(rk.verdict).toUpperCase() === 'APPROVE';
    if (check.approved) break;
  }
  result.riskCheck = check;
  ctx.riskApproved = check.approved;

  // 5. SCEPTIQUE
  const sk = await speak('skeptic', `Plan final : ${J({ ticker: focus.symbol, direction: plan.direction, entry: plan.entry, stop: plan.stop, target: plan.target, rr: check.rr })}\nDonnées : ${J(focus)}`,
    'attaque ce plan avec ton meilleur argument.', ctx);

  // 6. CHEF — ne peut pas forcer un GO refusé par le Risque (verrou en code).
  const ch = await speak('chef', `Verdict du Risque : ${check.approved ? 'APPROUVÉ' : 'REFUSÉ'}\nGravité de l'objection du Sceptique : ${sk.severity ?? '?'}/10\nPositions actives : ${journal.active().length}, P&L du jour : ${journal.realizedPnl} $`,
    'tranche : GO, NO_GO ou WATCH.', ctx);
  let decision = String(ch.decision || 'NO_GO').toUpperCase();
  if (decision === 'GO' && !check.approved) decision = 'NO_GO';
  result.decision = decision;

  if (decision === 'GO') {
    let pos, title;
    if (broker) {
      try {
        const fill = await broker.open(plan, check, cfg.risk.maxEntryDistancePct);
        pos = journal.openFilled(plan, fill, now);
        title = `🟢 ORDRE ${escapeHtml(broker.label || 'MT5')} EXÉCUTÉ — ${escapeHtml(pos.ticker)} (${escapeHtml(fill.symbol)} #${fill.ticket})`;
      } catch (e) {
        result.decision = 'BROKER_REJECTED';
        result.error = e.message;
        await tg.send('risk', `Ordre bloqué à l'exécution : ${e.message}. Rien n'est passé.`);
        return result;
      }
    } else {
      pos = journal.open(plan, check, now);
      title = `✅ ORDRE PAPIER — ${escapeHtml(pos.ticker)}`;
    }
    result.position = pos;
    const card = `<b>${title}</b>\n<code>${pos.direction.toUpperCase()} ${pos.shares} @ ${pos.entry}\nStop    ${pos.stop}\nObjectif ${pos.target}\nR:R ${check.rr} · risque ${check.riskUsd} $ · gain visé ${check.rewardUsd} $</code>`;
    await tg.send('chef', card, { html: true });
    if (provider.snapshot) {
      const file = await provider.snapshot(pos.ticker).catch(() => null);
      if (file) await tg.sendPhoto('chef', file, `${pos.ticker} — graphique TradingView au moment de la décision`).catch(() => {});
    }
  }
  return result;
}

// Réponse libre du Chef à une question posée dans le groupe (/ask …).
export async function askChef({ llm, tg, journal, question }) {
  const raw = await llm.chat({
    role: 'chef', system: PERSONAS.chef.system, json: true, ctx: { question },
    user: `Un membre humain du groupe te pose une question : "${question}"\nÉtat du desk : ${J({ actives: journal.active(), clotures: journal.state.closed, pnl: journal.realizedPnl })}\nRéponds au format {"decision": "WATCH", "message": "..."}.`,
  });
  await tg.send('chef', (parseJson(raw) || { message: raw }).message || '…');
}
