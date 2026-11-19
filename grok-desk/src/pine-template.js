// Injecte la config de l'app dans les scripts Pine (lignes marquées « // @desk CLE »),
// pour que l'indicateur, la stratégie et les bots appliquent exactement les mêmes règles.
import { readFileSync } from 'fs';

export function pineParams(cfg) {
  return {
    CAPITAL: cfg.risk.capital,
    RVOL_DAYS: Number(process.env.PINE_RVOL_DAYS || 5),
    MIN_REL_VOLUME: cfg.scanner.minRelVolume,
    MIN_BAR_SPIKE: cfg.scanner.minBarSpike,
    MIN_RANGE_SPIKE: cfg.scanner.minRangeSpike,
    STOP_ATR: Number(process.env.PINE_STOP_ATR || 1.5),
    RR_TARGET: Number(process.env.PINE_RR_TARGET || 2),
    MIN_RR: cfg.risk.minRR,
    MAX_STOP_PCT: cfg.risk.maxStopPct,
    NO_ENTRY_FIRST_MIN: cfg.risk.noEntryFirstMinutes,
    NO_ENTRY_LAST_MIN: cfg.risk.noEntryLastMinutes,
    MAX_TRADES_PER_DAY: cfg.risk.maxTradesPerDay,
    RISK_PER_TRADE_PCT: cfg.risk.riskPerTradePct,
    MAX_POSITION_PCT: cfg.risk.maxPositionPct,
    DAILY_LOSS_LIMIT_PCT: cfg.risk.dailyLossLimitPct,
    FLATTEN_MIN: cfg.risk.flattenMinutesBeforeClose,
    MAX_EXT_ATR: Number(process.env.PINE_MAX_EXT_ATR || 3),
  };
}

const fmt = (v, wasFloat) => (wasFloat && Number.isInteger(v) ? v.toFixed(1) : String(v));

export function renderPine(source, params) {
  return source.split('\n').map((line) => {
    const m = line.match(/\/\/ @desk (\w+)\s*$/);
    if (!m || params[m[1]] === undefined) return line;
    const v = params[m[1]];
    if (m[1] === 'CAPITAL') return line.replace(/initial_capital = [\d.]+/, `initial_capital = ${v}`);
    return line.replace(/(input\.(int|float)\()([\d.]+)/, (_, pre, kind) => `${pre}${kind === 'int' ? Math.round(v) : fmt(v, true)}`);
  }).join('\n');
}

export function loadPine(name, cfg) {
  const src = readFileSync(new URL(`../pine/${name}.pine`, import.meta.url), 'utf8');
  return renderPine(src, pineParams(cfg));
}
