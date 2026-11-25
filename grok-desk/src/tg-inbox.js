#!/usr/bin/env node
// Lit les boutons pressés sous les cartes (🛑 SL / ⚖️ BE / 🎯 TP1 / 🎯 TP2 / 🏁 TP final), accuse réception dans Telegram
// et ajoute chaque signalement à grok-desk/forward-test/user-reports.json.
// Usage : NODE_USE_ENV_PROXY=1 node grok-desk/src/tg-inbox.js            → traite les boutons en attente, affiche les nouveaux (JSON)
//         NODE_USE_ENV_PROXY=1 node grok-desk/src/tg-inbox.js --watch 120  → écoute en continu pendant 120 min (réaction immédiate)
// SL, BE ou TP final = trade terminé → les boutons disparaissent et le message indique la clôture.
import { fileURLToPath } from 'url';
import { appendFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs';
import { loadEnvFile } from './config.js';

const here = (p) => fileURLToPath(new URL(p, import.meta.url));
loadEnvFile(here('../.env'));
const token = process.env.TELEGRAM_TOKEN_CHEF || process.env.TELEGRAM_TOKEN;
const chat = String(process.env.TELEGRAM_CHAT_ID || '');
if (!token || !chat) { console.error('Telegram non configuré (TELEGRAM_TOKEN / TELEGRAM_CHAT_ID)'); process.exit(1); }

const LABELS = { sl: '🛑 SL', be: '⚖️ BE', tp1: '🎯 TP1', tp2: '🎯 TP2', tpf: '🏁 TP final' };
const stateFile = here('../data/tg-inbox.json');
const reportsFile = here('../forward-test/user-reports.json');
const read = (f, d) => { try { return JSON.parse(readFileSync(f, 'utf8')); } catch { return d; } };
const state = read(stateFile, { offset: 0 });
const reports = read(reportsFile, []);
const api = async (method, body) => (await fetch(`https://api.telegram.org/bot${token}/${method}`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
})).json();

const FINAL = new Set(['sl', 'be', 'tpf']);
const fresh = [];
async function poll(timeout) {
  const res = await api('getUpdates', { offset: state.offset, timeout, allowed_updates: ['callback_query', 'message'] });
  if (!res.ok) throw new Error(`Telegram : ${res.description}`);
  for (const u of res.result) {
    state.offset = u.update_id + 1;
    const msg = u.message;
    if (msg && String(msg.chat?.id) === chat && String(msg.text || '').startsWith('/sig ')) {
      // signal du groupe Telegram relayé par copier/listen.py (mode papier) → copier/inbox.jsonl
      mkdirSync(here('../copier'), { recursive: true });
      appendFileSync(here('../copier/inbox.jsonl'), msg.text.slice(5).trim() + '\n');
      fresh.push({ signal: msg.text.slice(5, 120) });
      continue;
    }
    const q = u.callback_query;
    if (!q) continue;
    if (String(q.message?.chat?.id) !== chat) { await api('answerCallbackQuery', { callback_query_id: q.id, text: 'Non autorisé' }); continue; }
    const [trade, outcome] = String(q.data || '').split(':');
    if (!LABELS[outcome]) continue;
    const r = { trade, outcome, at: new Date().toISOString(), by: 'utilisateur' };
    reports.push(r);
    fresh.push(r);
    await api('answerCallbackQuery', { callback_query_id: q.id, text: `Noté : ${LABELS[outcome]} sur le trade #${trade}` });
    if (FINAL.has(outcome)) {
      // Trade terminé : on retire les boutons et on l'indique sous le message
      await api('editMessageReplyMarkup', { chat_id: chat, message_id: q.message.message_id, reply_markup: { inline_keyboard: [] } });
      await api('sendMessage', { chat_id: chat, reply_to_message_id: q.message.message_id, text: `✅ Trade #${trade} clôturé : ${LABELS[outcome]} (noté pour le backtest)` });
      continue;
    }
    // Trade toujours en cours (TP1, TP2) : on garde les boutons et on coche ce qui a été signalé
    const kb = [['sl', 'be', 'tp1'], ['tp2', 'tpf']].map((row) => row.map((o) => ({
      text: (reports.some((x) => x.trade === trade && x.outcome === o) ? '✅ ' : '') + LABELS[o], callback_data: `${trade}:${o}`,
    })));
    await api('editMessageReplyMarkup', { chat_id: chat, message_id: q.message.message_id, reply_markup: { inline_keyboard: kb } });
  }
  save();
}
function save() {
  mkdirSync(here('../data'), { recursive: true });
  writeFileSync(stateFile, JSON.stringify(state));
  writeFileSync(reportsFile, JSON.stringify(reports, null, 2));
}
const wi = process.argv.indexOf('--watch');
if (wi >= 0) {
  const until = Date.now() + Number(process.argv[wi + 1] || 120) * 60_000;
  while (Date.now() < until) {
    try { await poll(25); if (fresh.length) { console.log(JSON.stringify(fresh.splice(0))); } }
    catch (e) { console.error(e.message); await new Promise((r) => setTimeout(r, 5000)); }
  }
  process.exit(0);
}
await poll(0);
console.log(JSON.stringify({ nouveaux: fresh, total: reports.length }));
