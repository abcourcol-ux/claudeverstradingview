#!/usr/bin/env node
// Outils TradingView pour Grok Desk (via le pont CDP du repo, TradingView Desktop lancé avec --remote-debugging-port=9222).
//
//   node grok-desk/src/tradingview.js export                 → écrit les .pine configurés dans grok-desk/data/pine/
//   node grok-desk/src/tradingview.js indicator              → ajoute l'indicateur "Grok Desk" au graphique
//   node grok-desk/src/tradingview.js backtest [SYM ...]     → stratégie + Strategy Tester sur chaque symbole
//        options : --timeframe 5  --telegram (le Chef poste le bilan, le Sceptique le critique)
import { mkdirSync, writeFileSync } from 'fs';
import { loadConfig, loadEnvFile } from './config.js';
import { loadPine } from './pine-template.js';
import { createGrok, parseJson, sleep } from './grok.js';
import { createTelegram, escapeHtml } from './telegram.js';
import { PERSONAS } from './personas.js';

loadEnvFile(new URL('../.env', import.meta.url).pathname);
const cfg = loadConfig();
const args = process.argv.slice(2);
const cmd = args[0];
const opt = (n, d) => { const i = args.indexOf(`--${n}`); return i >= 0 ? args[i + 1] : d; };
const dataDir = new URL('../data/', import.meta.url).pathname;
const stamp = () => new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);

async function core() { return import('../../src/core/index.js'); }

// Pousse un script dans l'éditeur Pine, après avoir sauvegardé ce qui s'y trouvait.
async function pushScript(name) {
  const { pine } = await core();
  const source = loadPine(name, cfg);
  try {
    const prev = await pine.getSource();
    if (prev?.source) {
      mkdirSync(`${dataDir}pine-backup`, { recursive: true });
      writeFileSync(`${dataDir}pine-backup/editor-${stamp()}.pine`, prev.source);
    }
  } catch {}
  await pine.setSource({ source });
  const r = await pine.smartCompile();
  if (r.has_errors) {
    console.error('Erreurs de compilation Pine :');
    for (const e of r.errors) console.error(`  ligne ${e.line}:${e.column} ${e.message}`);
    process.exit(1);
  }
  console.log(`✓ ${name} compilé et ajouté au graphique (${r.button_clicked})`);
  return r;
}

// Cherche une métrique par nom, où qu'elle soit dans l'objet renvoyé par TradingView.
function findMetric(obj, names, depth = 0) {
  if (!obj || typeof obj !== 'object' || depth > 4) return undefined;
  for (const n of names) if (typeof obj[n] === 'number') return obj[n];
  for (const k of ['all', 'performance', ...Object.keys(obj)]) {
    const v = findMetric(obj[k], names, depth + 1);
    if (v !== undefined) return v;
  }
  return undefined;
}

function summarize(sym, metrics) {
  const r2 = (x) => (x == null ? null : Math.round(x * 100) / 100);
  return {
    symbol: sym,
    netProfit: r2(findMetric(metrics, ['netProfit'])),
    netProfitPct: r2(findMetric(metrics, ['netProfitPercent'])),
    trades: findMetric(metrics, ['totalTrades']),
    winRatePct: r2((findMetric(metrics, ['percentProfitable']) ?? NaN) * (findMetric(metrics, ['percentProfitable']) <= 1 ? 100 : 1)),
    profitFactor: r2(findMetric(metrics, ['profitFactor'])),
    maxDrawdown: r2(findMetric(metrics, ['maxStrategyDrawDown', 'maxDrawDown'])),
    avgTrade: r2(findMetric(metrics, ['avgTrade'])),
    sharpe: r2(findMetric(metrics, ['sharpeRatio'])),
  };
}

async function backtest() {
  const symbols = args.slice(1).filter((a) => !a.startsWith('--') && !/^\d+$/.test(a)).map((s) => s.toUpperCase());
  const list = symbols.length ? symbols : cfg.watchlist;
  const { chart, data } = await core();
  await chart.setTimeframe({ timeframe: opt('timeframe', '5') });
  await chart.setSymbol({ symbol: list[0] });
  await pushScript('grok_desk_strategy');
  const rows = [];
  for (const sym of list) {
    await chart.setSymbol({ symbol: sym });
    await sleep(Number(process.env.TV_BACKTEST_WAIT_MS || 5000)); // le Strategy Tester recalcule
    const res = await data.getStrategyResults();
    const trades = await data.getTrades({ max_trades: 20 }).catch(() => ({ trades: [] }));
    const s = summarize(sym, res.metrics);
    rows.push({ ...s, error: res.error, lastTrades: trades.trades });
    console.log(`${sym.padEnd(6)} trades ${String(s.trades ?? '-').padStart(4)}  P&L ${String(s.netProfit ?? '-').padStart(9)} $  win ${s.winRatePct ?? '-'} %  PF ${s.profitFactor ?? '-'}  DD ${s.maxDrawdown ?? '-'}`);
  }
  mkdirSync(`${dataDir}backtests`, { recursive: true });
  const base = `${dataDir}backtests/backtest-${stamp()}`;
  writeFileSync(`${base}.json`, JSON.stringify({ config: { scanner: cfg.scanner, risk: cfg.risk }, results: rows }, null, 2));
  const md = ['# Backtest Grok Desk', '', `Généré le ${new Date().toISOString()} — UT ${opt('timeframe', '5')} min`, '',
    '| Symbole | Trades | P&L $ | P&L % | Gagnants % | Profit factor | Drawdown max |', '|---|---|---|---|---|---|---|',
    ...rows.map((r) => `| ${r.symbol} | ${r.trades ?? '-'} | ${r.netProfit ?? '-'} | ${r.netProfitPct ?? '-'} | ${r.winRatePct ?? '-'} | ${r.profitFactor ?? '-'} | ${r.maxDrawdown ?? '-'} |`)].join('\n');
  writeFileSync(`${base}.md`, md + '\n');
  console.log(`\nRapport : ${base}.md`);

  if (args.includes('--telegram')) {
    const tg = createTelegram(cfg.telegram);
    const total = rows.reduce((s, r) => s + (r.netProfit || 0), 0);
    await tg.send('chef', `<b>📊 Backtest TradingView (${rows.length} titres)</b>\n<code>${rows.map((r) => `${r.symbol.padEnd(6)} ${String(r.trades ?? '-').padStart(4)} tr  ${String(r.netProfit ?? '-').padStart(9)} $  PF ${r.profitFactor ?? '-'}`).map(escapeHtml).join('\n')}</code>\n<b>Total : ${Math.round(total)} $</b>`, { html: true });
    if (cfg.xai.apiKey) {
      const llm = createGrok(cfg.xai);
      for (const role of ['skeptic', 'risk']) {
        const raw = await llm.chat({ role, system: PERSONAS[role].system,
          user: `Voici les résultats du backtest de la stratégie du desk (mêmes règles que nos débats) :\n${JSON.stringify(rows.map(({ lastTrades, ...r }) => r))}\nRègles : ${JSON.stringify(cfg.risk)}\nDonne ton avis sur la robustesse (taille d'échantillon, profit factor, drawdown, dépendance à quelques titres) et une seule modification de paramètre à tester. Format {"message": "..."}`,
        });
        await tg.send(role, (parseJson(raw) || { message: raw }).message);
      }
    }
  }
}

switch (cmd) {
  case 'export': {
    mkdirSync(`${dataDir}pine`, { recursive: true });
    for (const n of ['grok_desk_indicator', 'grok_desk_strategy']) {
      writeFileSync(`${dataDir}pine/${n}.pine`, loadPine(n, cfg));
      console.log(`✓ ${dataDir}pine/${n}.pine`);
    }
    break;
  }
  case 'indicator': await pushScript('grok_desk_indicator'); break;
  case 'backtest': await backtest(); break;
  default:
    console.log('Usage : node grok-desk/src/tradingview.js export | indicator | backtest [SYM ...] [--timeframe 5] [--telegram]');
}
process.exit(0);
