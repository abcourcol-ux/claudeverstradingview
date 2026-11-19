// Envoi Telegram : un bot (token) par personnage, ou un seul bot qui préfixe les messages.
import { readFileSync } from 'fs';
import { basename } from 'path';
import { PERSONAS } from './personas.js';
import { sleep } from './grok.js';

export const escapeHtml = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

export function createTelegram(cfg, { dryRun = false, log = console.log } = {}) {
  const tokenFor = (bot) => cfg.tokens[bot] || cfg.fallbackToken;
  const live = !dryRun && cfg.chatId && Object.keys(PERSONAS).some((b) => tokenFor(b));
  const sent = [];

  async function api(token, method, body, isForm = false) {
    for (let attempt = 0; attempt < 4; attempt++) {
      const r = await fetch(`https://api.telegram.org/bot${token}/${method}`, isForm
        ? { method: 'POST', body }
        : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const j = await r.json().catch(() => ({}));
      if (j.ok) return j.result;
      if (r.status === 429) { await sleep(((j.parameters?.retry_after ?? 3) + 1) * 1000); continue; }
      throw new Error(`Telegram ${method}: ${j.description || r.status}`);
    }
    throw new Error(`Telegram ${method}: trop de tentatives`);
  }

  // `html` = texte déjà formaté (cartes générées par le code) ; sinon on échappe le texte de l'IA.
  async function send(bot, text, { html = false } = {}) {
    const p = PERSONAS[bot];
    const body = html ? text : escapeHtml(text);
    const ownBot = Boolean(cfg.tokens[bot]);
    const full = ownBot ? body : `${p.emoji} <b>${p.name}</b>\n${body}`;
    sent.push({ bot, text: full });
    if (!live) { log(`\n${p.emoji} ${p.name.toUpperCase()}\n${html ? text.replace(/<[^>]+>/g, '') : text}`); return; }
    const token = tokenFor(bot);
    if (cfg.typingDelayMs) {
      await api(token, 'sendChatAction', { chat_id: cfg.chatId, action: 'typing' }).catch(() => {});
      await sleep(cfg.typingDelayMs);
    }
    await api(token, 'sendMessage', { chat_id: cfg.chatId, text: full, parse_mode: 'HTML', disable_web_page_preview: true });
  }

  async function sendPhoto(bot, filePath, caption = '') {
    if (!live || !filePath) { log(`[photo ${bot}] ${filePath}`); return; }
    const form = new FormData();
    form.append('chat_id', cfg.chatId);
    form.append('caption', caption.slice(0, 1000));
    form.append('parse_mode', 'HTML');
    form.append('photo', new Blob([readFileSync(filePath)]), basename(filePath));
    await api(tokenFor(bot), 'sendPhoto', form, true);
  }

  // Écoute des commandes du groupe (/status, /pause…) via le bot du Chef.
  async function poll(onCommand) {
    if (!live) return;
    const token = tokenFor('chef');
    let offset = 0;
    for (;;) {
      try {
        const updates = await api(token, 'getUpdates', { offset, timeout: 30, allowed_updates: ['message'] });
        for (const u of updates) {
          offset = u.update_id + 1;
          const m = u.message;
          if (!m?.text || String(m.chat.id) !== String(cfg.chatId) || m.from?.is_bot) continue;
          const match = m.text.match(/^\/(\w+)(?:@\w+)?\s*([\s\S]*)$/);
          if (match) await onCommand(match[1].toLowerCase(), match[2].trim(), m).catch((e) => console.error('[cmd]', e.message));
        }
      } catch (e) { console.error('[telegram poll]', e.message); await sleep(5000); }
    }
  }

  return { send, sendPhoto, poll, sent, live };
}
