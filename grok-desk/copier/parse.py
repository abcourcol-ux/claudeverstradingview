"""Lecture des messages d'un groupe de signaux Telegram → signal structuré.
Formats reconnus (exemples réels) :
  « SELL GOLD 50 PIPS NOW »                                   → pré-alerte (pas d'ordre)
  « 📉 Je vends XAUUSD à 3526.56 ✅ TP 1: 3521.56 … 🔒 SL: 3531.56 (50 PIPS) » → ouverture
  « J'achète XAGUSD à 42.287 TP 1: 42.587 TP 2: … SL: 41.987 (30 pips) »      → ouverture
  « ✅ Déplacer votre SL à BE. » (en réponse au signal)       → stop au prix d'entrée
  « Clôturez / fermez … »                                     → clôture
Aucun ordre n'est passé ici : ce module ne fait que lire."""
import re

SYMBOLS = {'GOLD': 'XAUUSD', 'OR': 'XAUUSD', 'XAU': 'XAUUSD', 'SILVER': 'XAGUSD', 'ARGENT': 'XAGUSD', 'XAG': 'XAGUSD'}
NUM = r'(\d+(?:[.,]\d+)?)'


def _num(s):
    return float(s.replace(',', '.'))


def _symbol(t):
    for m in re.finditer(r'\b([A-Z]{6})\b', t):
        w = m.group(1)
        if w in SYMBOLS: return SYMBOLS[w]
        if w not in ('ACHETE', 'VENDRE', 'MOMENT', 'TRADES', 'SIGNAL'): return w
    for k, v in SYMBOLS.items():
        if re.search(rf'\b{k}\b', t):
            return v
    return None


def _side(t):
    low = t.lower().replace('’', "'")
    if re.search(r"\b(je vends|vente|sell|short)\b", low):
        return -1
    if re.search(r"(j'ach[eè]te|\bachat\b|\bbuy\b|\blong\b)", low):
        return 1
    return 0


def parse(text):
    """Renvoie un dict {kind: open|be|close|tp|alert|other, ...}."""
    t = (text or '').strip()
    up = t.upper()
    low = t.lower().replace('’', "'")
    side, sym = _side(t), _symbol(up)
    entry = re.search(r"(?:\bà|\bat|@)\s*" + NUM, t, re.I)
    sl = re.search(r'\bSL\s*[:=]?\s*' + NUM, t, re.I)
    tps = {int(n): _num(p) for n, p in re.findall(r'\bTP\s*(\d)\s*[:=]?\s*' + NUM, t, re.I)}
    if side and sym and entry and sl:
        e, s = _num(entry.group(1)), _num(sl.group(1))
        if (e - s) * side <= 0:                       # SL du mauvais côté : message mal lu
            return {'kind': 'other', 'why': 'SL incohérent', 'text': t}
        return {'kind': 'open', 'side': side, 'symbol': sym, 'entry': e, 'sl': s,
                'tps': [tps[k] for k in sorted(tps)], 'pips': re.search(r'\((\d+)\s*pips?\)', low) and int(re.search(r'\((\d+)\s*pips?\)', low).group(1))}
    if re.search(r'\b(sl|stop)\b[^.\n]{0,25}\b(be|break[ -]?even|prix d\'entr[ée]e)\b', low) or re.search(r'\bbe\b.*\bsl\b', low):
        return {'kind': 'be'}
    if re.search(r'\b(cl[oô]tur|ferm(ez|er|e)\b|close|coupez|sortez)', low):
        return {'kind': 'close'}
    m = re.search(r'\btp\s*(\d)\b[^\n]{0,20}\b(touch|atteint|hit|valid)', low)
    if m:
        return {'kind': 'tp', 'n': int(m.group(1))}
    if side and sym and re.search(r'\b(now|maintenant)\b', low):
        return {'kind': 'alert', 'side': side, 'symbol': sym}
    if side and sym:                                   # ex. « je surveille cette zone d'achat sur le silver » : info, pas d'ordre
        return {'kind': 'note', 'side': side, 'symbol': sym, 'text': t[:200]}
    return {'kind': 'other', 'text': t[:80]}
