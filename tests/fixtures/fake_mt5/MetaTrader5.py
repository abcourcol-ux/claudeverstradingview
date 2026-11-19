"""Faux module MetaTrader5 pour tester mt5_bridge.py sans Windows ni terminal."""
import os
from types import SimpleNamespace as NS

TRADE_ACTION_DEAL = 1
ORDER_TYPE_BUY, ORDER_TYPE_SELL = 0, 1
POSITION_TYPE_BUY, POSITION_TYPE_SELL = 0, 1
ORDER_TIME_GTC = 0
ORDER_FILLING_FOK, ORDER_FILLING_IOC = 0, 1
TRADE_RETCODE_DONE = 10009
DEAL_ENTRY_IN, DEAL_ENTRY_OUT, DEAL_ENTRY_OUT_BY = 0, 1, 3
DEAL_REASON_SL, DEAL_REASON_TP = 4, 5

_mode = int(os.environ.get("FAKE_MT5_TRADE_MODE", "0"))
_positions, _deals, _sent = [], [], []
_next = [1000]


def initialize(**kw): return True
def shutdown(): return True
def last_error(): return (1, "ok")
def account_info(): return NS(login=10072219, server="Axi-Demo", trade_mode=_mode, currency="USD", balance=5000.0, equity=4960.0, margin_free=4960.0, leverage=1000)
def symbol_select(sym, on): return sym == "NVIDIA+"
def symbol_info(sym): return NS(name=sym, description="NVIDIA Corp", trade_contract_size=1.0, volume_min=1.0, volume_max=20000.0, volume_step=1.0, digits=2, point=0.01, trade_stops_level=0, trade_mode=4, filling_mode=3)
def symbol_info_tick(sym): return NS(bid=180.00, ask=180.05)
def symbols_get(flt=None): return [NS(name="NVIDIA+", description="NVIDIA Corp", path="SHARES\\US\\NVIDIA+")]


def order_send(req):
    _sent.append(req)
    _next[0] += 1
    t = _next[0]
    if "position" in req:
        global _positions
        _positions = [p for p in _positions if p.ticket != req["position"]]
        _deals.append(NS(position_id=req["position"], entry=DEAL_ENTRY_OUT, price=req["price"], profit=-12.5, swap=0.0, commission=-1.0, reason=0))
    else:
        _positions.append(NS(ticket=t, symbol=req["symbol"], type=req["type"], volume=req["volume"], price_open=req["price"], price_current=req["price"], sl=req["sl"], tp=req["tp"], profit=0.0, magic=req["magic"]))
        _deals.append(NS(position_id=t, entry=DEAL_ENTRY_IN, price=req["price"], profit=0.0, swap=0.0, commission=-1.0, reason=0))
    return NS(retcode=TRADE_RETCODE_DONE, order=t, deal=t, price=req["price"], volume=req["volume"], comment="done")


def positions_get(ticket=None, symbol=None):
    return [p for p in _positions if ticket is None or p.ticket == ticket]


def history_deals_get(a, b, position=None):
    return [d for d in _deals if d.position_id == position]
