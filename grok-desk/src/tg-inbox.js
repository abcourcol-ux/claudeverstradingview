#!/usr/bin/env node
// Lit les boutons pressés sous les cartes (🛑 SL / 🎯 TP1 / 🎯 TP2 / 🏁 TP final), accuse réception dans Telegram
// et ajoute chaque signalement à grok-desk/forward-test/user-reports.json.
// Usage : NODE_USE_ENV_PROXY=1 node grok-desk/src/tg-inbox.js   → affiche les nouveaux signalements (JSON)
import { fileURLToPath } from 'url';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs';
import { loadEnvFile } from './config.js';

const here = (p) => fileURLToPath(new URL(p, import.meta.url));
loadEnvFile(here('../.env'));
const token = process.env.TELEGRAM_TOKEN_CHEF || process.env.TELEGRAM_TOKEN;
const chat = String(process.env.TELEGRAM_CHAT_ID || '');
if (!token || !chat) { console.error('Telegram non configuré (TELEGRAM_TOKEN / TELEGRAM_CHAT_ID)'); process.exit(1); }

const LABELS = { sl: '🛑 SL', tp1: '🎯 TP1', tp2: '🎯 TP2', tpf: '🏁 TP final' };
const stateFile = here('../data/tg-inbox.json');
const reportsFile = here('../forward-test/user-reports.json');
const read = (f, d) => { try { return JSON.parse(readFileSync(f, 'utf8')); } catch { return d; } };
const state = read(stateFile, { offset: 0 });
const reports = read(reportsFile, []);
const api = async (method, body) => (await fetch(`https://api.telegram.org/bot${token}/${method}`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
})).json();

const res = await api('getUpdates', { offset: state.offset, timeout: 0, allowed_updates: ['callback_query', 'message'] });
if (!res.ok) { console.error(`Telegram : ${res.description}`); process.exit(1); }
const fresh = [];
for (const u of res.result) {
  state.offset = u.update_id + 1;
  const q = u.callback_query;
  if (!q) continue;
  if (String(q.message?.chat?.id) !== chat) { await api('answerCallbackQuery', { callback_query_id: q.id, text: 'Non autorisé' }); continue; }
  const [trade, outcome] = String(q.data || '').split(':');
  if (!LABELS[outcome]) continue;
  const r = { trade, outcome, at: new Date().toISOString(), by: 'utilisateur' };
  reports.push(r);
  fresh.push(r);
  await api('answerCallbackQuery', { callback_query_id: q.id, text: `Noté : ${LABELS[outcome]} sur le trade #${trade}` });
  // Garde les boutons (on peut signaler TP1 puis TP2…) et marque le dernier signalement d'une coche
  const kb = [['sl', 'tp1'], ['tp2', 'tpf']].map((row) => row.map((o) => ({
    text: (reports.some((x) => x.trade === trade && x.outcome === o) ? '✅ ' : '') + LABELS[o], callback_data: `${trade}:${o}`,
  })));
  await api('editMessageReplyMarkup', { chat_id: chat, message_id: q.message.message_id, reply_markup: { inline_keyboard: kb } });
}
mkdirSync(here('../data'), { recursive: true });
writeFileSync(stateFile, JSON.stringify(state));
writeFileSync(reportsFile, JSON.stringify(reports, null, 2));
console.log(JSON.stringify({ nouveaux: fresh, total: reports.length }));
