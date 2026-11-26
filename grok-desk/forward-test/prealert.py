"""Pré-alerte du test papier de nuit : regarde la bougie 5 min EN COURS (reconstruite avec les bougies 1 min Axi)
et prévient sur Telegram si elle ressemble déjà à un signal de la règle validée. Ce n'est PAS un signal :
la carte officielle n'est envoyée qu'à la clôture de la bougie (night_pass.py). Aucun ordre n'est passé.
Usage : python3 -I grok-desk/forward-test/prealert.py <fichier JSON des bougies M1 Axi> [--dry]
Conditions (bougie en formation) : début entre 00h45 et 03h10 Paris · amplitude ≥ 1,5 ATR14 (5 min) · bougie dans le sens
de la clôture provisoire et du bon côté du VWAP de séance · ≤ 3 ATR du VWAP · aucune position ouverte · nuit non arrêtée par un SL."""
import json, os, subprocess, sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
H = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(H))
PAR = ZoneInfo('Europe/Paris'); STATE = os.path.join(H, 'live', 'state.json'); CANDLES = os.path.join(H, 'live', 'candles.txt')
MIN_ATR = 1.5

# bougies 5 min clôturées → ATR (Wilder, comme month.py) et VWAP de séance (moyenne hlc3, remise à zéro après un trou > 30 min)
B = []
for l in open(CANDLES):
    p = l.split()
    if len(p) == 6: B.append((datetime.strptime(p[0] + p[1], '%Y%m%d%H%M').replace(tzinfo=timezone.utc), *map(float, p[2:])))
atr = None; trs = []; s = n = 0; prev = None
for t, o, h, l, c in B:
    if prev is None or t - prev[0] > timedelta(minutes=30): s = n = 0
    tr = h - l if prev is None else max(h - l, abs(h - prev[4]), abs(l - prev[4]))
    trs.append(tr)
    atr = (sum(trs[-14:]) / 14 if len(trs) >= 14 else None) if atr is None else (atr * 13 + tr) / 14
    s += (h + l + c) / 3; n += 1; prev = (t, o, h, l, c)
vwap = s / n

m1 = json.load(open(sys.argv[1]))
m1 = sorted(((datetime.fromisoformat(x['time']), x['open'], x['high'], x['low'], x['close']) for x in m1), key=lambda x: x[0])
last = m1[-1][0]
bucket = last.replace(minute=last.minute - last.minute % 5, second=0)
cur = [x for x in m1 if x[0] >= bucket]
if not cur or bucket <= prev[0]:
    print('pas de bougie 5 min en formation'); sys.exit(0)
o, h, l, c = cur[0][1], max(x[2] for x in cur), min(x[3] for x in cur), cur[-1][4]
tr = max(h - l, abs(h - prev[4]), abs(l - prev[4]))
lp = bucket.astimezone(PAR); pm = lp.hour * 60 + lp.minute
d = 1 if (c > o and c > vwap) else -1 if (c < o and c < vwap) else 0

st = json.load(open(STATE))
since = st.get('since', '')
night = {k: v for k, v in st['trades'].items() if k >= since}
busy = any(not v.get('done') for v in night.values())
stopped = any(v.get('done') and v.get('r', 0) < -0.5 for v in night.values())
key = bucket.isoformat()
why = []
if not (45 <= pm <= 190): why.append('hors fenêtre de signal')
if tr / atr < MIN_ATR: why.append(f'amplitude {tr / atr:.2f} ATR')
if d == 0: why.append('pas de sens net / mauvais côté du VWAP')
if abs(c - vwap) > 3 * atr: why.append('trop loin du VWAP')
if busy: why.append('position déjà ouverte')
if stopped: why.append('nuit arrêtée après un SL')
if key in st.get('prealerts', []): why.append('déjà prévenu')
print(f"bougie {lp:%H:%M} Paris ({len(cur)} min) · amplitude {tr:.2f} $ = {tr / atr:.2f} ATR · prix {c} · VWAP {vwap:.2f} · " + ('→ PRÉ-ALERTE' if not why else 'rien : ' + ', '.join(why)))
if why: sys.exit(0)

end = (bucket + timedelta(minutes=5)).astimezone(PAR)
msg = (f"⚠️ Pré-alerte XAUUSD — {'ACHAT' if d > 0 else 'VENTE'} possible à la clôture de {end:%H:%M}\n"
       f"Bougie {lp:%H:%M} en formation ({len(cur)} min) : amplitude {tr / atr:.1f} ATR (seuil 2), prix {c:.2f} {'au-dessus' if d > 0 else 'sous'} du VWAP {vwap:.2f}\n"
       f"Niveaux indicatifs si confirmé : entrée ≈ {c:.2f} · SL {c - d * 5:.2f} · TP1 {c + d * 5:.2f} · TP2 {c + d * 10:.2f} · TP3 {c + d * 15:.2f}\n"
       "Pas encore un signal : attendre la carte officielle à la clôture. Test papier, aucun ordre passé.")
if '--dry' in sys.argv:
    print(msg)
else:
    env = dict(os.environ, NODE_USE_ENV_PROXY='1', NODE_NO_WARNINGS='1')
    print(subprocess.run(['node', os.path.join(ROOT, 'grok-desk/src/notify.js'), '--text', msg], capture_output=True, text=True, env=env, cwd=ROOT).stdout.strip()[-80:])
    st.setdefault('prealerts', []).append(key)
    json.dump(st, open(STATE, 'w'), indent=1)
