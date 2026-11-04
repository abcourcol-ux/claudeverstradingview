#!/usr/bin/env python3
"""Telegram alerts for day-trader-skill opening-range signals, BUY and SELL.

Every --every seconds during the US session it reads today's 5-minute bars
(Yahoo, through trader-entry's own code) for each symbol and looks for the first
5-minute close above the 15-minute opening range (ACHAT) or below it (VENTE).
The buy rule is trader-entry's. The sell rule is its mirror image, done here,
because the day-trader-skill v2 tools plan longs only.

On a signal it sends one message:

    BTCUSD // ACHAT
    Entrée : ...   SL : ... (range midpoint)   Objectif : ... (2R)
    Risque : Bas / Moyen / Risqué / Très risqué   (from trader-timemachine)
    Commentaire : ...

and later ONE "TROP TARD" message once taking it would no longer be the
planned trade (price 0.5R past the entry, back at the stop, at the target, or
10 minutes after the signal). Times are Andorra time (Europe/Andorra). It
never places an order. Not financial advice.

Standard library only. Token and chat id come from environment variables:
    TELEGRAM_BOT_TOKEN   the token BotFather gave you
    TELEGRAM_CHAT_ID     your chat id (run the chat-id command)

Usage:
    python scripts/trader_signal_telegram.py test
    python scripts/trader_signal_telegram.py chat-id
    python scripts/trader_signal_telegram.py run
    python scripts/trader_signal_telegram.py run --once --dry-run

Symbols are LABEL:YAHOO pairs (default XAUUSD:GC=F BTCUSD:BTC-USD). GC=F is the
COMEX gold future, not spot XAUUSD: its levels differ from your broker's.
"""
import argparse
import datetime
import importlib.util
import json
import math
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(REPO, ".claude", "skills")
ENTRY = os.path.join(SKILLS, "trader-entry", "entry.py")
TM = os.path.join(SKILLS, "trader-timemachine", "timemachine.py")
DEFAULT_SYMBOLS = ["XAUUSD:GC=F", "BTCUSD:BTC-USD"]
FLAT_BY = (15, 55)          # New York
OR_BARS = 3                 # 15-minute range on 5-minute bars


def _load_entry():
    spec = importlib.util.spec_from_file_location("trader_entry", ENTRY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


E = _load_entry()


# ---------------------------------------------------------------- time

def _last_sunday(y, m):
    d = datetime.datetime(y + (m == 12), m % 12 + 1, 1) - datetime.timedelta(days=1)
    return d - datetime.timedelta(days=(d.weekday() + 1) % 7)


def local_offset(utc):
    """UTC -> Andorra (same as Paris): EU summer time from the last Sunday of March to the
    last Sunday of October, 01:00 UTC. Written out because Windows Python has no tz database."""
    y = utc.year
    dst = _last_sunday(y, 3) + datetime.timedelta(hours=1) <= utc < _last_sunday(y, 10) + datetime.timedelta(hours=1)
    return 2 if dst else 1


def hm_local(utc):
    return (utc + datetime.timedelta(hours=local_offset(utc))).strftime("%H:%M")


def hm_local_ny(ny):
    return hm_local(E.eastern_to_utc(ny))


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


# ---------------------------------------------------------------- signal

def fmt(x):
    return "{:,.2f}".format(x).replace(",", " ")


def read_chart(label, ysym, offline):
    if offline:
        with open(os.path.join(offline, "%s.json" % label), encoding="utf-8") as fh:
            return fh.read()
    return E.yahoo_get(E.chart_path(ysym, "1d", "5m"))


def find_signal(res):
    """trader-entry's evaluate() result -> the first buy or sell trigger, or None."""
    rng = res.get("opening_range") or {}
    if not rng.get("complete") or res.get("phase") in ("pre-open", "forming", "closed"):
        return None
    day = datetime.date.fromisoformat(res["date"])
    before = datetime.datetime.combine(day, E.parse_hhmm(res["no_entries_before"], "before"))
    cutoff = datetime.datetime.combine(day, E.parse_hhmm(res["no_entries_after"], "cutoff"))
    hi, lo = rng["high"], rng["low"]
    for b in res.get("_bars") or []:
        if b["slot"] < OR_BARS or b["end"] < before or b["end"] > cutoff:
            continue
        if b["c"] > hi:
            side = "buy"
        elif b["c"] < lo:
            side = "sell"
        else:
            continue
        return {"side": side, "entry": round(b["c"], 2), "end": b["end"], "or_high": hi, "or_low": lo,
                "entry_time": b["end"].strftime("%I:%M %p").lstrip("0")}
    return None


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


# ---------------------------------------------------------------- risk level (trader-timemachine)

LEVELS = ["Bas", "Moyen", "Risqué", "Très risqué"]


def time_machine(label, ysym, plan, a, state_dir):
    """Run trader-timemachine on the plan. Returns its JSON or raises."""
    if a.offline:
        path = os.path.join(a.offline, "%s.json" % label)
    else:
        text = E.yahoo_get(E.chart_path(ysym, "60d", "5m"))
        doc = json.loads(text)
        doc["chart"]["result"][0]["meta"]["symbol"] = label   # the tool wants a plain ticker
        path = os.path.join(state_dir, "tm-%s-60d.json" % label)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
    cmd = [sys.executable, "-I", TM, "run", "--symbol", label, "--side", plan["side"],
           "--date", plan["end"].date().isoformat(), "--entry", str(plan["entry"]), "--stop", str(plan["stop"]),
           "--target", str(plan["target"]), "--entry-time", plan["entry_time"], "--setup", "orb",
           "--stop-rule", "or_mid", "--until", "%02d:%02d" % FLAT_BY, "--offline", path, "--json",
           "--now", (a.now_utc or E.utc_now()).strftime("%Y-%m-%dT%H:%M:%SZ")]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    try:
        return json.loads(p.stdout)
    except ValueError:
        lines = (p.stderr or p.stdout or "no output").strip().splitlines()
        raise RuntimeError(lines[-1] if lines else "failed")


def risk_level(tm, plan):
    """Bas / Moyen / Risqué / Très risqué, and whether the stop is wide.
    From the Time Machine: among the replays that hit a side, how often the target came
    first, minus the share needed to break even at this R (33 % at 2R). A stop wider than
    1.5 % of the price moves it up one level."""
    mc = tm["mc"]
    pt, ps = mc["p_target"], mc["p_stop"]
    if pt + ps <= 0:
        i = 2
    else:
        d = pt / (pt + ps) - 1.0 / (1.0 + plan["target_r"])
        i = 0 if d >= 0.05 else 1 if d > -0.05 else 2 if d > -0.15 else 3
    wide = plan["risk"] / plan["entry"] > 0.015
    return LEVELS[min(3, i + wide)], wide


# ---------------------------------------------------------------- messages

def head(label, plan, late=False):
    side = "ACHAT" if plan["side"] == "buy" else "VENTE"
    return ["%s // %s%s" % (label, side, " // TROP TARD" if late else ""),
            "Entrée : %s" % fmt(plan["entry"]),
            "SL : %s" % fmt(plan["stop"]),
            "Objectif : %s" % fmt(plan["target"])]


def signal_message(label, ysym, plan, tm, tm_error, open_ny):
    side_txt = "haut" if plan["side"] == "buy" else "bas"
    level_px = plan["or_high"] if plan["side"] == "buy" else plan["or_low"]
    or_end = open_ny + datetime.timedelta(minutes=15)
    flat = datetime.datetime.combine(open_ny.date(), datetime.time(*FLAT_BY))
    parts = ["Cassure du %s du range %s-%s (%s), clôture 5 min à %s heure d'Andorre (%s)."
             % (side_txt, hm_local_ny(open_ny), hm_local_ny(or_end), fmt(level_px), hm_local_ny(plan["end"]), ysym),
             "SL au milieu du range, objectif à %gR, risque %s par unité." % (plan["target_r"], fmt(plan["risk"]))]
    if tm:
        level, wide = risk_level(tm, plan)
        mc, h = tm["mc"], tm["history"]
        parts.append("Time Machine (%d séances) : objectif d'abord %.0f %%, SL d'abord %.0f %%, ni l'un ni l'autre %.0f %% ; "
                     "historique : %d objectif(s) sur %d signaux."
                     % (mc.get("pool_sessions", 0), 100 * mc["p_target"], 100 * mc["p_stop"], 100 * mc["p_neither"],
                        sum(1 for t in h.get("trades", []) if t.get("outcome") == "target"), h.get("triggered", 0)))
        if wide:
            parts.append("SL large (plus de 1,5 % du prix).")
    else:
        level = "Risqué"
        parts.append("Time Machine indisponible (%s) : risque non mesuré." % tm_error)
    if plan["side"] == "sell":
        parts.append("Vente : règle miroir, les skills ne testent que l'achat.")
    parts.append("À plat avant %s. Aucun ordre passé." % hm_local_ny(flat))
    return "\n".join(head(label, plan) + ["Risque : %s" % level, "Commentaire : " + " ".join(parts)])


def late_message(label, plan, last, reason, alarm_sent):
    parts = ["Trop tard : %s." % reason]
    if last is not None:
        s = 1 if plan["side"] == "buy" else -1
        if s * (last - plan["stop"]) > 0:
            parts.append("Entrer maintenant à %s risquerait %s par unité au lieu de %s."
                         % (fmt(last), fmt(abs(last - plan["stop"])), fmt(plan["risk"])))
    parts.append("Signal d'origine à %s heure d'Andorre." % hm_local_ny(plan["end"]))
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


def check_all(a, symbols):
    now_utc = a.now_utc or E.utc_now()
    now_ny = E.to_eastern(now_utc)
    state_dir = os.path.dirname(a.state) or "."
    os.makedirs(state_dir, exist_ok=True)
    st = load_state(a.state, now_ny.date().isoformat())
    stamp = hm_local(now_utc)
    for pair in symbols:
        label, _, ysym = pair.partition(":")
        ysym = ysym or label
        done = st["sent"].setdefault(label, [])
        if "late" in done:
            continue
        try:
            res = E.evaluate(E.parse_chart(read_chart(label, ysym, a.offline), ysym), now_utc)
        except Exception as e:  # network hiccup, bad data: report and keep going
            print("%s %s: check failed: %s" % (stamp, label, e), flush=True)
            continue
        sig = find_signal(res)
        if not sig:
            print("%s %s: %s" % (stamp, label, "waiting" if res.get("status") != "no-data" else res.get("reason")),
                  flush=True)
            continue
        plan = make_plan(sig, a.target_r)
        if plan["risk"] <= 0:
            print("%s %s: signal with no room for a stop, skipped" % (stamp, label), flush=True)
            continue
        print("%s %s: %s signal" % (stamp, label, "ACHAT" if plan["side"] == "buy" else "VENTE"), flush=True)
        last = (res.get("last") or {}).get("close")
        minutes = int((now_ny - plan["end"]).total_seconds() // 60)
        reason = late_reason(plan, last, minutes, a)
        if reason:
            send(late_message(label, plan, last, reason, "entry" in done), a.dry_run)
            done.append("late")
        elif "entry" not in done:
            tm, err = None, None
            try:
                tm = time_machine(label, ysym, plan, a, state_dir)
                if "mc" not in tm:
                    tm, err = None, tm.get("error") or "no result"
            except Exception as e:
                err = str(e)
            open_ny = datetime.datetime.combine(plan["end"].date(), datetime.time(9, 30))
            send(signal_message(label, ysym, plan, tm, err, open_ny), a.dry_run)
            done.append("entry")
        save_state(a.state, st)


def cmd_run(a):
    symbols = a.symbols or DEFAULT_SYMBOLS
    a.now_utc = E.parse_now(a.now) if a.now else None
    if not a.dry_run:
        creds()
    while True:
        now_ny = E.to_eastern(a.now_utc or E.utc_now())
        in_hours = now_ny.weekday() < 5 and (9, 45) <= (now_ny.hour, now_ny.minute) < FLAT_BY
        if a.once or in_hours:
            check_all(a, symbols)
        if a.once:
            return
        if (now_ny.hour, now_ny.minute) >= FLAT_BY and not a.forever:
            print("%s (15:55 New York): done for today." % hm_local(E.utc_now()), flush=True)
            return
        time.sleep(a.every)


def cmd_test(a):
    send("Test : le bot des signaux day-trader-skill fonctionne. Aucun ordre ne sera jamais passé.", a.dry_run)


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
    r = sub.add_parser("run", help="watch the symbols: a signal message, then a too-late message")
    r.add_argument("--symbols", nargs="*", help="LABEL:YAHOO pairs, default %s" % " ".join(DEFAULT_SYMBOLS))
    r.add_argument("--every", type=int, default=60, help="seconds between checks (default 60)")
    r.add_argument("--target-r", type=float, default=2.0, help="target in R (default 2)")
    r.add_argument("--late-r", type=float, default=0.5,
                   help="too late once the price is this many R past the entry (default 0.5)")
    r.add_argument("--late-minutes", type=int, default=10,
                   help="too late this many minutes after the signal bar closed (default 10)")
    r.add_argument("--state", default=os.path.join(REPO, "trader", "state", "telegram.json"))
    r.add_argument("--once", action="store_true", help="one pass, then exit")
    r.add_argument("--forever", action="store_true", help="keep running across days")
    r.add_argument("--dry-run", action="store_true", help="print the message instead of sending it")
    r.add_argument("--offline", help="folder of saved Yahoo chart JSON named LABEL.json (testing)")
    r.add_argument("--now", help='pin the New York clock, e.g. "2026-11-04 10:10" (testing)')
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
