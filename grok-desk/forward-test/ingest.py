"""Ajoute des bougies Axi (JSON de get_mt5_candles sur stdin) à live/candles.txt, sans doublon, triées."""
import json, os, sys
H = os.path.dirname(os.path.abspath(__file__)); P = os.path.join(H, 'live', 'candles.txt')
rows = {}
if os.path.exists(P):
    for l in open(P):
        p = l.split()
        if len(p) == 6: rows[p[0] + p[1]] = l.strip()
new = 0
for c in json.loads(sys.stdin.read()):
    t = c['time'][:16].replace('-', '').replace('T', ' ').replace(':', '')  # 2026-11-23T00:05 → 20261123 0005
    k = t.replace(' ', '')
    if k not in rows: new += 1
    rows[k] = f"{t} {c['open']} {c['high']} {c['low']} {c['close']}"
open(P, 'w').write('\n'.join(rows[k] for k in sorted(rows)) + '\n')
print(f'{new} nouvelles bougies · total {len(rows)} · dernière {sorted(rows)[-1]}')
