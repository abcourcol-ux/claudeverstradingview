"""Rejoue la stratégie Grok Desk (mêmes règles que « Grok Desk Strategy » v3.0) sur des bougies M5 Axi.
Usage : python3 month.py [--prudent] [--k 1.5] [--pips 50] [--nobe] [--window ny|nuit|both] [--list]
Données : data/c*.txt  (YYYYMMDD HHMM open high low close, UTC)."""
import glob, os, sys
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
H = os.path.dirname(os.path.abspath(__file__)); A = sys.argv
def arg(n, d): return type(d)(A[A.index(n) + 1]) if n in A else d
K = arg('--k', 1.5); PIPS = arg('--pips', 50.0); PRUDENT = '--prudent' in A; BE = '--nobe' not in A
WIN = arg('--window', 'both'); BEAFTER = arg('--beafter', 1); BEOFF = arg('--beoff', 0.0); TPN = arg('--tpn', 3); MAXDAY = arg('--maxday', 5); MAXSL = arg('--maxsl', 99); TREND = arg('--trend', 0); CWIN = arg('--win', ''); RANGE_MIN = arg('--range', 2.0); EXT = arg('--ext', 3.0)
NY, PAR = ZoneInfo('America/New_York'), ZoneInfo('Europe/Paris')
rows = {}
for f in sorted(f for d in arg('--data', 'data').split(',') for f in glob.glob(os.path.join(H, d, '*.txt'))):
    for l in open(f):
        p = l.split()
        if len(p) == 6: rows[p[0] + p[1]] = (datetime.strptime(p[0] + p[1], '%Y%m%d%H%M').replace(tzinfo=timezone.utc), *map(float, p[2:]))
B = [rows[k] for k in sorted(rows)]
# fenêtres : (nom, tz, début, fin) en heure locale
TK = ZoneInfo('Asia/Tokyo')
ALL = {'ny': [('NY', NY, (9, 30), (16, 0))], 'nuit': [('Nuit', PAR, (0, 30), (4, 0))],
       'asie': [('Asie', TK, (9, 0), (18, 0))],      # séance asiatique : 9h–18h Tokyo = 00h–09h UTC (01h–10h Paris en hiver)
       'tokyo': [('Tokyo', TK, (9, 0), (15, 0))]}    # bourse de Tokyo : 9h–15h Tokyo = 00h–06h UTC
ALL['both'] = ALL['ny'] + ALL['nuit']
WINDOWS = ALL[WIN] if not CWIN else [('Nuit', PAR, (int(CWIN[:2]), int(CWIN[2:4])), (int(CWIN[5:7]), int(CWIN[7:9])))]
def window_of(t):
    for name, tz, a, z in WINDOWS:
        lt = t.astimezone(tz); s = lt.replace(hour=a[0], minute=a[1]); e = lt.replace(hour=z[0], minute=z[1])
        if s <= lt < e: return name, (lt - s).total_seconds() / 60, (e - lt).total_seconds() / 60 - 5  # minToClose sur time_close
    return None, 0, 0
atr = None; trs = []; sumpx = 0; npx = 0; prev = None
pos = None; trades = []; day_n = 0; day_r = 0.0; sess = None
for i, (t, o, h, l, c) in enumerate(B):
    newsess = prev is None or (t - prev[0]) > timedelta(minutes=30)
    tr = h - l if prev is None else max(h - l, abs(h - prev[4]), abs(l - prev[4]))
    atr_prev = atr
    trs.append(tr)
    if atr is None:
        if len(trs) == 14: atr = sum(trs) / 14
    else: atr = (atr * 13 + tr) / 14
    if newsess: sumpx = 0; npx = 0; day_n = 0; day_r = 0.0; day_sl = 0; sess = t
    ema = c if i == 0 else ema + 2 / (TREND + 1) * (c - ema) if TREND else 0
    sumpx += (h + l + c) / 3; npx += 1; vwap = sumpx / npx
    w, since, toclose = window_of(t)
    # gestion de la position ouverte
    if pos and i >= pos['fill']:
        if i == pos['fill']: pos['e'] = o; pos['tfill'] = t
        d = pos['d']
        pts = ([o, h, l, c] if d < 0 else [o, l, h, c]) if PRUDENT else ([o, h, l, c] if abs(o - h) < abs(o - l) else [o, l, h, c])
        done = None
        for a, z in zip(pts, pts[1:]):
            while not done:
                lo, hi = min(a, z), max(a, z); ev = []
                if lo <= pos['st'] <= hi: ev.append((abs(pos['st'] - a), 'sl', pos['st']))
                if pos['hit'] < TPN:
                    tp = pos['e0'] + d * (pos['hit'] + 1) * pos['R']
                    if lo <= tp <= hi: ev.append((abs(tp - a), 'tp', tp))
                if not ev: break
                ev.sort(); _, k, p = ev[0]
                if k == 'sl':
                    pos['r'] += (TPN - pos['hit']) / TPN * d * (p - pos['e']) / pos['R']; done = 'SL' if pos['hit'] == 0 else ('BE' if BE else 'SL') + f" après TP{pos['hit']}"
                else:
                    pos['hit'] += 1; pos['r'] += d * (p - pos['e']) / pos['R'] / TPN
                    if pos['hit'] == BEAFTER and BE: pos['st'] = pos['e0'] - d * BEOFF
                    if pos['hit'] == TPN: done = 'TP final'
                a = p
            if done: break
        if not done and (w != pos['w'] or toclose <= 5):
            pos['r'] += (TPN - pos['hit']) / TPN * d * (c - pos['e']) / pos['R']; done = f"fin de fenêtre ({pos['hit']} TP)"
        if done:
            pos['out'] = done; pos['t1'] = t; day_r += pos['r']; day_sl += pos['r'] < -0.5; trades.append(pos); pos = None
        prev = (t, o, h, l, c); continue
    if pos is None and w and atr_prev and since >= 15 and toclose >= 45 and day_n < MAXDAY and day_r > -4 and day_sl < MAXSL and (i + 1 < len(B) or '--json' in A):
        rs = tr / atr_prev
        d = 1 if (rs >= RANGE_MIN and c > vwap and c > o) else -1 if (rs >= RANGE_MIN and c < vwap and c < o) else 0
        if TREND and d and d * (c - ema) < 0: d = 0  # filtre de tendance : seulement dans le sens de l'EMA
        if d and abs(c - vwap) <= EXT * atr:
            R = max(PIPS * 0.1, K * atr)
            pos = dict(w=w, d=d, t=t, fill=i + 1, e0=c, e=c, R=R, st=c - d * R, hit=0, r=0.0, atr=atr); day_n += 1
    prev = (t, o, h, l, c)
# slippage d'entrée : l'entrée réelle est l'ouverture suivante, niveaux fixés au signal (comme Pine)
tot = sum(x['r'] for x in trades); win = [x for x in trades if x['r'] > 0.01]; loss = [x for x in trades if x['r'] < -0.01]
gp = sum(x['r'] for x in win); gl = -sum(x['r'] for x in loss)
print(f"Période {B[0][0]:%d/%m %H:%M} → {B[-1][0]:%d/%m %H:%M} UTC · {len(B)} bougies · SL max({PIPS:g} pips ; {K:g} ATR) · BE {'oui' if BE else 'non'} · comptage {'prudent' if PRUDENT else 'probable'} · fenêtres {WIN}")
print(f"Trades {len(trades)} · gagnants {len(win)} · perdants {len(loss)} · nuls {len(trades)-len(win)-len(loss)} · total {tot:+.2f}R = {tot*25:+.0f} $ · PF {gp/gl if gl else float('inf'):.2f}")
eq = 0; peak = 0; dd = 0
for x in trades: eq += x['r']; peak = max(peak, eq); dd = max(dd, peak - eq)
print(f"Drawdown max {dd:.2f}R = {dd*25:.0f} $")
for name in ('NY', 'Nuit', 'Asie', 'Tokyo'):
    s = [x for x in trades if x['w'] == name]
    if s: print(f"  {name:4} : {len(s)} trades, {sum(x['r'] for x in s):+.2f}R, gagnants {sum(1 for x in s if x['r']>0.01)}")
for lbl, f in (('achats', 1), ('ventes', -1)):
    s = [x for x in trades if x['d'] == f]
    if s: print(f"  {lbl:6}: {len(s)} trades, {sum(x['r'] for x in s):+.2f}R")
if '--list' in A:
    for x in trades:
        lt = x['t'].astimezone(PAR)
        print(f"{lt:%a %d/%m %H:%M} Paris  {x['w']:4} {'ACHAT' if x['d']>0 else 'VENTE'}  entrée {x['e']:.2f}  SL {x['e0']-x['d']*x['R']:.2f} ({x['R']*10:.0f} pips)  TP1 {x['e0']+x['d']*x['R']:.2f}  → {x['out']:22} {x['r']:+.2f}R")

if '--json' in A:  # mode direct : état pour le test papier
    import json as _j
    def ser(x, st):
        d = {k: (v.isoformat() if hasattr(v, 'isoformat') else v) for k, v in x.items() if k != 'fill'}
        d['status'] = st; d['sl'] = round(x['e0'] - x['d'] * x['R'], 2); d['tp1'] = round(x['e0'] + x['d'] * x['R'], 2)
        d['tp2'] = round(x['e0'] + 2 * x['d'] * x['R'], 2); d['tpf'] = round(x['e0'] + 3 * x['d'] * x['R'], 2); return d
    out = [ser(x, 'closed') for x in trades]
    if pos: out.append(ser(pos, 'open' if 'tfill' in pos else 'pending'))
    print('JSON' + _j.dumps({'last': B[-1][0].isoformat(), 'price': B[-1][4], 'atr': atr, 'trades': out}))
