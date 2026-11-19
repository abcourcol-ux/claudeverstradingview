// Configuration de Grok Desk — tout passe par des variables d'environnement (.env).
import { existsSync, readFileSync } from 'fs';

export function loadEnvFile(path) {
  if (!existsSync(path)) return;
  for (const line of readFileSync(path, 'utf8').split('\n')) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/);
    if (!m || line.trim().startsWith('#')) continue;
    let v = m[2];
    if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) v = v.slice(1, -1);
    if (process.env[m[1]] === undefined) process.env[m[1]] = v;
  }
}

const num = (v, d) => (v === undefined || v === '' || Number.isNaN(Number(v)) ? d : Number(v));
const list = (v, d) => (v ? v.split(',').map((s) => s.trim().toUpperCase()).filter(Boolean) : d);

export function loadConfig(env = process.env, flags = {}) {
  const mock = flags.mock ?? env.DESK_MOCK === '1';
  return {
    mock,
    dryRun: flags.dryRun ?? env.DESK_DRY_RUN === '1',
    xai: {
      apiKey: env.XAI_API_KEY || '',
      baseUrl: (env.XAI_BASE_URL || 'https://api.x.ai/v1').replace(/\/$/, ''),
      model: env.GROK_MODEL || 'grok-4',
      // Modèle par bot optionnel, ex. GROK_MODEL_SCANNER=grok-4-fast
      models: {
        scanner: env.GROK_MODEL_SCANNER, news: env.GROK_MODEL_NEWS, planner: env.GROK_MODEL_PLANNER,
        risk: env.GROK_MODEL_RISK, skeptic: env.GROK_MODEL_SKEPTIC, chef: env.GROK_MODEL_CHEF,
      },
      maxTokens: env.GROK_MAX_TOKENS ? Number(env.GROK_MAX_TOKENS) : undefined,
      timeoutMs: num(env.GROK_TIMEOUT_MS, 90_000),
    },
    telegram: {
      chatId: env.TELEGRAM_CHAT_ID || '',
      // Un token par bot = six identités distinctes dans le groupe.
      tokens: {
        scanner: env.TELEGRAM_TOKEN_SCANNER, news: env.TELEGRAM_TOKEN_NEWS, planner: env.TELEGRAM_TOKEN_PLANNER,
        risk: env.TELEGRAM_TOKEN_RISK, skeptic: env.TELEGRAM_TOKEN_SKEPTIC, chef: env.TELEGRAM_TOKEN_CHEF,
      },
      // Repli : un seul bot qui préfixe chaque message par le nom du personnage.
      fallbackToken: env.TELEGRAM_TOKEN || '',
      typingDelayMs: num(env.DESK_TYPING_DELAY_MS, mock ? 0 : 2500),
    },
    watchlist: list(env.DESK_WATCHLIST, ['AAPL', 'MSFT', 'NVDA', 'TSLA', 'AMD', 'META', 'AMZN', 'GOOGL', 'NFLX', 'PLTR', 'COIN', 'SMCI', 'AVGO', 'MU', 'SOFI']),
    cycleMinutes: num(env.DESK_CYCLE_MINUTES, 15),
    scanner: {
      minRelVolume: num(env.SCAN_MIN_REL_VOLUME, 2.0),
      minBarSpike: num(env.SCAN_MIN_BAR_SPIKE, 3.0),
      minPrice: num(env.SCAN_MIN_PRICE, 5),
      maxCandidates: num(env.SCAN_MAX_CANDIDATES, 3),
    },
    risk: {
      capital: num(env.RISK_CAPITAL, 25_000),
      riskPerTradePct: num(env.RISK_PER_TRADE_PCT, 0.5),
      minRR: num(env.RISK_MIN_RR, 1.5),
      maxStopPct: num(env.RISK_MAX_STOP_PCT, 3),
      maxEntryDistancePct: num(env.RISK_MAX_ENTRY_DISTANCE_PCT, 1.5),
      maxPositionPct: num(env.RISK_MAX_POSITION_PCT, 25),
      maxOpenPositions: num(env.RISK_MAX_OPEN_POSITIONS, 3),
      maxTradesPerDay: num(env.RISK_MAX_TRADES_PER_DAY, 5),
      dailyLossLimitPct: num(env.RISK_DAILY_LOSS_LIMIT_PCT, 2),
      noEntryFirstMinutes: num(env.RISK_NO_ENTRY_FIRST_MIN, 15),
      noEntryLastMinutes: num(env.RISK_NO_ENTRY_LAST_MIN, 45),
      flattenMinutesBeforeClose: num(env.RISK_FLATTEN_MIN_BEFORE_CLOSE, 5),
      pendingExpiryMinutes: num(env.RISK_PENDING_EXPIRY_MIN, 45),
    },
    extraHolidays: list(env.DESK_EXTRA_HOLIDAYS, []),
    journalPath: env.DESK_JOURNAL_PATH || new URL('../data/journal.json', import.meta.url).pathname,
  };
}
