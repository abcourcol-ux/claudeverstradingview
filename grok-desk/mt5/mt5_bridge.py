"""Pont MetaTrader 5 pour Grok Desk.

Lancé par l'app Node (src/broker-mt5.js). Protocole : une requête JSON par ligne sur stdin,
une réponse JSON par ligne sur stdout : {"id": 1, "cmd": "account", ...} -> {"id": 1, "ok": true, "result": {...}}

Sécurité : refuse de démarrer sur un compte RÉEL sauf si MT5_ALLOW_LIVE=YES_REAL_MONEY,
et refuse un autre compte que MT5_LOGIN si celui-ci est fourni.
Nécessite Windows, le terminal MetaTrader 5 d'Axi ouvert et connecté, et `pip install MetaTrader5`.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import MetaTrader5 as mt5

MAGIC = int(os.environ.get("MT5_MAGIC", "770077"))
DEVIATION = int(os.environ.get("MT5_DEVIATION", "20"))
ALLOW_LIVE = os.environ.get("MT5_ALLOW_LIVE", "") == "YES_REAL_MONEY"
TRADE_MODES = {0: "demo", 1: "contest", 2: "real"}


class DeskError(Exception):
    pass


def last_error():
    err = mt5.last_error()
    return f"{err[0]} {err[1]}" if err else "inconnue"


def cmd_init(req):
    kwargs = {}
    if os.environ.get("MT5_PATH"):
        kwargs["path"] = os.environ["MT5_PATH"]
    if os.environ.get("MT5_LOGIN"):
        kwargs["login"] = int(os.environ["MT5_LOGIN"])
        if os.environ.get("MT5_PASSWORD"):
            kwargs["password"] = os.environ["MT5_PASSWORD"]
        if os.environ.get("MT5_SERVER"):
            kwargs["server"] = os.environ["MT5_SERVER"]
    if not mt5.initialize(**kwargs):
        raise DeskError(f"initialisation MT5 impossible ({last_error()}) : le terminal MetaTrader 5 est-il ouvert ?")
    acc = cmd_account(req)
    if os.environ.get("MT5_LOGIN") and str(acc["login"]) != os.environ["MT5_LOGIN"]:
        mt5.shutdown()
        raise DeskError(f"le terminal est connecté au compte {acc['login']}, pas à MT5_LOGIN={os.environ['MT5_LOGIN']}")
    if acc["mode"] != "demo" and not ALLOW_LIVE:
        mt5.shutdown()
        raise DeskError(f"LIVE_REFUSED : le compte {acc['login']} est un compte {acc['mode'].upper()}. "
                        "Grok Desk ne trade que sur démo tant que MT5_ALLOW_LIVE=YES_REAL_MONEY n'est pas défini.")
    return acc


def cmd_account(req):
    a = mt5.account_info()
    if a is None:
        raise DeskError(f"account_info: {last_error()}")
    return {"login": a.login, "server": a.server, "mode": TRADE_MODES.get(a.trade_mode, str(a.trade_mode)),
            "currency": a.currency, "balance": a.balance, "equity": a.equity, "margin_free": a.margin_free,
            "leverage": a.leverage}


def symbol_info(sym):
    if not mt5.symbol_select(sym, True):
        raise DeskError(f"symbole {sym} introuvable ou non sélectionnable ({last_error()})")
    s = mt5.symbol_info(sym)
    if s is None:
        raise DeskError(f"symbol_info {sym}: {last_error()}")
    return s


def cmd_symbol(req):
    s = symbol_info(req["symbol"])
    t = mt5.symbol_info_tick(req["symbol"])
    return {"symbol": s.name, "description": s.description, "contract_size": s.trade_contract_size,
            "volume_min": s.volume_min, "volume_max": s.volume_max, "volume_step": s.volume_step,
            "digits": s.digits, "point": s.point, "stops_level": s.trade_stops_level,
            "trade_mode": s.trade_mode, "bid": t.bid if t else None, "ask": t.ask if t else None}


def cmd_symbols(req):
    flt = req.get("filter", "")
    out = []
    for s in mt5.symbols_get(flt) if flt else mt5.symbols_get():
        out.append({"symbol": s.name, "description": s.description, "path": s.path})
    return out[: int(req.get("limit", 200))]


def filling_mode(s):
    # bit 1 = FOK, bit 2 = IOC
    return mt5.ORDER_FILLING_IOC if s.filling_mode & 2 else mt5.ORDER_FILLING_FOK


def cmd_open(req):
    sym, side, volume = req["symbol"], req["side"], float(req["volume"])
    s = symbol_info(sym)
    tick = mt5.symbol_info_tick(sym)
    if tick is None:
        raise DeskError(f"pas de cotation pour {sym}")
    price = tick.ask if side == "buy" else tick.bid
    sl, tp = float(req["sl"]), float(req["tp"])
    if side == "buy" and not (sl < price < tp):
        raise DeskError(f"stop/objectif incohérents avec le prix {price} (achat : stop < prix < objectif)")
    if side == "sell" and not (tp < price < sl):
        raise DeskError(f"stop/objectif incohérents avec le prix {price} (vente : objectif < prix < stop)")
    request = {
        "action": mt5.TRADE_ACTION_DEAL, "symbol": sym, "volume": volume,
        "type": mt5.ORDER_TYPE_BUY if side == "buy" else mt5.ORDER_TYPE_SELL,
        "price": price, "sl": round(sl, s.digits), "tp": round(tp, s.digits),
        "deviation": DEVIATION, "magic": MAGIC, "comment": str(req.get("comment", "GrokDesk"))[:31],
        "type_time": mt5.ORDER_TIME_GTC, "type_filling": filling_mode(s),
    }
    r = mt5.order_send(request)
    if r is None or r.retcode != mt5.TRADE_RETCODE_DONE:
        raise DeskError(f"ordre refusé : {r.retcode if r else ''} {r.comment if r else last_error()}")
    return {"ticket": r.order, "deal": r.deal, "price": r.price, "volume": r.volume}


def position_dict(p):
    return {"ticket": p.ticket, "symbol": p.symbol, "side": "buy" if p.type == mt5.POSITION_TYPE_BUY else "sell",
            "volume": p.volume, "price_open": p.price_open, "price_current": p.price_current,
            "sl": p.sl, "tp": p.tp, "profit": p.profit, "magic": p.magic}


def cmd_positions(req):
    ps = mt5.positions_get() or []
    return [position_dict(p) for p in ps if p.magic == MAGIC]


def cmd_close(req):
    ticket = int(req["ticket"])
    ps = mt5.positions_get(ticket=ticket) or []
    if not ps:
        raise DeskError(f"position {ticket} introuvable (déjà fermée ?)")
    p = ps[0]
    s = symbol_info(p.symbol)
    tick = mt5.symbol_info_tick(p.symbol)
    buy = p.type == mt5.POSITION_TYPE_BUY
    r = mt5.order_send({
        "action": mt5.TRADE_ACTION_DEAL, "symbol": p.symbol, "volume": p.volume, "position": ticket,
        "type": mt5.ORDER_TYPE_SELL if buy else mt5.ORDER_TYPE_BUY, "price": tick.bid if buy else tick.ask,
        "deviation": DEVIATION, "magic": MAGIC, "comment": str(req.get("comment", "GrokDesk close"))[:31],
        "type_time": mt5.ORDER_TIME_GTC, "type_filling": filling_mode(s),
    })
    if r is None or r.retcode != mt5.TRADE_RETCODE_DONE:
        raise DeskError(f"fermeture refusée : {r.retcode if r else ''} {r.comment if r else last_error()}")
    return {"price": r.price, "volume": r.volume}


def cmd_closed(req):
    """Résultat d'une position fermée : prix de sortie, P&L total (profit + swap + commission), raison."""
    ticket = int(req["ticket"])
    now = datetime.now(timezone.utc)
    deals = mt5.history_deals_get(now - timedelta(days=7), now + timedelta(days=1), position=ticket) or []
    if not deals:
        return None
    exits = [d for d in deals if d.entry in (mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_OUT_BY)]
    if not exits:
        return None
    last = exits[-1]
    reasons = {mt5.DEAL_REASON_SL: "stop", mt5.DEAL_REASON_TP: "target"}
    return {"price": last.price, "pnl": round(sum(d.profit + d.swap + d.commission for d in deals), 2),
            "reason": reasons.get(last.reason, "manuel")}


_offset = {"value": None}


def server_offset(sym):
    """Décalage heure serveur MT5 - UTC, en secondes (Axi = New York + 7 h).
    MT5_SERVER_UTC_OFFSET_HOURS le force ; sinon déduit de la dernière cotation (marché ouvert)."""
    if os.environ.get("MT5_SERVER_UTC_OFFSET_HOURS"):
        return int(float(os.environ["MT5_SERVER_UTC_OFFSET_HOURS"]) * 3600)
    if _offset["value"] is None:
        tick = mt5.symbol_info_tick(sym)
        if tick is None:
            raise DeskError("impossible de déduire l'heure du serveur MT5 : définis MT5_SERVER_UTC_OFFSET_HOURS (Axi : 2 en hiver, 3 en été)")
        diff = tick.time - datetime.now(timezone.utc).timestamp()
        if abs(diff) > 14 * 3600:
            raise DeskError("cotation trop ancienne pour déduire l'heure du serveur : définis MT5_SERVER_UTC_OFFSET_HOURS")
        _offset["value"] = int(round(diff / 1800.0) * 1800)
    return _offset["value"]


def cmd_rates(req):
    """Bougies : time (unix s, UTC), open, high, low, close, tick_volume, real_volume."""
    tf = getattr(mt5, "TIMEFRAME_" + str(req.get("timeframe", "M5")).upper())
    symbol_info(req["symbol"])
    off = server_offset(req["symbol"])
    rates = mt5.copy_rates_from_pos(req["symbol"], tf, 0, int(req.get("count", 1500)))
    if rates is None:
        raise DeskError(f"copy_rates {req['symbol']}: {last_error()}")
    return [{"time": int(r["time"]) - off, "open": float(r["open"]), "high": float(r["high"]), "low": float(r["low"]),
             "close": float(r["close"]), "tick_volume": int(r["tick_volume"]), "real_volume": int(r["real_volume"])}
            for r in rates]


COMMANDS = {"init": cmd_init, "account": cmd_account, "symbol": cmd_symbol, "symbols": cmd_symbols,
            "rates": cmd_rates, "open": cmd_open, "positions": cmd_positions, "close": cmd_close, "closed": cmd_closed}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = {}
        try:
            req = json.loads(line)
            fn = COMMANDS.get(req.get("cmd"))
            if fn is None:
                raise DeskError(f"commande inconnue : {req.get('cmd')}")
            out = {"id": req.get("id"), "ok": True, "result": fn(req)}
        except Exception as e:  # noqa: BLE001 — toute erreur est renvoyée à Node
            out = {"id": req.get("id"), "ok": False, "error": str(e)}
        sys.stdout.write(json.dumps(out, default=str) + "\n")
        sys.stdout.flush()
    mt5.shutdown()


if __name__ == "__main__":
    main()
