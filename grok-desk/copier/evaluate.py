"""Résultat papier des signaux du groupe, sur bougies M5 Axi (comptage prudent).
Usage : python3 grok-desk/copier/evaluate.py [--signals copier/inbox.jsonl] [--candles XAUUSD=forward-test/live/candles.txt,XAGUSD=chemin]
Règles de simulation (ce que ferait un copieur) :
  - entrée au prix annoncé à l'heure du message (signal « NOW ») ; ignorée si le prix n'a pas été touché dans les 15 min ;
  - sortie par tiers aux TP1 / TP2 / TP3 ; SL au niveau annoncé ;
  - « SL à BE » (réponse au signal) : stop au prix d'entrée à partir de l'heure du message ;
  - « clôture » : sortie de tout le reste à la clôture de la bougie du message ; sinon clôture au bout de 24 h.
  - dans une même bougie, le SL passe avant les TP (prudent)."""
import json, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
A = sys.argv
def arg(n, d): return A[A.index(n) + 1] if n in A else d
SIG = Path(arg('--signals', str(HERE / 'inbox.jsonl')))
CAND = dict(x.split('=') for x in arg('--candles', f'XAUUSD={HERE.parent / "forward-test/live/candles.txt"}').split(','))


def candles(path):
    out = []
    for l in open(path):
        p = l.split()
        if len(p) == 6:
            out.append((datetime.strptime(p[0] + p[1], '%Y%m%d%H%M').replace(tzinfo=timezone.utc), *map(float, p[2:])))
    return out


recs = [json.loads(l) for l in open(SIG) if l.strip()]
opens, mgmt = {}, []
for r in recs:
    if r['kind'] == 'open':
        opens.setdefault(r['msg'], r)              # 1re version du message (les modifications ajoutent juste des ✅)
    elif r['kind'] in ('be', 'close'):
        mgmt.append(r)
res = []
for mid, s in sorted(opens.items(), key=lambda x: x[1]['at']):
    path = CAND.get(s['symbol'])
    if not path:
        res.append((s, None, f"pas de bougies {s['symbol']}")); continue
    B = candles(path); t0 = datetime.fromisoformat(s['at']); d, e, st = s['side'], s['entry'], s['sl']
    R = abs(e - st); tps = s['tps'][:3]; n = len(tps) or 1
    be_at = min((datetime.fromisoformat(m['at']) for m in mgmt if m['kind'] == 'be' and m.get('reply_to') == mid), default=None)
    cl_at = min((datetime.fromisoformat(m['at']) for m in mgmt if m['kind'] == 'close' and m.get('reply_to') == mid), default=None)
    bars = [b for b in B if b[0] + timedelta(minutes=5) > t0 and b[0] < t0 + timedelta(hours=24)]
    if not bars or bars[-1][0] < t0 + timedelta(hours=1) and bars[-1][0] < B[-1][0]:
        res.append((s, None, 'bougies insuffisantes')); continue
    filled = None; hit = 0; r = 0.0; out = None
    for (t, o, h, l, c) in bars:
        if filled is None:
            if l <= e <= h: filled = t
            elif t > t0 + timedelta(minutes=15): out = 'non exécuté (prix parti)'; break
            else: continue
        if be_at and t + timedelta(minutes=5) > be_at and hit < n: st = e if d * (e - st) > 0 else st
        if (d > 0 and l <= st) or (d < 0 and h >= st):
            r += (n - hit) / n * d * (st - e) / R; out = 'SL' if hit == 0 else f'stop après TP{hit}'; break
        while hit < n and ((d > 0 and h >= tps[hit]) or (d < 0 and l <= tps[hit])):
            r += d * (tps[hit] - e) / R / n; hit += 1
        if hit == n: out = 'TP3'; break
        if cl_at and t + timedelta(minutes=5) > cl_at:
            r += (n - hit) / n * d * (c - e) / R; out = f'clôture ({hit} TP)'; break
    else:
        if filled: r += (n - hit) / n * d * (bars[-1][4] - e) / R; out = f'en cours ({hit} TP)'
    res.append((s, r if filled else None, out))

print('| Signal (UTC) | Sens | Symbole | Entrée | SL | Résultat | R |\n|---|---|---|---|---|---|---|')
tot = [x[1] for x in res if x[1] is not None]
for s, r, out in res:
    print(f"| {s['at'][:16].replace('T', ' ')} | {'ACHAT' if s['side'] > 0 else 'VENTE'} | {s['symbol']} | {s['entry']} | {s['sl']} | {out} | {'' if r is None else f'{r:+.2f}'} |")
print(f"\nSignaux : {len(res)} · exécutés : {len(tot)} · gagnants : {sum(1 for x in tot if x > 0.01)} · total {sum(tot):+.2f}R")
