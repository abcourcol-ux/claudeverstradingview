"""Un passage du test papier de nuit (00h30–04h Paris) : rejoue la stratégie validée sur live/candles.txt,
envoie sur Telegram les nouvelles cartes et les résultats, tient le journal. Aucun ordre n'est passé.
Règle : SL 50 pips fixe, BE après TP1, TP 1R/2R/3R par tiers, filtre 3 ATR, une position à la fois, comptage prudent."""
import json, os, subprocess, sys
from datetime import datetime
from zoneinfo import ZoneInfo
H = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(H))
PAR = ZoneInfo('Europe/Paris'); STATE = os.path.join(H, 'live', 'state.json')
out = subprocess.run([sys.executable, os.path.join(ROOT, 'grok-desk/backtests/month.py'), '--data', os.path.join(H, 'live'),
                      '--window', 'nuit', '--prudent', '--pips', '50', '--k', '0', '--json'], capture_output=True, text=True, check=True).stdout
snap = json.loads(next(l for l in out.splitlines() if l.startswith('JSON'))[4:])
st = json.load(open(STATE)) if os.path.exists(STATE) else {'next_id': 100, 'trades': {}}
DRY = '--dry' in sys.argv
def tg(args):
    cmd = ['node', os.path.join(ROOT, 'grok-desk/src/notify.js')] + args
    if DRY: print('[dry]', ' '.join(args)[:200]); return
    env = dict(os.environ, NODE_USE_ENV_PROXY='1', NODE_NO_WARNINGS='1')
    print(subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=ROOT).stdout.strip()[-120:])
def paris(iso): return datetime.fromisoformat(iso).astimezone(PAR).strftime('%d/%m %H:%M')
log = []
for t in snap['trades']:
    key = t['t']
    if datetime.fromisoformat(key) < datetime.fromisoformat(st.get('since', '2000-01-01T00:00:00+00:00')): continue
    s = st['trades'].get(key)
    if s is None:
        s = st['trades'][key] = {'id': st['next_id'], 'hit': 0, 'done': False}; st['next_id'] += 1
        card = {'symbol': 'XAUUSD', 'direction': 'long' if t['d'] > 0 else 'short', 'entry': t['e0'], 'slPips': 50,
                'atr': t['atr'], 'price': snap['price']}
        tg([json.dumps(card), '--id', str(s['id']), '--comment',
            f"Test papier nuit #{s['id']} (bougie signal {paris(t['t'])}) — pic d'amplitude ≥ 2 ATR côté VWAP. Entrée à l'ouverture suivante, 1/3 à chaque TP, BE dès TP1."])
        log.append(f"| #{s['id']} | {paris(t['t'])} | {'ACHAT' if t['d']>0 else 'VENTE'} | {t['e0']:.2f} | {t['sl']:.2f} | {t['tp1']:.2f} | {t['tp2']:.2f} | {t['tpf']:.2f} | carte envoyée |")
    if t['hit'] > s['hit'] and not s['done']:
        for k in range(s['hit'] + 1, t['hit'] + 1):
            tg(['--text', f"🎯 Trade #{s['id']} : TP{k if k < 3 else ' final'} touché" + (" — SL remonté au BE" if k == 1 else '')])
        s['hit'] = t['hit']
    if t['status'] == 'closed' and not s['done']:
        s['done'] = True; s['r'] = round(t['r'], 2); s['out'] = t['out']
        tg(['--text', f"✅ Trade #{s['id']} clôturé : {t['out']} → {t['r']:+.2f}R ({t['r']*25:+.0f} $ pour 25 $ risqués)"])
        log.append(f"| #{s['id']} | | | | | | | | **{t['out']} : {t['r']:+.2f}R** |")
json.dump(st, open(STATE, 'w'), indent=1)
day = datetime.now(PAR).strftime('%Y-%m-%d'); J = os.path.join(H, f'{day}-nuit-papier.md')
if not os.path.exists(J):
    open(J, 'w').write(f"# Test papier de nuit {day} — 00h30–04h Paris\n\nRègle validée (sept.–nov.) : SL 50 pips fixe, BE après TP1, TP 1R/2R/3R par tiers, filtre 3 ATR du VWAP, une position à la fois. Données : bougies M5 Axi (lecture seule). Aucun ordre passé.\n\n| # | Signal (Paris) | Sens | Entrée | SL | TP1 | TP2 | TP final | Statut |\n|---|---|---|---|---|---|---|---|---|\n")
if log: open(J, 'a').write('\n'.join(log) + '\n')
op = [t for t in snap['trades'] if t['status'] != 'closed']
print(f"Dernière bougie {paris(snap['last'])} · prix {snap['price']} · ATR {snap['atr']:.2f} · position : {op[0]['status'] + ' ' + ('ACHAT' if op[0]['d']>0 else 'VENTE') if op else 'aucune'} · {len(log)} lignes de journal")
