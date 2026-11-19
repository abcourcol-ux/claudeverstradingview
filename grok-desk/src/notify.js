#!/usr/bin/env node
// Envoie une carte de prise de position sur Telegram (sans passer par le desk complet).
//   node grok-desk/src/notify.js '{"symbol":"XAUUSD","direction":"short","entry":3690,"stop":3700,"finalTarget":3660,"atr":5,"price":3689}' --comment "…" [--id 1] [--dry-run]
//   node grok-desk/src/notify.js --text "message libre" [--id 1]
// --id N ajoute sous le message des boutons 🛑 SL / 🎯 TP1 / 🎯 TP2 / 🏁 TP final (lus ensuite par tg-inbox.js).
// Champs optionnels : backtestWinRate, biasAligned (-1..1), extended, newsSoon, againstHtf.
// Utilise TELEGRAM_TOKEN_CHEF (ou TELEGRAM_TOKEN) et TELEGRAM_CHAT_ID du .env.
import { fileURLToPath } from 'url';
import { homedir } from 'os';
import { existsSync, readFileSync } from 'fs';
import { join } from 'path';
import { loadEnvFile } from './config.js';
import { buildSignal, formatSignal } from './signal.js';

loadEnvFile(fileURLToPath(new URL('../.env', import.meta.url)));
const args = process.argv.slice(2);
const opt = (n) => { const i = args.indexOf(`--${n}`); return i >= 0 ? args[i + 1] : undefined; };
const text = opt('text') ?? formatSignal(buildSignal(JSON.parse(args[0])), opt('comment') || '');
const tradeId = opt('id');
const replyMarkup = tradeId ? { inline_keyboard: [
  [{ text: '🛑 SL', callback_data: `${tradeId}:sl` }, { text: '🎯 TP1', callback_data: `${tradeId}:tp1` }],
  [{ text: '🎯 TP2', callback_data: `${tradeId}:tp2` }, { text: '🏁 TP final', callback_data: `${tradeId}:tpf` }],
] } : undefined;
// Token : .env du desk, sinon celui enregistré par /telegram:configure
const pluginDir = process.env.TELEGRAM_STATE_DIR || join(process.env.CLAUDE_CONFIG_DIR || join(homedir(), '.claude'), 'channels', 'telegram');
const pluginEnv = join(pluginDir, '.env');
const pluginToken = existsSync(pluginEnv) ? (readFileSync(pluginEnv, 'utf8').match(/^TELEGRAM_BOT_TOKEN=(.+)$/m) || [])[1]?.trim() : undefined;
const token = process.env.TELEGRAM_TOKEN_CHEF || process.env.TELEGRAM_TOKEN || pluginToken;
let chat = process.env.TELEGRAM_CHAT_ID;
// Sans ID de conversation : on prend la dernière conversation privée avec le bot (écris-lui d'abord un message)
if (token && !chat) {
  const u = await fetch(`https://api.telegram.org/bot${token}/getUpdates`).then((r) => r.json()).catch(() => ({}));
  const m = (u.result || []).map((x) => x.message).filter((m) => m?.chat?.type === 'private').at(-1);
  if (m) chat = String(m.chat.id);
}
if (args.includes('--dry-run') || !token || !chat) {
  console.log(text);
  if (!args.includes('--dry-run')) console.error('\n(Telegram non configuré : TELEGRAM_TOKEN / TELEGRAM_CHAT_ID manquants)');
  process.exit(0);
}
const r = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ chat_id: chat, text, disable_web_page_preview: true, ...(replyMarkup ? { reply_markup: replyMarkup } : {}) }),
});
const j = await r.json().catch(() => ({}));
if (!j.ok) { console.error(`Telegram : ${j.description || r.status}`); process.exit(1); }
console.log('✓ envoyé sur Telegram');
