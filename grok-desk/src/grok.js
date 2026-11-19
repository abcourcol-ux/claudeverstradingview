// Client xAI (API compatible OpenAI : POST /v1/chat/completions).
export function createGrok(cfg) {
  if (!cfg.apiKey) throw new Error('XAI_API_KEY manquant (ou lance avec --mock)');
  return {
    async chat({ role, system, user, json = true }) {
      const body = {
        model: cfg.models?.[role] || cfg.model,
        messages: [{ role: 'system', content: system }, { role: 'user', content: user }],
        temperature: role === 'skeptic' ? 0.9 : 0.6,
      };
      if (cfg.maxTokens) body.max_tokens = cfg.maxTokens;
      if (json) body.response_format = { type: 'json_object' };
      for (let attempt = 0; ; attempt++) {
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), cfg.timeoutMs);
        try {
          const r = await fetch(`${cfg.baseUrl}/chat/completions`, {
            method: 'POST', signal: ctrl.signal,
            headers: { Authorization: `Bearer ${cfg.apiKey}`, 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
          });
          if ((r.status === 429 || r.status >= 500) && attempt < 3) { await sleep(2000 * 2 ** attempt); continue; }
          if (!r.ok) throw new Error(`xAI HTTP ${r.status}: ${(await r.text()).slice(0, 300)}`);
          const j = await r.json();
          return j.choices?.[0]?.message?.content ?? '';
        } catch (e) {
          if (e.name === 'AbortError' && attempt < 2) continue;
          throw e;
        } finally { clearTimeout(timer); }
      }
    },
  };
}

export function parseJson(text) {
  if (!text) return null;
  try { return JSON.parse(text); } catch {}
  const m = String(text).match(/\{[\s\S]*\}/);
  if (m) { try { return JSON.parse(m[0]); } catch {} }
  return null;
}

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Faux Grok pour tester sans clé ni réseau : réponses déterministes à partir du contexte.
export function createMockGrok() {
  return {
    async chat({ role, ctx }) {
      const m = ctx.focus;
      const r2 = (x) => Math.round(x * 100) / 100;
      switch (role) {
        case 'scanner':
          return JSON.stringify({ focus: ctx.candidates[0].symbol, message: `${ctx.candidates.map((c) => `${c.symbol} volume x${c.relVolume}`).join(', ')}. Je mets ${ctx.candidates[0].symbol} en tête : ${ctx.candidates[0].changePct} % et ${ctx.candidates[0].vsVwapPct} % au-dessus du VWAP. News, qu'est-ce qui se passe ?` });
        case 'news':
          return JSON.stringify({ catalyst: 'bullish', confidence: 0.7, message: `Catalyseur clair sur ${m.symbol} : relèvement des prévisions annuelles et flux d'options inhabituel. Ce n'est pas un mouvement orphelin.` });
        case 'planner': {
          const e = m.price, a = m.atr5m;
          return ctx.revision
            ? JSON.stringify({ ticker: m.symbol, direction: 'long', entry: r2(e), stop: r2(e - 1.5 * a), target: r2(e + 3.5 * a), horizon: 'intraday', message: `Corrigé : stop élargi sous le bruit à ${r2(e - 1.5 * a)}, objectif ${r2(e + 3.5 * a)}. R:R d'environ 2,3.` })
            : JSON.stringify({ ticker: m.symbol, direction: 'long', entry: r2(e), stop: r2(e - 0.3 * a), target: r2(e + 0.5 * a), horizon: 'intraday', message: `Long ${m.symbol} à ${r2(e)}, stop serré ${r2(e - 0.3 * a)}, objectif ${r2(e + 0.5 * a)}.` });
        }
        case 'risk':
          return JSON.stringify({ verdict: ctx.riskCheck.ok ? 'APPROVE' : 'REJECT', message: ctx.riskCheck.ok ? `Validé. ${ctx.riskCheck.shares} actions, ${ctx.riskCheck.riskUsd} $ en jeu, R:R ${ctx.riskCheck.rr}.` : `REFUS. ${ctx.riskCheck.violations.join(' ; ')}. Planificateur, refais ta copie.` });
        case 'skeptic':
          return JSON.stringify({ severity: 5, message: `On achète un titre déjà à ${m.changePct} % sur la journée, après la news. Qui reste pour acheter derrière nous ? Si le VWAP casse, c'est un piège.` });
        case 'chef':
          if (ctx.question) return JSON.stringify({ decision: 'WATCH', message: `(mock) Réponse du Chef à : ${ctx.question}` });
          return JSON.stringify(ctx.riskApproved
            ? { decision: 'GO', message: `Le Sceptique a raison sur le retard, mais le volume confirme et le risque est borné. GO, et on sort si ça repasse sous le VWAP.` }
            : { decision: 'NO_GO', message: `Pas de trade : le risque a dit non.` });
        default:
          return JSON.stringify({ message: '…' });
      }
    },
  };
}
