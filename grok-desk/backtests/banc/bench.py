"""Banc d'essai : rejoue TOUJOURS les mêmes trades de référence avec plusieurs règles de gestion.
Usage : python3 bench.py            (toutes les variantes)
Ajouter les nouveaux trades dans trades-reference.json (et les bougies M5 du jour) pour enrichir le banc."""
import json, os
H = os.path.dirname(os.path.abspath(__file__))
REF = json.load(open(os.path.join(H, 'trades-reference.json')))
END = '2100'  # clôture forcée 21h00 UTC (fin de la séance de NY ; 22h Paris)

def load(day):
    p = os.path.join(H, REF['candles'][day]); out = []
    for l in open(p):
        t, o, h, lo, c = l.split(); out.append((t, float(o), float(h), float(lo), float(c)))
    return out

def order(t):  # ordre chronologique depuis 23h00 UTC la veille
    m = int(t[:2]) * 60 + int(t[2:]); return (m - 23 * 60) % 1440

def path(b, prudent, d):
    _, o, h, l, c = b
    if prudent:  # pire cas : d'abord vers le SL, puis vers les TP
        return [o, h, l, c] if d < 0 else [o, l, h, c]
    return [o, h, l, c] if abs(o - h) < abs(o - l) else [o, l, h, c]

def run(tr, v, prudent):
    B = load(tr['day']); d = tr['dir']; e = tr['entry']
    R = max(v['pips'] * 0.1, v['k'] * tr['atr'])
    st = e - d * R; tps = [e + d * x * R for x in v['tps']]; w = v['w']
    hit = 0; r = 0.0; filled = tr['type'] == 'market'; t0 = None
    for b in B:
        if order(b[0]) < order(tr['from']): continue
        if not filled and 'until' in tr and order(b[0]) >= order(tr['until']): return dict(r=0, out='non déclenché', t0=None, t1=None, R=R)
        pts = path(b, prudent, d)
        for a, z in zip(pts, pts[1:]):
            if not filled:
                if min(a, z) <= e <= max(a, z): filled = True; t0 = b[0]; a = e
                else: continue
            t0 = t0 or b[0]
            while True:
                lo, hi = min(a, z), max(a, z); ev = []
                if lo <= st <= hi: ev.append((abs(st - a), 'sl', st))
                if hit < len(tps) and lo <= tps[hit] <= hi: ev.append((abs(tps[hit] - a), 'tp', tps[hit]))
                if not ev: break
                ev.sort(); _, k, p = ev[0]
                if k == 'sl':
                    r += (1 - sum(w[:hit])) * d * (p - e) / R
                    return dict(r=r, out=('SL' if hit == 0 else 'BE' if v['be'] and abs(st - e) < 1e-9 else 'SL') + f' après {hit} TP', t0=t0, t1=b[0], R=R)
                r += w[hit] * d * (p - e) / R; hit += 1
                if hit == 1 and v['be']: st = e
                if hit == len(tps): return dict(r=r, out='TP final', t0=t0, t1=b[0], R=R)
                a = p
        if filled and order(b[0]) >= order(END):
            r += (1 - sum(w[:hit])) * d * (b[4] - e) / R
            return dict(r=r, out=f'fin de séance après {hit} TP', t0=t0, t1=b[0], R=R)
    return dict(r=r, out='ouvert', t0=t0, t1=None, R=R)

THIRDS = dict(tps=[1, 2, 3], w=[1/3, 1/3, 1/3])
VARIANTS = {
    'A  50 pips fixes': dict(pips=50, k=0, be=True, **THIRDS),
    'B  1,5 ATR': dict(pips=0, k=1.5, be=True, **THIRDS),
    'C  max(50 pips ; 1,5 ATR)  ← règle actuelle': dict(pips=50, k=1.5, be=True, **THIRDS),
    'D  max(50 pips ; 1,2 ATR)': dict(pips=50, k=1.2, be=True, **THIRDS),
    'E  max(50 pips ; 2 ATR)': dict(pips=50, k=2.0, be=True, **THIRDS),
    'F  règle actuelle sans BE': dict(pips=50, k=1.5, be=False, **THIRDS),
    'G  règle actuelle, TP 1R/2R (moitié-moitié)': dict(pips=50, k=1.5, be=True, tps=[1, 2], w=[.5, .5]),
}

def bench(one_at_a_time=True):
    rows = []
    for name, v in VARIANTS.items():
        for prudent in (False, True):
            res = []; busy_until = None
            for tr in REF['trades']:
                x = run(tr, v, prudent)
                if one_at_a_time and x['t0'] and busy_until and order(x['t0']) <= order(busy_until):
                    x = dict(r=0, out='bloqué (un trade déjà ouvert)', t0=None, t1=None, R=x['R'])
                if x['t0']: busy_until = x['t1'] or END
                res.append(x)
            rows.append((name, prudent, res))
    return rows

if __name__ == '__main__':
    ids = [t['id'] for t in REF['trades']]
    print('Trades de référence :', ', '.join(ids), '| une seule position à la fois | risque 25 $')
    for name, prudent, res in bench():
        tot = sum(x['r'] for x in res); n = sum(1 for x in res if x['t0']); g = sum(1 for x in res if x['r'] > 0)
        print(f"\n{name} — {'comptage prudent (SL d abord dans la bougie)' if prudent else 'comptage probable'}")
        for t, x in zip(ids, res): print(f"   {t:8} SL {x['R']*10:4.0f} pips  {x['out']:32} {x['r']:+.2f}R")
        print(f"   TOTAL {tot:+.2f}R = {tot*25:+.0f} $  ({g}/{n} gagnants)")
