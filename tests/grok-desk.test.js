// Tests de Grok Desk (sans réseau) : horaires NYSE, scanner, règles de risque, gabarit Pine, tour de débat complet en mock.
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'fs';
import { marketStatus, nextOpen } from '../grok-desk/src/market-hours.js';
import { computeMetrics } from '../grok-desk/src/scanner.js';
import { evaluatePlan } from '../grok-desk/src/risk.js';
import { loadConfig } from '../grok-desk/src/config.js';
import { renderPine, pineParams } from '../grok-desk/src/pine-template.js';
import { mockProvider } from '../grok-desk/src/providers.js';
import { createMockGrok } from '../grok-desk/src/grok.js';
import { createTelegram } from '../grok-desk/src/telegram.js';
import { createJournal } from '../grok-desk/src/journal.js';
import { runRound } from '../grok-desk/src/debate.js';

const cfg = loadConfig({}, { mock: true, dryRun: true });
const emptyJournal = () => createJournal('/dev/null', { persist: false });
const okStatus = { open: true, minutesSinceOpen: 120, minutesToClose: 180, hhmm: '11:30', date: '2026-11-19' };

describe('grok-desk — horaires NYSE', () => {
  it('ouvert un jeudi à 10h00 NY (heure d’hiver)', () => assert.equal(marketStatus(new Date('2026-11-19T15:00:00Z')).open, true));
  it('fermé avant 9h30 et à 16h00', () => {
    assert.equal(marketStatus(new Date('2026-11-19T14:29:00Z')).open, false);
    assert.equal(marketStatus(new Date('2026-11-19T21:00:00Z')).open, false);
  });
  it('heure d’été : 9h30 NY = 13h30 UTC', () => assert.equal(marketStatus(new Date('2026-07-15T13:30:00Z')).open, true));
  it('fermé le week-end et à Thanksgiving', () => {
    assert.equal(marketStatus(new Date('2026-11-21T16:00:00Z')).reason, 'week-end');
    assert.equal(marketStatus(new Date('2026-11-26T16:00:00Z')).reason, 'jour férié');
  });
  it('demi-séance le lendemain de Thanksgiving (clôture 13h)', () => {
    assert.equal(marketStatus(new Date('2026-11-27T17:30:00Z')).open, true);
    assert.equal(marketStatus(new Date('2026-11-27T18:30:00Z')).open, false);
  });
  it('prochaine ouverture après Thanksgiving = vendredi 9h30 NY', () => {
    assert.equal(nextOpen(new Date('2026-11-25T22:00:00Z')).toISOString(), '2026-11-27T14:30:00.000Z');
  });
});

describe('grok-desk — scanner', () => {
  it('volume relatif à la même heure', () => {
    // 2 jours précédents à 100/bougie, aujourd'hui 300/bougie → RVOL 3
    const day = (d, v) => Array.from({ length: 6 }, (_, i) => ({ t: Date.parse(`2026-11-${d}T14:30:00Z`) / 1000 + i * 300, o: 10, h: 10.1, l: 9.9, c: 10, v }));
    const m = computeMetrics('X', [...day(17, 100), ...day(18, 100), ...day(19, 300)]);
    assert.equal(m.relVolume, 3);
    assert.equal(m.price, 10);
  });
});

describe('grok-desk — gestionnaire de risque', () => {
  const metrics = { price: 100, atr5m: 0.5 };
  const good = { ticker: 'X', direction: 'long', entry: 100, stop: 99, target: 102 };
  it('valide un plan correct et dimensionne la position', () => {
    const r = evaluatePlan(good, metrics, emptyJournal(), cfg.risk, okStatus);
    assert.equal(r.ok, true, r.violations.join());
    assert.equal(r.rr, 2);
    assert.equal(r.shares, 62); // 0,5 % de 25 000 $ = 125 $ / 1 $ = 125, plafonné à 25 % du capital = 62
  });
  it('refuse un R:R trop faible, un stop dans le bruit, un stop à l’envers', () => {
    assert.match(evaluatePlan({ ...good, target: 100.5 }, metrics, emptyJournal(), cfg.risk, okStatus).violations.join(), /ratio/);
    assert.match(evaluatePlan({ ...good, stop: 99.9, target: 100.3 }, metrics, emptyJournal(), cfg.risk, okStatus).violations.join(), /bruit/);
    assert.equal(evaluatePlan({ ...good, stop: 101 }, metrics, emptyJournal(), cfg.risk, okStatus).ok, false);
  });
  it('refuse près de la clôture et après la limite de perte du jour', () => {
    assert.match(evaluatePlan(good, metrics, emptyJournal(), cfg.risk, { ...okStatus, minutesToClose: 20 }).violations.join(), /clôture/);
    const j = emptyJournal();
    j.state.realizedPnl = -600;
    assert.match(evaluatePlan(good, metrics, j, cfg.risk, okStatus).violations.join(), /desk coupé/);
  });
});

describe('grok-desk — scripts Pine', () => {
  it('injecte la config dans les lignes @desk', () => {
    const src = readFileSync(new URL('../grok-desk/pine/grok_desk_strategy.pine', import.meta.url), 'utf8');
    const out = renderPine(src, { ...pineParams(cfg), MIN_RR: 2, CAPITAL: 10000, NO_ENTRY_FIRST_MIN: 30 });
    assert.match(out, /minRR\s+= input\.float\(2\.0,/);
    assert.match(out, /initial_capital = 10000,/);
    assert.match(out, /noFirst\s+= input\.int\(30,/);
    assert.doesNotMatch(out, /\/\*/); // Pine n'a pas de commentaires de bloc
  });
});

describe('grok-desk — tour de débat (mock)', () => {
  it('les six bots parlent, le Risque refuse puis valide, le Chef ouvre un ordre papier', async () => {
    const tg = createTelegram(cfg.telegram, { dryRun: true, log: () => {} });
    const journal = emptyJournal();
    const r = await runRound({ cfg, llm: createMockGrok(), tg, provider: mockProvider(cfg.watchlist), journal, status: okStatus });
    const speakers = tg.sent.map((m) => m.bot);
    for (const b of ['scanner', 'news', 'planner', 'risk', 'skeptic', 'chef']) assert.ok(speakers.includes(b), b);
    assert.equal(speakers.filter((b) => b === 'planner').length, 2); // révision après refus
    assert.equal(r.decision, 'GO');
    assert.equal(journal.active().length, 1);
  });
  it('le Chef ne peut pas forcer un GO quand le Risque refuse', async () => {
    const tg = createTelegram(cfg.telegram, { dryRun: true, log: () => {} });
    const llm = { async chat({ role, ctx }) {
      if (role === 'chef') return '{"decision":"GO","message":"On y va quand même"}';
      if (role === 'planner') return JSON.stringify({ direction: 'long', entry: ctx.focus.price, stop: ctx.focus.price * 0.9, target: ctx.focus.price * 1.3, message: 'yolo' });
      if (role === 'scanner') return JSON.stringify({ focus: ctx.candidates[0].symbol, message: 'x' });
      return '{"verdict":"APPROVE","message":"ok"}';
    } };
    const r = await runRound({ cfg, llm, tg, provider: mockProvider(cfg.watchlist), journal: emptyJournal(), status: okStatus });
    assert.equal(r.riskCheck.ok, false); // stop à 10 % > 3 % max
    assert.equal(r.decision, 'NO_GO');
  });
});
