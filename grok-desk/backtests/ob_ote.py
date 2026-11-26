"""Backtest « OB 5★ + OTE » sur bougies M5 Axi (XAUUSD), unités de temps 5 / 15 / 30 / 60 min.
Définitions reprises de la stratégie TradingView de l'utilisateur (« OB 5★ — Strategy P1+2+3 ») + critères demandés :
  OB haussier   = bougie baissière juste avant une imbalance (FVG : low[i] > high[i-2]) ; OB = bougie entière (mèches comprises)
  Tendance      = biais journalier (pivots 2/2 du D1 : clôture au-dessus du dernier sommet → haussier, sous le dernier creux → baissier)
  Liquidité     = refus si un bord de l'OB est à ≤ 20 pips d'un EQH / EQL (pivots 5/5 égaux à 20 pips près sur 50 bougies)
  Non mitigé    = pas de clôture au-delà du milieu de l'OB avant l'entrée ; OB invalidé par une clôture au-delà de son extrême
  Plus bas protégé = le bas de l'OB est à ≤ 1 ATR du plus bas des 20 dernières bougies (OB d'origine du mouvement)
  OTE           = milieu de l'OB entre 62 % et 78,6 % de retracement (fibo D1 sur 50 jours, comme l'indicateur, ou swing local 50 bougies)
Entrées : « limite » (ordre au bord de l'OB, 1er retour) ou « figure » (bougie de retournement dans l'OB, comme l'indicateur).
SL = au-delà de l'OB + 2 pips. Gestion « desk » (tiers 1R/2R/3R, BE après TP1) ou « indicateur » (BE à 1R, 50 % à 2R, 50 % à 5R).
Comptage prudent (dans une bougie M5, le stop passe avant les objectifs ; pas d'objectif sur la bougie d'entrée). Spread 0,16 $ déduit.
Usage : python3 ob_ote.py [--json]"""
import glob, os, sys, json
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
H = os.path.dirname(os.path.abspath(__file__)); A = sys.argv
PAR = ZoneInfo('Europe/Paris'); PIP = 0.1; SPREAD = 0.16

rows = {}
files = [f for d in ('data_mai', 'data_aug', 'data_sep', 'data') for f in glob.glob(os.path.join(H, d, '*.txt'))]
files.append(os.path.join(H, '..', 'forward-test', 'live', 'candles.txt'))
for f in sorted(files):
    for l in open(f):
        p = l.split()
        if len(p) == 6:
            rows[p[0] + p[1]] = (datetime.strptime(p[0] + p[1], '%Y%m%d%H%M').replace(tzinfo=timezone.utc), *map(float, p[2:]))
M5 = [rows[k] for k in sorted(rows)]
T0 = datetime(2026, 5, 20, tzinfo=timezone.utc); T1 = datetime(2026, 11, 26, 4, tzinfo=timezone.utc); MID = datetime(2026, 8, 20, tzinfo=timezone.utc)


def resample(bars, minutes, offset=0):
    out, cur, key = [], None, None
    for t, o, h, l, c in bars:
        k = int((t.timestamp() + offset) // (minutes * 60))
        if k != key:
            if cur: out.append(cur)
            key = k; cur = [datetime.fromtimestamp(k * minutes * 60 - offset, timezone.utc), o, h, l, c]
        else:
            cur[2] = max(cur[2], h); cur[3] = min(cur[3], l); cur[4] = c
    if cur: out.append(cur)
    return out


def atr(B, n=14):
    out, a, prev = [], None, None
    for t, o, h, l, c in B:
        tr = h - l if prev is None else max(h - l, abs(h - prev), abs(l - prev))
        a = tr if a is None else (a * (n - 1) + tr) / n
        out.append(a); prev = c
    return out


def pivots(B, n):  # (index de confirmation, index du pivot, valeur) pour sommets et creux
    ph, pl = [], []
    for i in range(2 * n, len(B)):
        j = i - n
        if all(B[j][2] > B[k][2] for k in range(j - n, j + n + 1) if k != j): ph.append((i, j, B[j][2]))
        if all(B[j][3] < B[k][3] for k in range(j - n, j + n + 1) if k != j): pl.append((i, j, B[j][3]))
    return ph, pl


# ── Biais et fibo D1 (journée serveur Axi : 22h UTC) ──
D = resample(M5, 1440, offset=2 * 3600)
dph, dpl = pivots(D, 2)
dbias, lastPH, lastPL, b = [], None, None, 0
php = {i: v for i, j, v in dph}; plp = {i: v for i, j, v in dpl}
for i, (t, o, h, l, c) in enumerate(D):
    if i in php: lastPH = php[i]
    if i in plp: lastPL = plp[i]
    if lastPH is not None and c > lastPH: b = 1
    if lastPL is not None and c < lastPL: b = -1
    dbias.append(b)
dhi = [max(x[2] for x in D[max(0, i - 49):i + 1]) for i in range(len(D))]
dlo = [min(x[3] for x in D[max(0, i - 49):i + 1]) for i in range(len(D))]
dstart = [x[0] for x in D]


def daily_ctx(t):  # dernier jour TERMINÉ avant t (pas de regard vers le futur)
    lo, hi = 0, len(D) - 1; k = -1
    while lo <= hi:
        m = (lo + hi) // 2
        if dstart[m] + timedelta(days=1) <= t: k = m; lo = m + 1
        else: hi = m - 1
    return (dbias[k], dhi[k], dlo[k]) if k >= 0 else (0, None, None)


def bull_pattern(B, i, avgb):
    t, o, h, l, c = B[i]; body = abs(c - o); rng = h - l; up = h - max(c, o); dn = min(c, o) - l
    if rng <= 0: return False
    po, pc = B[i - 1][1], B[i - 1][4]
    return (dn >= 2 * body and up <= body and dn >= rng * 0.5) or (body <= rng * 0.05 and dn >= rng * 0.6) or \
           (c > o and pc < po and c >= po and o <= pc) or (c > o and body >= rng * 0.8)


def bear_pattern(B, i, avgb):
    t, o, h, l, c = B[i]; body = abs(c - o); rng = h - l; up = h - max(c, o); dn = min(c, o) - l
    if rng <= 0: return False
    po, pc = B[i - 1][1], B[i - 1][4]
    return (up >= 2 * body and dn <= body and up >= rng * 0.5) or (body <= rng * 0.05 and up >= rng * 0.6) or \
           (c < o and pc > po and c <= po and o >= pc) or (c < o and body >= rng * 0.8)


m5_times = [x[0] for x in M5]


def m5_index(t):
    lo, hi = 0, len(M5)
    while lo < hi:
        m = (lo + hi) // 2
        if m5_times[m] < t: lo = m + 1
        else: hi = m
    return lo


def manage(d, e, sl, i0, mgmt, fill_bar_check=True):
    """Suit la position sur M5 à partir de l'indice i0 (bougie d'entrée). Renvoie (r, sortie, index de fin)."""
    R = abs(e - sl); st = sl; r = 0.0
    legs = [(1, 1 / 3), (2, 1 / 3), (3, 1 / 3)] if mgmt == 'desk' else [(2, 0.5), (5, 0.5)]
    be_at = 1 if mgmt == 'desk' else 1  # desk : BE au TP1 (1R) ; indicateur : BE à 1R
    left = 1.0; k = 0; be = False
    end = min(len(M5), i0 + 288 * 5)
    for i in range(i0, end):
        t, o, h, l, c = M5[i]
        adverse = l if d > 0 else h
        if d * (adverse - st) <= 0:  # stop touché (prioritaire)
            r += left * d * (st - e) / R
            return r, ('SL' if not be else f'BE après {k} TP'), i
        if i == i0: continue  # prudent : pas d'objectif sur la bougie d'entrée
        fav = h if d > 0 else l
        if not be and d * (fav - (e + d * be_at * R)) >= 0:
            be = True; st = e
        while k < len(legs) and d * (fav - (e + d * legs[k][0] * R)) >= 0:
            r += legs[k][1] * legs[k][0]; left -= legs[k][1]; k += 1
        if k == len(legs): return r, 'TP final', i
    t, o, h, l, c = M5[end - 1]
    return r + left * d * (c - e) / R, 'temps écoulé', end - 1


def run(tf, entry='limite', mgmt='desk', ote='D1', protected=True, use_ote=True):
    B = resample(M5, tf) if tf > 5 else [list(x) for x in M5]
    AT = atr(B)
    ph, pl = pivots(B, 5)
    eqh, eql = [], []  # (index de formation, niveau)
    phs, pls = {}, {}
    for i, j, v in ph: phs.setdefault(i, []).append((j, v))
    for i, j, v in pl: pls.setdefault(i, []).append((j, v))
    seen_h, seen_l = [], []
    obs = {1: None, -1: None}
    trades = []; busy_until = None
    bodies = [abs(x[4] - x[1]) for x in B]
    def try_entries(i, t, o, h, l, c, tclose):
        nonlocal busy_until
        if busy_until is not None and t < busy_until: return
        for d in (1, -1):
            ob = obs[d]
            if ob is None or ob['mit']: continue
            if entry == 'figure':
                inzone = h >= ob['lo'] and l <= ob['hi']
                if i == ob['i'] or not inzone: continue
                if not (bull_pattern(B, i, 0) if d > 0 else bear_pattern(B, i, 0)): continue
                e = c; sl = ob['lo'] - 2 * PIP if d > 0 else ob['hi'] + 2 * PIP
                if d * (e - sl) <= 0: continue
                i0 = m5_index(tclose)
                if i0 >= len(M5): continue
                r, out, iend = manage(d, e, sl, i0, mgmt)
            else:  # limite au bord de l'OB, 1er retour (cherché sur M5 pendant cette bougie TF)
                lim = ob['hi'] if d > 0 else ob['lo']
                if i == ob['i'] or not ((d > 0 and l <= lim) or (d < 0 and h >= lim)): continue
                j0 = m5_index(t)
                jf = None
                for j in range(j0, min(len(M5), j0 + tf // 5)):
                    if (d > 0 and M5[j][3] <= lim) or (d < 0 and M5[j][2] >= lim): jf = j; break
                if jf is None: continue
                e = min(lim, M5[jf][1]) if d > 0 else max(lim, M5[jf][1])
                sl = ob['lo'] - 2 * PIP if d > 0 else ob['hi'] + 2 * PIP
                if d * (e - sl) <= 0: obs[d] = None; continue
                r, out, iend = manage(d, e, sl, jf, mgmt)
            R = abs(e - sl)
            trades.append(dict(t=M5[min(iend, len(M5) - 1)][0] if False else (t if entry == 'limite' else tclose), d=d, e=e, R=R, r=r - SPREAD / R, out=out))
            obs[d] = None
            busy_until = M5[iend][0] + timedelta(minutes=5)
            return
        return

    for i in range(30, len(B)):
        t, o, h, l, c = B[i]
        tclose = t + timedelta(minutes=tf)
        for j, v in phs.get(i, []):
            for jj, vv in seen_h:
                if j - jj <= 50 and abs(v - vv) <= 20 * PIP: eqh.append((i, (v + vv) / 2)); break
            seen_h.append((j, v))
        for j, v in pls.get(i, []):
            for jj, vv in seen_l:
                if j - jj <= 50 and abs(v - vv) <= 20 * PIP: eql.append((i, (v + vv) / 2)); break
            seen_l.append((j, v))
        if entry == 'limite': try_entries(i, t, o, h, l, c, tclose)  # l'ordre limite est touché pendant la bougie, avant sa clôture
        # invalidation / mitigation des OB actifs
        for d in (1, -1):
            ob = obs[d]
            if ob is None: continue
            if (d > 0 and c < ob['lo']) or (d < 0 and c > ob['hi']): obs[d] = None; continue
            if (d > 0 and c < ob['mid']) or (d < 0 and c > ob['mid']): ob['mit'] = True
        # nouvel OB (bougie i-2) si imbalance
        bias, fh, fl = daily_ctx(tclose)
        for d in (1, -1):
            fvg = (l > B[i - 2][2]) if d > 0 else (h < B[i - 2][3])
            opp = (B[i - 2][4] < B[i - 2][1]) if d > 0 else (B[i - 2][4] > B[i - 2][1])
            if not (fvg and opp) or bias != d or obs[d] is not None: continue
            hi_, lo_ = B[i - 2][2], B[i - 2][3]; mid = (hi_ + lo_) / 2
            if any(abs(hi_ - v) <= 20 * PIP for _, v in eqh[-40:]) or any(abs(lo_ - v) <= 20 * PIP for _, v in eql[-40:]): continue
            a = AT[i]
            if protected:
                ext = min(x[3] for x in B[i - 22:i - 1]) if d > 0 else max(x[2] for x in B[i - 22:i - 1])
                if (d > 0 and lo_ - ext > a) or (d < 0 and ext - hi_ > a): continue
            if use_ote:
                if ote == 'D1':
                    if fh is None: continue
                    top, bot = fh, fl
                else:
                    top = max(x[2] for x in B[max(0, i - 50):i + 1]); bot = min(x[3] for x in B[max(0, i - 50):i + 1])
                rg = top - bot
                if rg <= 0: continue
                z1, z2 = (top - 0.786 * rg, top - 0.62 * rg) if d > 0 else (bot + 0.62 * rg, bot + 0.786 * rg)
                if not (z1 <= mid <= z2): continue
            obs[d] = dict(hi=hi_, lo=lo_, mid=mid, mit=False, born=tclose, i=i)
        if entry == 'figure': try_entries(i, t, o, h, l, c, tclose)
    return [x for x in trades if T0 <= x['t'] <= T1]


def stats(T):
    if not T: return dict(n=0, tot=0, pf=0, dd=0, win=0, h1=0, h2=0, R=0)
    rs = [x['r'] for x in T]; gp = sum(r for r in rs if r > 0); gl = -sum(r for r in rs if r < 0)
    e = p = dd = 0
    for r in rs: e += r; p = max(p, e); dd = max(dd, p - e)
    return dict(n=len(T), tot=sum(rs), pf=gp / gl if gl else 99, dd=dd, win=100 * sum(1 for r in rs if r > 0.01) / len(rs),
                h1=sum(x['r'] for x in T if x['t'] < MID), h2=sum(x['r'] for x in T if x['t'] >= MID), R=sum(x['R'] for x in T) / len(T))


if __name__ == '__main__':
    print(f"Données M5 Axi {M5[0][0]:%d/%m} → {M5[-1][0]:%d/%m} · période testée 20/05 → 26/11/2026 · comptage prudent, spread déduit\n")
    print('| UT | Entrée | Gestion | OTE | Trades | Gagnants | Total R | PF | Pire creux R | SL moyen $ | 20/05–19/08 | 20/08–26/11 |')
    print('|---|---|---|---|---|---|---|---|---|---|---|---|')
    res = {}
    for tf in (5, 15, 30, 60):
        for entry in ('limite', 'figure'):
            for mgmt in ('desk', 'indicateur'):
                for ote in ('D1', 'local', 'sans'):
                    T = run(tf, entry, mgmt, ote if ote != 'sans' else 'D1', use_ote=ote != 'sans')
                    s = stats(T); res[(tf, entry, mgmt, ote)] = s
                    print(f"| {tf} min | {entry} | {mgmt} | {ote} | {s['n']} | {s['win']:.0f} % | {s['tot']:+.1f} | {s['pf']:.2f} | {s['dd']:.1f} | {s['R']:.2f} | {s['h1']:+.1f} | {s['h2']:+.1f} |")
