"""Compare des modifications de la règle de nuit sur 20/08–20/11, par moitié (20/08–04/10 et 05/10–20/11).
Résultats en $ pour 0,03 lot, spread 0,16 $/oz déduit, comptage prudent. Une variante n'est retenue que si elle bat la règle actuelle sur les DEUX moitiés."""
import json, subprocess, sys, os
from datetime import datetime
from zoneinfo import ZoneInfo
H = os.path.dirname(os.path.abspath(__file__)); PAR = ZoneInfo('Europe/Paris'); OZ = 3; SPREAD = 0.16
BASE = ['--data', 'data_aug,data_sep,data', '--window', 'nuit', '--prudent', '--pips', '50', '--k', '0', '--maxsl', '1', '--json']
V = [('Règle actuelle', []),
     ('SMC Premium/Discount (range 4 h)', ['--pd', '48']),
     ('SMC Premium/Discount (range 2 h)', ['--pd', '24']),
     ('SMC prise de liquidité (30 min, réf. 4 h)', ['--sweep', '6']),
     ('SMC prise de liquidité (1 h, réf. 4 h)', ['--sweep', '12']),
     ('SMC Premium/Discount 4 h + prise de liquidité 1 h', ['--pd', '48', '--sweep', '12']),
     ('BE après TP2 (au lieu de TP1)', ['--beafter', '2']),
     ('BE 1 $ sous l\'entrée', ['--beoff', '1']),
     ('BE 2 $ sous l\'entrée', ['--beoff', '2']),
     ('2 sorties (1R / 2R)', ['--tpn', '2']),
     ('4 sorties (1R → 4R)', ['--tpn', '4']),
     ('Max 3 trades par nuit', ['--maxday', '3']),
     ('Arrêt après 2 SL dans la nuit', ['--maxsl', '2']),
     ('Arrêt après 1 SL dans la nuit', ['--maxsl', '1']),
     ('Filtre tendance EMA 50 (5 min)', ['--trend', '50']),
     ('Filtre tendance EMA 200 (5 min)', ['--trend', '200']),
     ('Fenêtre 00h00–04h', ['--win', '0000-0400']),
     ('Fenêtre 00h30–05h', ['--win', '0030-0500']),
     ('Fenêtre 00h30–03h', ['--win', '0030-0300']),
     ('Pic d\'amplitude ≥ 1,8 ATR', ['--range', '1.8']),
     ('Pic d\'amplitude ≥ 2,2 ATR', ['--range', '2.2']),
     ('SL 40 pips', ['--pips', '40']),
     ('SL 60 pips', ['--pips', '60'])]
def run(extra):
    args = BASE[:]
    for i in range(0, len(extra), 2):
        if extra[i] in args: args[args.index(extra[i]) + 1] = extra[i + 1]
        else: args += extra[i:i + 2]
    out = subprocess.run([sys.executable, os.path.join(H, 'month.py')] + args, capture_output=True, text=True, check=True).stdout
    tr = [t for t in json.loads(next(l for l in out.splitlines() if l.startswith('JSON'))[4:])['trades'] if t['status'] == 'closed']
    res = {'A': [], 'B': []}
    for t in tr:
        d = datetime.fromisoformat(t['t']).astimezone(PAR).strftime('%Y-%m-%d')
        if d < '2026-08-20' or d > '2026-11-20': continue
        res['A' if d <= '2026-10-04' else 'B'].append(t['r'] * t['R'] * OZ - SPREAD * OZ)
    allp = res['A'] + res['B']; gp = sum(x for x in allp if x > 0); gl = -sum(x for x in allp if x < 0)
    eq = pk = dd = 0
    for x in allp: eq += x; pk = max(pk, eq); dd = max(dd, pk - eq)
    return len(allp), sum(res['A']), sum(res['B']), sum(allp), gp / gl if gl else 0, dd
base = run([])
print('| Variante | Trades | 20/08–04/10 | 05/10–20/11 | Total | PF | Drawdown | Verdict |\n|---|---|---|---|---|---|---|---|')
for name, ex in V:
    n, a, b, t, pf, dd = run(ex)
    ok = 'référence' if not ex else ('✅ mieux sur les 2' if a > base[1] + 1 and b > base[2] + 1 else '❌')
    print(f'| {name} | {n} | {a:+.0f} $ | {b:+.0f} $ | **{t:+.0f} $** | {pf:.2f} | {dd:.0f} $ | {ok} |')
