"""Backtest de la règle de nuit validée, résultats en $ pour un lot fixe, par mois et au total.
Usage : python3 report_lot.py --lot 0.03 [--from 2026-08-20] [--to 2026-11-20] [--spread 0.16]"""
import json, subprocess, sys, os
from collections import OrderedDict
from datetime import datetime
from zoneinfo import ZoneInfo
H = os.path.dirname(os.path.abspath(__file__)); A = sys.argv
def arg(n, d): return type(d)(A[A.index(n) + 1]) if n in A else d
LOT = arg('--lot', 0.03); OZ = LOT * 100; SPREAD = arg('--spread', 0.16); FROM = arg('--from', '2026-08-20'); TO = arg('--to', '2026-11-20')
PAR = ZoneInfo('Europe/Paris'); MOIS = ['', 'janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre']
out = subprocess.run([sys.executable, os.path.join(H, 'month.py'), '--data', 'data_aug,data_sep,data', '--window', 'nuit', '--prudent',
                      '--pips', '50', '--k', '0', '--json'], capture_output=True, text=True, check=True).stdout
snap = json.loads(next(l for l in out.splitlines() if l.startswith('JSON'))[4:])
tr = [t for t in snap['trades'] if t['status'] == 'closed' and FROM <= datetime.fromisoformat(t['t']).astimezone(PAR).strftime('%Y-%m-%d') <= TO]
def usd(t):  # P&L réel : distance en $ × onces (r est exprimé en R = 5 $), moins le spread payé à l'entrée
    return t['r'] * t['R'] * OZ - SPREAD * OZ
by = OrderedDict()
for t in tr:
    d = datetime.fromisoformat(t['t']).astimezone(PAR); k = (d.year, d.month); by.setdefault(k, []).append(t)
def line(name, ts):
    g = sum(1 for t in ts if t['r'] > 0.01); pnl = sum(usd(t) for t in ts); gp = sum(usd(t) for t in ts if usd(t) > 0); gl = -sum(usd(t) for t in ts if usd(t) < 0)
    eq = pk = dd = 0
    for t in ts: eq += usd(t); pk = max(pk, eq); dd = max(dd, pk - eq)
    return f"| {name} | {len(ts)} | {g} ({100*g/len(ts):.0f} %) | {sum(t['r'] for t in ts):+.2f}R | **{pnl:+.2f} $** | {gp/gl if gl else float('inf'):.2f} | {dd:.2f} $ |"
print(f"Règle de nuit 00h30–04h Paris · SL 50 pips · BE après TP1 · TP 1R/2R/3R · lot {LOT} ({OZ:g} oz) → 1R = {5*OZ:.0f} $ · spread {SPREAD} $ déduit · comptage prudent")
print(f"Période {FROM} → {TO} · {len(tr)} trades\n")
print("| Mois | Trades | Gagnants | R | Résultat | PF | Drawdown max |\n|---|---|---|---|---|---|---|")
for (y, m), ts in by.items(): print(line(f"{MOIS[m]} {y}" + (' (dès le 20)' if m == 8 else ' (au 20)' if m == 11 else ''), ts))
print(line('**Total**', tr))
if '--list' in A:
    for t in tr: print(f"{datetime.fromisoformat(t['t']).astimezone(PAR):%d/%m %H:%M}  {'ACHAT' if t['d']>0 else 'VENTE'}  {t['out']:22} {t['r']:+.2f}R  {usd(t):+7.2f} $")
