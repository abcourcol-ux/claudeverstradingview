#!/usr/bin/env python3
"""Telegram alerts for day-trader-skill signals.

Every --every seconds during the US session it runs trader-entry (opening-range
breakout, 5-minute bars) on each symbol. The first time a symbol triggers on a
given day it runs trader-exit (stop at the range midpoint, 2R target) and sends
ONE Telegram message: entry, stop, target, risk. It never places an order.

Standard library only. The token and chat id come from environment variables,
never from the command line or a file in the repo:

    TELEGRAM_BOT_TOKEN   the token BotFather gave you
    TELEGRAM_CHAT_ID     your chat id (send /start to the bot, then run `chat-id`)

Usage:
    python3 scripts/trader_signal_telegram.py test               # send a test message
    python3 scripts/trader_signal_telegram.py chat-id            # print the chat ids that wrote to the bot
    python3 scripts/trader_signal_telegram.py run                # loop until 15:55 New York
    python3 scripts/trader_signal_telegram.py run --once --dry-run

Symbols are LABEL:YAHOO pairs (default XAUUSD:GC=F BTCUSD:BTC-USD). GC=F is the
COMEX gold future, not spot XAUUSD: its levels differ from your broker's by a
few dollars. Not financial advice.
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(REPO, ".claude", "skills")
ENTRY = os.path.join(SKILLS, "trader-entry", "entry.py")
EXIT = os.path.join(SKILLS, "trader-exit", "exit.py")
DEFAULT_SYMBOLS = ["XAUUSD:GC=F", "BTCUSD:BTC-USD"]
STOP_AT = (15, 55)  # New York, matches flat_by


def ny_now():
    """Current New York time (US DST rules), without third-party tz data."""
    utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    y = utc.year
    mar = datetime.datetime(y, 3, 8) + datetime.timedelta(days=(6 - datetime.datetime(y, 3, 8).weekday()) % 7)
    nov = datetime.datetime(y, 11, 1) + datetime.timedelta(days=(6 - datetime.datetime(y, 11, 1).weekday()) % 7)
    dst = mar + datetime.timedelta(hours=7) <= utc < nov + datetime.timedelta(hours=6)
    return utc + datetime.timedelta(hours=-4 if dst else -5)


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


def run_json(cmd):
    p = subprocess.run([sys.executable, "-I"] + cmd, capture_output=True, text=True, timeout=120)
    try:  # entry.py exits non-zero for "waiting" but still prints its JSON
        return json.loads(p.stdout)
    except ValueError:
        msg = (p.stderr or p.stdout or "no output").strip().splitlines()
        raise RuntimeError(msg[-1] if msg else "failed")


def fmt(x):
    return "{:,.2f}".format(x).replace(",", " ")


def message(label, ysym, entry, plan):
    t = entry["trigger"]
    lines = [
        "SIGNAL %s (cassure du range d'ouverture, achat)" % label,
        "Données : %s 5 min (Yahoo), %s %s heure de New York" % (ysym, entry["date"], t["time"]),
        "Range 9:30-9:45 : %s - %s" % (fmt(entry["opening_range"]["low"]), fmt(entry["opening_range"]["high"])),
        "Entrée : %s (clôture %s)" % (fmt(plan["entry"]), t["time"]),
        "Stop : %s (%s)" % (fmt(plan["stop"]), plan.get("stop_label", "")),
        "Objectif : %s (%s)" % (fmt(plan["target"]), plan.get("target_label", "")),
        "Risque : %s par unité, à plat avant %s" % (fmt(plan["risk_per_share"]), plan.get("flat_by", "15:55")),
    ]
    last = entry.get("last") or {}
    if last.get("close") is not None:
        lines.append("Dernier prix : %s (bougie %s)" % (fmt(last["close"]), last.get("bar_start", "?")))
    for w in plan.get("warnings") or []:
        lines.append("Attention : %s" % w)
    lines.append("Aucun ordre passé. Pas un conseil financier.")
    return "\n".join(lines)


def load_state(path, today):
    try:
        with open(path, encoding="utf-8") as fh:
            st = json.load(fh)
    except (OSError, ValueError):
        st = {}
    return st if st.get("date") == today else {"date": today, "sent": []}


def save_state(path, st):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(st, fh, indent=2)


def check_all(a, symbols, now_ny):
    today = now_ny.date().isoformat()
    st = load_state(a.state, today)
    os.makedirs(os.path.dirname(a.state) or ".", exist_ok=True)
    for pair in symbols:
        label, _, ysym = pair.partition(":")
        ysym = ysym or label
        if label in st["sent"]:
            continue
        entry_path = os.path.join(os.path.dirname(a.state), "entry-%s.json" % label)
        cmd = [ENTRY, "check", ysym, "--setup", "orb", "--json", "--write", entry_path]
        if a.offline:
            cmd += ["--offline", os.path.join(a.offline, "%s.json" % label)]
        if a.now:
            cmd += ["--now", a.now]
        try:
            entry = run_json(cmd)
        except Exception as e:  # network hiccup, bad data: report and keep going
            print("%s: entry check failed: %s" % (label, e), flush=True)
            continue
        print("%s %s: %s" % (now_ny.strftime("%H:%M"), label, entry.get("status")), flush=True)
        if entry.get("status") != "triggered":
            continue
        pcmd = [EXIT, "plan", "--from", entry_path, "--stop", "or-mid", "--target", a.target, "--json"]
        if a.now:
            pcmd += ["--now", a.now]
        try:
            plan = run_json(pcmd)
        except Exception as e:
            send("SIGNAL %s déclenché, mais le plan de sortie a été refusé : %s" % (label, e), a.dry_run)
        else:
            send(message(label, ysym, entry, plan), a.dry_run)
        st["sent"].append(label)
        save_state(a.state, st)


def cmd_run(a):
    symbols = a.symbols or DEFAULT_SYMBOLS
    if not a.dry_run:
        creds()
    while True:
        now_ny = ny_now()
        if a.once or now_ny.weekday() < 5:
            if a.once or (9, 45) <= (now_ny.hour, now_ny.minute) < STOP_AT:
                check_all(a, symbols, now_ny)
        if a.once:
            return
        if (now_ny.hour, now_ny.minute) >= STOP_AT and not a.forever:
            print("15:55 New York: done for today.", flush=True)
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
    r = sub.add_parser("run", help="watch the symbols and send one message per signal per day")
    r.add_argument("--symbols", nargs="*", help="LABEL:YAHOO pairs, default %s" % " ".join(DEFAULT_SYMBOLS))
    r.add_argument("--every", type=int, default=60, help="seconds between checks (default 60)")
    r.add_argument("--target", default="2R", help="trader-exit target (default 2R)")
    r.add_argument("--state", default=os.path.join(REPO, "trader", "state", "telegram.json"))
    r.add_argument("--once", action="store_true", help="one pass, then exit")
    r.add_argument("--forever", action="store_true", help="keep running across days")
    r.add_argument("--dry-run", action="store_true", help="print the message instead of sending it")
    r.add_argument("--offline", help="folder of saved Yahoo chart JSON named LABEL.json (testing)")
    r.add_argument("--now", help='pin the New York clock for trader-entry, e.g. "2026-11-04 10:10" (testing)')
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
