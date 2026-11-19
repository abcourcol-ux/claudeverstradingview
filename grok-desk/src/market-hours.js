// Horaires du NYSE (9h30–16h00, heure de New York), week-ends, jours fériés et demi-séances.
const fmt = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', weekday: 'short', hourCycle: 'h23',
});

export function nyParts(d = new Date()) {
  const p = Object.fromEntries(fmt.formatToParts(d).map((x) => [x.type, x.value]));
  return { date: `${p.year}-${p.month}-${p.day}`, weekday: p.weekday, minutes: Number(p.hour) * 60 + Number(p.minute), hhmm: `${p.hour}:${p.minute}` };
}

// Calendrier officiel NYSE (à compléter chaque année, ou via DESK_EXTRA_HOLIDAYS).
export const NYSE_HOLIDAYS = new Set([
  '2026-01-01', '2026-01-19', '2026-02-16', '2026-04-03', '2026-05-25', '2026-06-19',
  '2026-07-03', '2026-09-07', '2026-11-26', '2026-12-25',
  '2027-01-01', '2027-01-18', '2027-02-15', '2027-03-26', '2027-05-31', '2027-06-18',
  '2027-07-05', '2027-09-06', '2027-11-25', '2027-12-24',
]);
export const NYSE_EARLY_CLOSES = new Set(['2026-11-27', '2026-12-24', '2027-11-26']); // clôture 13h00

const OPEN = 9 * 60 + 30;

export function marketStatus(d = new Date(), extraHolidays = []) {
  const ny = nyParts(d);
  const base = { ...ny, open: false, minutesSinceOpen: null, minutesToClose: null };
  if (ny.weekday === 'Sat' || ny.weekday === 'Sun') return { ...base, reason: 'week-end' };
  if (NYSE_HOLIDAYS.has(ny.date) || extraHolidays.includes(ny.date)) return { ...base, reason: 'jour férié' };
  const close = NYSE_EARLY_CLOSES.has(ny.date) ? 13 * 60 : 16 * 60;
  if (ny.minutes < OPEN) return { ...base, reason: 'pré-marché' };
  if (ny.minutes >= close) return { ...base, reason: 'après clôture' };
  return { ...base, open: true, reason: 'séance', minutesSinceOpen: ny.minutes - OPEN, minutesToClose: close - ny.minutes };
}

export function nextOpen(d = new Date(), extraHolidays = []) {
  const t = new Date(Math.floor(d.getTime() / 60_000) * 60_000 + 60_000);
  for (let i = 0; i < 60 * 24 * 12; i++, t.setTime(t.getTime() + 60_000)) {
    if (marketStatus(t, extraHolidays).open) return t;
  }
  return null;
}
