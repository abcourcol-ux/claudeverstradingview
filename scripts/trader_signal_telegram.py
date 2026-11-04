#!/usr/bin/env python3
"""Telegram alerts for opening-range breakouts, BUY and SELL, in YOUR trading windows.

Each symbol has one or more trading windows in Andorra time (Europe/Andorra, same
clock as Paris). In every window the first 15 minutes make the range; after that,
the first 5-minute close above the range high is ACHAT, below the range low is
VENTE (the opening-range rule of day-trader-skill's trader-entry, applied to your
window instead of the 9:30 New York open, both sides). Default windows:

    XAUUSD (GC=F)    00:30-02:30 and 14:00-22:00
    BTCUSD (BTC-USD) 14:00-22:00

On a signal it sends one message:

    XAUUSD // VENTE
    Entrée : ...   SL : ... (range midpoint)   Objectif : ... (2R)
    Risque : Bas / Moyen / Risqué / Très risqué
    Commentaire : ...

then at most ONE "TROP TARD" message once taking it would no longer be the
planned trade (price 0.5R past the entry, back at the stop, at the target, or 10
minutes after the signal). One signal per symbol and window. The risk level comes
from replaying the same rule in the same window over the last 60 days of
5-minute bars. It never places an order. Not financial advice.

Standard library only: runs on Windows, Mac, Linux and Android (Termux).
Token and chat id come from environment variables:
    TELEGRAM_BOT_TOKEN   the token BotFather gave you
    TELEGRAM_CHAT_ID     your chat id (run the chat-id command)

Usage:
    python scripts/trader_signal_telegram.py test
    python scripts/trader_signal_telegram.py chat-id
    python scripts/trader_signal_telegram.py run
    python scripts/trader_signal_telegram.py run --symbols "XAUUSD:GC=F@00:30-02:30,14:00-22:00"
    python scripts/trader_signal_telegram.py run --once --dry-run

Symbols are LABEL:YAHOO@WINDOWS. GC=F is the COMEX gold future, not spot XAUUSD:
its levels are a few dollars away from your broker's.
"""
import argparse
import datetime
import importlib.util
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENTRY = os.path.join(REPO, ".claude", "skills", "trader-entry", "entry.py")
DEFAULT_SYMBOLS = ["XAUUSD:GC=F@00:30-02:30,14:00-22:00", "BTCUSD:BTC-USD@14:00-22:00"]
BAR = datetime.timedelta(minutes=5)
FLAT_BEFORE_END = datetime.timedelta(minutes=5)


def _load_entry():
    """trader-entry's Yahoo client and chart parser (it keeps the request polite)."""
    spec = importlib.util.spec_from_file_location("trader_entry", ENTRY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


E = _load_entry()


# ---------------------------------------------------------------- time (Andorra)

def _last_sunday(y, m):
    d = datetime.datetime(y + (m == 12), m % 12 + 1, 1) - datetime.timedelta(days=1)
    return d - datetime.timedelta(days=(d.weekday() + 1) % 7)


def local_offset(utc):
    """Hours Andorra is ahead of UTC: EU summer time from the last Sunday of March to the
    last Sunday of October, 01:00 UTC. Written out because Windows Python has no tz database."""
    y = utc.year
    dst = _last_sunday(y, 3) + datetime.timedelta(hours=1) <= utc < _last_sunday(y, 10) + datetime.timedelta(hours=1)
    return 2 if dst else 1


def to_local(utc):
    return utc + datetime.timedelta(hours=local_offset(utc))


def local_to_utc(local):
    return local - datetime.timedelta(hours=local_offset(local - datetime.timedelta(hours=1)))


def hm(dt):
    return dt.strftime("%H:%M")


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def parse_now(text):
    """--now "2026-11-04 15:10" is Andorra time."""
    return local_to_utc(datetime.datetime.strptime(text.strip().replace("T", " "), "%Y-%m-%d %H:%M"))


# ---------------------------------------------------------------- symbols and windows

def _hhmm(text):
    h, _, m = text.strip().partition(":")
    return datetime.time(int(h), int(m or 0))


def parse_symbol(spec):
    """'XAUUSD:GC=F@00:30-02:30,14:00-22:00' -> (label, yahoo, [(start, end), ...])."""
    name, _, wins = spec.partition("@")
    label, _, ysym = name.partition(":")
    label, ysym = label.strip().upper(), (ysym or label).strip()
    windows = []
    for w in (wins or "14:00-22:00").split(","):
        a, _, b = w.partition("-")
        try:
            s, e = _hhmm(a), _hhmm(b)
        except ValueError:
            sys.exit("bad window %r in %r: use HH:MM-HH:MM" % (w, spec))
        if not s < e:
            sys.exit("window %r in %r must end after it starts, on the same day" % (w, spec))
        windows.append((s, e))
    return label, ysym, windows


def window_times(day, w, a):
    """Local datetimes of one window on one local day."""
    start = datetime.datetime.combine(day, w[0])
    end = datetime.datetime.combine(day, w[1])
    or_end = start + datetime.timedelta(minutes=a.or_minutes)
    cutoff = max(or_end + BAR, end - datetime.timedelta(minutes=a.entry_cutoff))
    return {"start": start, "or_end": or_end, "cutoff": cutoff, "flat": end - FLAT_BEFORE_END, "end": end}


def trading_day(day, a):
    return a.weekends or day.weekday() < 5


# ---------------------------------------------------------------- telegram

def telegram(method, params, token):
    url = "https://api.telegram.org/bot%s/%s" % (token, method)
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20) as r:
        return json.loads(r.read().decode())


def creds(need_chat=True):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token:
        sys.exit("TELEGRAM_BOT_TOKEN is not set")
    if need_chat and not chat:
        sys.exit("TELEGRAM_CHAT_ID is not set (run the chat-id command first)")
    return token, chat


def send(text, dry_run):
    if dry_run:
        print("---- would send ----\n%s\n--------------------" % text, flush=True)
        return
    token, chat = creds()
    telegram("sendMessage", {"chat_id": chat, "text": text, "disable_web_page_preview": "true"}, token)
    print("sent to Telegram", flush=True)


# ---------------------------------------------------------------- data

def fmt(x):
    return "{:,.2f}".format(x).replace(",", " ")


def load_bars(label, ysym, rng, a):
    """Yahoo 5-minute bars as dicts with local start/end datetimes, oldest first."""
    if a.offline:
        with open(os.path.join(a.offline, "%s.json" % label), encoding="utf-8") as fh:
            text = fh.read()
    else:
        text = E.yahoo_get(E.chart_path(ysym, rng, "5m"))
    bars = []
    for b in E.parse_chart(text, ysym)["bars"]:
        if b["t"] % 300:
            continue                       # off-grid tick (the live price), not a bar
        start = to_local(datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=b["t"]))
        bars.append(dict(b, start=start, end=start + BAR))
    return bars


def history_bars(label, ysym, a, state_dir, today):
    """60 days of 5-minute bars, fetched once a day per symbol."""
    if a.offline:
        return load_bars(label, ysym, "60d", a)
    path = os.path.join(state_dir, "hist-%s.json" % label)
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        if doc.get("date") == today:
            return [dict(b, start=datetime.datetime.fromisoformat(b["start"]),
                         end=datetime.datetime.fromisoformat(b["end"])) for b in doc["bars"]]
    except (OSError, ValueError, KeyError):
        pass
    bars = load_bars(label, ysym, "60d", a)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"date": today, "bars": [dict(b, start=b["start"].isoformat(), end=b["end"].isoformat())
                                           for b in bars]}, fh)
    return bars


# ---------------------------------------------------------------- the rule

def find_signal(bars, wt, now_local):
    """First completed 5-minute close outside the window's opening range, or None.
    Returns (signal, range) where range is None until it is complete."""
    rng = [b for b in bars if wt["start"] <= b["start"] < wt["or_end"]]
    if not rng or now_local < wt["or_end"]:
        return None, None
    hi, lo = max(b["h"] for b in rng), min(b["l"] for b in rng)
    info = {"high": hi, "low": lo, "bars": len(rng)}
    for b in bars:
        if b["start"] < wt["or_end"] or b["end"] > wt["cutoff"] or b["end"] > now_local:
            continue
        side = "buy" if b["c"] > hi else "sell" if b["c"] < lo else None
        if side:
            return {"side": side, "entry": round(b["c"], 2), "end": b["end"], "or_high": hi, "or_low": lo}, info
    return None, info


def make_plan(sig, target_r):
    mid = (sig["or_high"] + sig["or_low"]) / 2
    if sig["side"] == "buy":
        stop = math.floor(mid * 100 + 1e-6) / 100
        risk = round(sig["entry"] - stop, 2)
        target = round(sig["entry"] + target_r * risk, 2)
    else:
        stop = math.ceil(mid * 100 - 1e-6) / 100
        risk = round(stop - sig["entry"], 2)
        target = round(sig["entry"] - target_r * risk, 2)
    return dict(sig, stop=round(stop, 2), risk=risk, target=target, target_r=target_r)


def outcome(plan, bars, flat):
    """target / stop / neither by the flat time. A bar that touches both counts as the stop."""
    s = 1 if plan["side"] == "buy" else -1
    for b in bars:
        if b["start"] < plan["end"] or b["end"] > flat:
            continue
        worst, best = (b["l"], b["h"]) if s == 1 else (b["h"], b["l"])
        if s * (worst - plan["stop"]) <= 0:
            return "stop"
        if s * (best - plan["target"]) >= 0:
            return "target"
    return "neither"


def replay(bars, w, a, today):
    """The same rule in the same window on every past day in the bars."""
    days = sorted({b["start"].date() for b in bars if b["start"].date() < today})
    res = {"sessions": 0, "signals": 0, "buy": 0, "sell": 0, "target": 0, "stop": 0, "neither": 0}
    for d in days:
        if not trading_day(d, a):
            continue
        wt = window_times(d, w, a)
        day_bars = [b for b in bars if wt["start"] <= b["start"] < wt["end"]]
        if len(day_bars) < (wt["end"] - wt["start"]) / BAR * 0.8:
            continue                       # market closed or too many gaps
        res["sessions"] += 1
        sig, _ = find_signal(day_bars, wt, wt["end"])
        if not sig:
            continue
        plan = make_plan(sig, a.target_r)
        if plan["risk"] <= 0:
            continue
        res["signals"] += 1
        res[plan["side"]] += 1
        res[outcome(plan, day_bars, wt["flat"])] += 1
    return res


LEVELS = ["Bas", "Moyen", "Risqué", "Très risqué"]


def risk_level(hist, plan):
    """From the replay: the share of decided trades that hit the target, minus the share
    needed to break even at this R (33 % at 2R). Fewer than 10 signals is at least Risqué;
    a stop wider than 1.5 % of the price moves it up one level."""
    decided = hist["target"] + hist["stop"]
    if decided == 0:
        i = 2
    else:
        d = hist["target"] / decided - 1.0 / (1.0 + plan["target_r"])
        i = 0 if d >= 0.05 else 1 if d > -0.05 else 2 if d > -0.15 else 3
        if hist["signals"] < 10:
            i = max(i, 2)
    wide = plan["risk"] / plan["entry"] > 0.015
    return LEVELS[min(3, i + wide)], wide


def late_reason(plan, last, minutes_since, a):
    s = 1 if plan["side"] == "buy" else -1
    if last is not None:
        if s * (last - plan["stop"]) <= 0:
            return "le prix (%s) est revenu au stop : signal invalidé" % fmt(last)
        if s * (last - plan["target"]) >= 0:
            return "le prix (%s) a déjà atteint l'objectif" % fmt(last)
        moved = s * (last - plan["entry"]) / plan["risk"]
        if moved >= a.late_r:
            return "le prix (%s) est déjà à %.2fR au-delà de l'entrée" % (fmt(last), moved)
    if minutes_since > a.late_minutes:
        return "le signal date de %d minutes" % minutes_since
    return None


# ---------------------------------------------------------------- messages

def head(label, plan, late=False):
    side = "ACHAT" if plan["side"] == "buy" else "VENTE"
    return ["%s%s // %s" % ("TROP TARD // " if late else "", label, side),
            "Entrée : %s" % fmt(plan["entry"]),
            "SL : %s" % fmt(plan["stop"]),
            "Objectif : %s" % fmt(plan["target"])]


def signal_message(label, ysym, plan, wt, hist, hist_error):
    side_txt = "haut" if plan["side"] == "buy" else "bas"
    level_px = plan["or_high"] if plan["side"] == "buy" else plan["or_low"]
    parts = ["Cassure du %s du range %s-%s (%s), clôture 5 min à %s heure d'Andorre (%s)."
             % (side_txt, hm(wt["start"]), hm(wt["or_end"]), fmt(level_px), hm(plan["end"]), ysym),
             "SL au milieu du range, objectif à %gR, risque %s par unité." % (plan["target_r"], fmt(plan["risk"]))]
    if hist and hist["signals"]:
        level, wide = risk_level(hist, plan)
        parts.append("Historique de cette fenêtre (%d séances, 60 jours) : %d signaux, %d objectif(s), %d SL, %d ni l'un ni l'autre."
                     % (hist["sessions"], hist["signals"], hist["target"], hist["stop"], hist["neither"]))
        if hist["signals"] < 10:
            parts.append("Échantillon petit : peu fiable.")
        if wide:
            parts.append("SL large (plus de 1,5 % du prix).")
    else:
        level = "Risqué"
        parts.append("Historique indisponible (%s) : risque non mesuré." % (hist_error or "aucun signal passé"))
    parts.append("À plat avant %s. Aucun ordre passé." % hm(wt["flat"]))
    return "\n".join(head(label, plan) + ["Risque : %s" % level, "Commentaire : " + " ".join(parts)])


def late_message(label, plan, last, reason, alarm_sent):
    parts = ["Trop tard : %s." % reason]
    if last is not None:
        s = 1 if plan["side"] == "buy" else -1
        if s * (last - plan["stop"]) > 0:
            parts.append("Entrer maintenant à %s risquerait %s par unité au lieu de %s."
                         % (fmt(last), fmt(abs(last - plan["stop"])), fmt(plan["risk"])))
    parts.append("Signal d'origine à %s heure d'Andorre." % hm(plan["end"]))
    if not alarm_sent:
        parts.append("Détecté trop tard pour l'alarme d'entrée.")
    parts.append("Ne pas courir après le prix. Aucun ordre passé.")
    return "\n".join(head(label, plan, late=True) + ["Risque : Très risqué", "Commentaire : " + " ".join(parts)])


# ---------------------------------------------------------------- the loop

def load_state(path, today):
    try:
        with open(path, encoding="utf-8") as fh:
            st = json.load(fh)
    except (OSError, ValueError):
        st = {}
    if st.get("date") != today or not isinstance(st.get("sent"), dict):
        return {"date": today, "sent": {}}
    return st


def save_state(path, st):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(st, fh, indent=2)


def active_windows(symbols, now_local, a):
    """(label, ysym, window, times) for every window where a check makes sense now."""
    day = now_local.date()
    out = []
    if not trading_day(day, a):
        return out
    for label, ysym, wins in symbols:
        for w in wins:
            wt = window_times(day, w, a)
            if wt["or_end"] <= now_local < wt["flat"]:
                out.append((label, ysym, w, wt))
    return out


def next_window(symbols, now_local, a):
    best = None
    for k in range(8):
        day = now_local.date() + datetime.timedelta(days=k)
        if not trading_day(day, a):
            continue
        for label, _, wins in symbols:
            for w in wins:
                wt = window_times(day, w, a)
                if wt["flat"] > now_local and (best is None or wt["start"] < best[0]):
                    best = (wt["start"], label)
    return best


def check(a, symbols, now_utc):
    now_local = to_local(now_utc)
    today = now_local.date()
    stamp = hm(now_local)
    state_dir = os.path.dirname(a.state) or "."
    os.makedirs(state_dir, exist_ok=True)
    st = load_state(a.state, today.isoformat())
    live = {}
    for label, ysym, w, wt in active_windows(symbols, now_local, a):
        key = "%s@%s" % (label, hm(wt["start"]))
        done = st["sent"].setdefault(key, [])
        if "late" in done:
            continue
        try:
            if label not in live:
                live[label] = load_bars(label, ysym, "5d", a)
            bars = live[label]
        except Exception as e:  # network hiccup, bad data: report and keep going
            print("%s %s: check failed: %s" % (stamp, key, e), flush=True)
            continue
        sig, rng = find_signal(bars, wt, now_local)
        if not sig:
            print("%s %s: %s" % (stamp, key, "waiting (range %s-%s)" % (fmt(rng["low"]), fmt(rng["high"]))
                                 if rng else "no data for the range"), flush=True)
            continue
        plan = make_plan(sig, a.target_r)
        if plan["risk"] <= 0:
            print("%s %s: signal with no room for a stop, skipped" % (stamp, key), flush=True)
            continue
        print("%s %s: %s signal" % (stamp, key, "ACHAT" if plan["side"] == "buy" else "VENTE"), flush=True)
        done_bars = [b for b in bars if b["start"] <= now_local]
        last = done_bars[-1]["c"] if done_bars else None
        minutes = int((now_local - plan["end"]).total_seconds() // 60)
        reason = late_reason(plan, last, minutes, a)
        if reason:
            send(late_message(label, plan, last, reason, "entry" in done), a.dry_run)
            done.append("late")
        elif "entry" not in done:
            hist, err = None, None
            try:
                hist = replay(history_bars(label, ysym, a, state_dir, today.isoformat()), w, a, today)
            except Exception as e:
                err = str(e)
            send(signal_message(label, ysym, plan, wt, hist, err), a.dry_run)
            done.append("entry")
        save_state(a.state, st)


def cmd_run(a):
    symbols = [parse_symbol(s) for s in (a.symbols or DEFAULT_SYMBOLS)]
    fixed = parse_now(a.now) if a.now else None
    if not a.dry_run:
        creds()
    for label, ysym, wins in symbols:
        print("%s (%s): %s heure d'Andorre" % (label, ysym, ", ".join("%s-%s" % (hm(datetime.datetime.combine(
            datetime.date.today(), s)), hm(datetime.datetime.combine(datetime.date.today(), e))) for s, e in wins)),
            flush=True)
    idle = None
    while True:
        now_utc = fixed or utc_now()
        now_local = to_local(now_utc)
        if a.once or active_windows(symbols, now_local, a):
            idle = None
            check(a, symbols, now_utc)
        else:
            nxt = next_window(symbols, now_local, a)
            msg = "prochaine fenêtre : %s %s" % (nxt[1], nxt[0].strftime("%d/%m %H:%M")) if nxt else "aucune fenêtre"
            if msg != idle:
                print("%s %s (signaux possibles 15 min après le début)" % (hm(now_local), msg), flush=True)
                idle = msg
        if a.once:
            return
        time.sleep(a.every)


def cmd_test(a):
    send("Test : le bot des signaux fonctionne. Aucun ordre ne sera jamais passé.", a.dry_run)


def cmd_chat_id(a):
    token, _ = creds(need_chat=False)
    res = telegram("getUpdates", {}, token)
    seen = {}
    for u in res.get("result", []):
        chat = (u.get("message") or u.get("channel_post") or {}).get("chat") or {}
        if chat.get("id") is not None:
            seen[chat["id"]] = chat.get("username") or chat.get("title") or chat.get("first_name") or ""
    if not seen:
        print("No messages yet: send /start to your bot in Telegram, then run this again.")
    for cid, name in seen.items():
        print("%s  %s" % (cid, name))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="watch the symbols in their windows: a signal message, then a too-late message")
    r.add_argument("--symbols", nargs="*",
                   help="LABEL:YAHOO@HH:MM-HH:MM[,HH:MM-HH:MM] in Andorra time, default %s" % " ".join(DEFAULT_SYMBOLS))
    r.add_argument("--every", type=int, default=60, help="seconds between checks (default 60)")
    r.add_argument("--or-minutes", type=int, default=15, help="opening range length in minutes (default 15)")
    r.add_argument("--entry-cutoff", type=int, default=60,
                   help="no new signal in the last N minutes of a window (default 60)")
    r.add_argument("--target-r", type=float, default=2.0, help="target in R (default 2)")
    r.add_argument("--late-r", type=float, default=0.5,
                   help="too late once the price is this many R past the entry (default 0.5)")
    r.add_argument("--late-minutes", type=int, default=10,
                   help="too late this many minutes after the signal bar closed (default 10)")
    r.add_argument("--weekends", action="store_true", help="also watch on Saturday and Sunday (crypto)")
    r.add_argument("--state", default=os.path.join(REPO, "trader", "state", "telegram.json"))
    r.add_argument("--once", action="store_true", help="one pass, then exit")
    r.add_argument("--forever", action="store_true", help=argparse.SUPPRESS)  # old flag: it now always runs on
    r.add_argument("--dry-run", action="store_true", help="print the message instead of sending it")
    r.add_argument("--offline", help="folder of saved Yahoo chart JSON named LABEL.json (testing)")
    r.add_argument("--now", help='pin the Andorra clock, e.g. "2026-11-04 15:10" (testing)')
    r.set_defaults(fn=cmd_run)
    t = sub.add_parser("test", help="send a test message")
    t.add_argument("--dry-run", action="store_true")
    t.set_defaults(fn=cmd_test)
    c = sub.add_parser("chat-id", help="list chat ids that wrote to the bot")
    c.set_defaults(fn=cmd_chat_id)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
