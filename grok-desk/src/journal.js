// Journal de paper trading : positions, P&L du jour, historique. Persisté en JSON.
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs';
import { dirname } from 'path';
import { round } from './scanner.js';

export function createJournal(path, { persist = true } = {}) {
  let state = { date: null, positions: [], closed: [], tradesToday: 0, realizedPnl: 0, history: [] };
  if (persist && existsSync(path)) { try { state = { ...state, ...JSON.parse(readFileSync(path, 'utf8')) }; } catch {} }
  const save = () => { if (persist) { mkdirSync(dirname(path), { recursive: true }); writeFileSync(path, JSON.stringify(state, null, 2)); } };

  return {
    get state() { return state; },
    get positions() { return state.positions; },
    get tradesToday() { return state.tradesToday; },
    get realizedPnl() { return state.realizedPnl; },
    rollDay(date) {
      if (state.date === date) return false;
      if (state.date) state.history.push({ date: state.date, pnl: round(state.realizedPnl), trades: state.closed.length });
      state = { ...state, date, positions: state.positions.filter((p) => p.status !== 'closed' && p.status !== 'expired'), closed: [], tradesToday: 0, realizedPnl: 0 };
      save();
      return true;
    },
    open(plan, check, now = new Date()) {
      const pos = {
        id: `${plan.ticker}-${now.getTime()}`, ticker: plan.ticker, direction: plan.direction,
        entry: Number(plan.entry), stop: Number(plan.stop), target: Number(plan.target), shares: check.shares,
        status: 'pending', createdAt: now.toISOString(), filledAt: null, exit: null, pnl: null,
      };
      state.positions.push(pos);
      state.tradesToday++;
      save();
      return pos;
    },
    // Position réellement exécutée chez le courtier (MT5).
    openFilled(plan, fill, now = new Date()) {
      const pos = {
        id: `${plan.ticker}-${fill.ticket}`, ticker: plan.ticker, direction: plan.direction, broker: 'mt5',
        ticket: fill.ticket, brokerSymbol: fill.symbol, lots: fill.lots,
        entry: fill.price, stop: Number(plan.stop), target: Number(plan.target), shares: fill.shares,
        status: 'open', createdAt: now.toISOString(), filledAt: now.toISOString(), exit: null, pnl: null,
      };
      state.positions.push(pos);
      state.tradesToday++;
      save();
      return pos;
    },
    markClosed(pos, { price, pnl, reason }) {
      pos.status = 'closed';
      pos.exit = round(price);
      pos.pnl = round(pnl);
      pos.reason = reason;
      state.realizedPnl = round(state.realizedPnl + pos.pnl);
      state.closed.push({ ...pos });
      save();
      return { type: reason, price, pnl: pos.pnl };
    },
    // Met à jour une position avec le dernier prix ; renvoie les événements (fill, stop, target, expiry).
    update(pos, price, now, expiryMin) {
      const ev = [];
      const long = pos.direction === 'long';
      if (pos.status === 'pending') {
        const touched = long ? price <= pos.entry * 1.001 : price >= pos.entry * 0.999;
        if (touched) { pos.status = 'open'; pos.filledAt = now.toISOString(); ev.push({ type: 'fill', price }); }
        else if ((now - new Date(pos.createdAt)) / 60_000 > expiryMin) { pos.status = 'expired'; ev.push({ type: 'expired', price }); }
      }
      if (pos.status === 'open') {
        if (long ? price <= pos.stop : price >= pos.stop) ev.push(this.close(pos, pos.stop, 'stop'));
        else if (long ? price >= pos.target : price <= pos.target) ev.push(this.close(pos, pos.target, 'target'));
      }
      save();
      return ev;
    },
    close(pos, price, reason) {
      pos.status = 'closed';
      pos.exit = round(price);
      pos.pnl = round((pos.direction === 'long' ? price - pos.entry : pos.entry - price) * pos.shares);
      pos.reason = reason;
      state.realizedPnl = round(state.realizedPnl + pos.pnl);
      state.closed.push({ ...pos });
      save();
      return { type: reason, price, pnl: pos.pnl };
    },
    active() { return state.positions.filter((p) => p.status === 'pending' || p.status === 'open'); },
    save,
  };
}
