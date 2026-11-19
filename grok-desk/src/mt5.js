#!/usr/bin/env node
// Vérifications MetaTrader 5 (aucun ordre passé) :
//   node grok-desk/src/mt5.js check            → compte connecté (démo/réel), équité, symboles de MT5_SYMBOLS
//   node grok-desk/src/mt5.js symbols "*NVIDIA*" → cherche des symboles (filtre MT5, jokers *)
import { fileURLToPath } from 'url';
import { loadConfig, loadEnvFile } from './config.js';
import { createMt5Broker, parseSymbolMap } from './broker-mt5.js';

loadEnvFile(fileURLToPath(new URL('../.env', import.meta.url)));
const cfg = loadConfig();
const broker = createMt5Broker(cfg.mt5);
const [cmd, arg] = process.argv.slice(2);
try {
  const acc = await broker.connect();
  console.log(`Compte ${acc.login} sur ${acc.server} — ${acc.mode.toUpperCase()} — équité ${acc.equity} ${acc.currency}, levier 1:${acc.leverage}`);
  if (cmd === 'symbols') {
    for (const s of await broker.listSymbols(arg || '*')) console.log(`${s.symbol.padEnd(22)} ${s.description}  [${s.path}]`);
  } else {
    const map = parseSymbolMap(cfg.mt5.symbolMap);
    if (!Object.keys(map).length) console.log('MT5_SYMBOLS est vide : renseigne-le dans grok-desk/.env (ex. NVDA:NVIDIA+,TSLA:TESLA+)');
    for (const t of Object.keys(map)) {
      try {
        const i = await broker.symbolInfo(t);
        console.log(`✓ ${t.padEnd(6)} → ${i.symbol.padEnd(16)} ${i.description} · bid ${i.bid} / ask ${i.ask} · lot ${i.contract_size} · min ${i.volume_min} pas ${i.volume_step}`);
      } catch (e) { console.log(`✗ ${t.padEnd(6)} → ${map[t]} : ${e.message}`); }
    }
  }
} catch (e) {
  console.error(`✗ ${e.message}`);
  process.exitCode = 1;
} finally { broker.stop(); }
