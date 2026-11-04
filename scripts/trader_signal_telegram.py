#!/usr/bin/env python3
"""Telegram alerts for day-trader-skill signals.

Every --every seconds during the US session it runs trader-entry (opening-range
breakout, 5-minute bars) on each symbol. The first time a symbol triggers on a
given day it runs trader-exit (stop at the range midpoint, 2R target) and sends
an ENTRY ALARM (entry, stop, target, risk). Later, once buying would no longer be
the planned trade (price 0.5R above the entry, back at the stop, at the target, or
10 minutes after the signal) it sends ONE "too late" message. Times are shown in
Andorra time (Europe/Andorra, same as Paris). It never places an order.

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


def _nth_sunday(y, m, n):
    d = datetime.datetime(y, m, 1)
    d += datetime.timedelta(days=(6 - d.weekday()) % 7)
    return d + datetime.timedelta(weeks=n - 1)


def _last_sunday(y, m):
    d = datetime.datetime(y + (m == 12), m % 12 + 1, 1) - datetime.timedelta(days=1)
    return d - datetime.timedelta(days=(d.weekday() + 1) % 7)


def ny_offset(utc):
    """Hours from UTC to New York (US DST: 2nd Sunday of March to 1st Sunday of November)."""
    y = utc.year
    dst = _nth_sunday(y, 3, 2) + datetime.timedelta(hours=7) <= utc < _nth_sunday(y, 11, 1) + datetime.timedelta(hours=6)
    return -4 if dst else -5


def local_offset(utc):
    """Hours from UTC to Andorra (Europe/Andorra, same as Paris: EU DST, last Sunday of March/October 01:00 UTC).
    Written out by hand because Windows Python has no time-zone database without the tzdata package."""
    y = utc.year
    dst = _last_sunday(y, 3) + datetime.timedelta(hours=1) <= utc < _last_sunday(y, 10) + datetime.timedelta(hours=1)
    return 2 if dst else 1


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def ny_now():
    utc = utc_now()
    return utc + datetime.timedelta(hours=ny_offset(utc))


def to_local(utc):
    return utc + datetime.timedelta(hours=local_offset(utc))


def ny_to_utc(date_iso, clock):
    """'2026-11-04', '9:50 AM' (New York) -> naive UTC datetime."""
    t = datetime.datetime.strptime("%s %s" % (date_iso, clock.strip().upper()), "%Y-%m-%d %I:%M %p")
    for off in (-4, -5):
        u = t - datetime.timedelta(hours=off)
        if ny_offset(u) == off:
            return u
    return t + datetime.timedelta(hours=5)


def hm_local(utc):
    return to_local(utc).strftime("%H:%M")


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


def header_lines(entry, plan):
    t = entry["trigger"]
    trig_utc = ny_to_utc(entry["date"], t["time"])
    open_utc = ny_to_utc(entry["date"], "9:30 AM")
    or_end = open_utc + datetime.timedelta(minutes=entry["opening_range"].get("minutes", 15))
    hh, mm = (int(x) for x in str(plan.get("flat_by", "15:55")).split(":"))
    flat_utc = ny_to_utc(entry["date"], datetime.time(hh, mm).strftime("%I:%M %p"))
    return trig_utc, [
        "Range %s-%s : %s - %s" % (hm_local(open_utc), hm_local(or_end),
                                   fmt(entry["opening_range"]["low"]), fmt(entry["opening_range"]["high"])),
        "Entrée : %s (clôture de %s)" % (fmt(plan["entry"]), hm_local(trig_utc)),
        "Stop : %s (%s)" % (fmt(plan["stop"]), plan.get("stop_label", "")),
        "Objectif : %s (%s)" % (fmt(plan["target"]), plan.get("target_label", "")),
        "Risque : %s par unité, à plat avant %s" % (fmt(plan["risk_per_share"]), hm_local(flat_utc)),
    ]


def entry_message(label, ysym, entry, plan):
    trig_utc, lines = header_lines(entry, plan)
    out = ["ALARME ENTRÉE %s (cassure du range d'ouverture, achat)" % label,
           "Signal à %s, heure d'Andorre (%s, 5 min, Yahoo)" % (hm_local(trig_utc), ysym)] + lines
    last = entry.get("last") or {}
    if last.get("close") is not None:
        out.append("Dernier prix : %s" % fmt(last["close"]))
    out += ["Attention : %s" % w for w in plan.get("warnings") or []]
    out.append("Aucun ordre passé. Pas un conseil financier.")
    return "\n".join(out)


def late_reason(entry, plan, a):
    """Why buying now is no longer the planned trade, or None."""
    last = (entry.get("last") or {}).get("close")
    risk = plan["risk_per_share"]
    if last is not None and last <= plan["stop"]:
        return "le prix (%s) est revenu au stop ou en dessous : signal invalidé" % fmt(last)
    if last is not None and last >= plan["target"]:
        return "le prix (%s) a déjà atteint l'objectif" % fmt(last)
    if last is not None and risk > 0 and (last - plan["entry"]) / risk >= a.late_r:
        return "le prix (%s) est déjà %.2fR au-dessus de l'entrée" % (fmt(last), (last - plan["entry"]) / risk)
    if entry.get("minutes_since", 0) > a.late_minutes:
        return "le signal date de %d minutes" % entry["minutes_since"]
    return None


def late_message(label, entry, plan, reason, alarm_sent):
    trig_utc, lines = header_lines(entry, plan)
    last = (entry.get("last") or {}).get("close")
    out = ["ENTRÉE TROP TARDIVE %s" % label,
           "Raison : %s." % reason,
           "Signal d'origine à %s, heure d'Andorre." % hm_local(trig_utc)] + lines
    if last is not None and last > plan["stop"]:
        out.append("Acheter maintenant à %s risquerait %s par unité (au lieu de %s) : ce n'est plus le même trade."
                   % (fmt(last), fmt(last - plan["stop"]), fmt(plan["risk_per_share"])))
    if not alarm_sent:
        out.append("(Le signal a été détecté trop tard pour l'alarme d'entrée.)")
    out.append("Ne pas courir après le prix. Aucun ordre passé.")
    return "\n".join(out)


def load_state(path, today):
    try:
        with open(path, encoding="utf-8") as fh:
            st = json.load(fh)
    except (OSError, ValueError):
        st = {}
    if st.get("date") != today:
        return {"date": today, "sent": {}}
    if isinstance(st.get("sent"), list):  # older format: one message per symbol
        st["sent"] = {k: ["entry", "late"] for k in st["sent"]}
    return st


def save_state(path, st):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(st, fh, indent=2)


def check_all(a, symbols, now_ny):
    today = now_ny.date().isoformat()
    st = load_state(a.state, today)
    os.makedirs(os.path.dirname(a.state) or ".", exist_ok=True)
    stamp = hm_local(utc_now())
    for pair in symbols:
        label, _, ysym = pair.partition(":")
        ysym = ysym or label
        done = st["sent"].setdefault(label, [])
        if "late" in done or "error" in done:
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
            print("%s %s: entry check failed: %s" % (stamp, label, e), flush=True)
            continue
        print("%s %s: %s" % (stamp, label, entry.get("status")), flush=True)
        if entry.get("status") != "triggered":
            continue
        pcmd = [EXIT, "plan", "--from", entry_path, "--stop", "or-mid", "--target", a.target, "--json"]
        if a.now:
            pcmd += ["--now", a.now]
        try:
            plan = run_json(pcmd)
            if "entry" not in plan:
                raise RuntimeError(plan.get("error") or "no plan")
        except Exception as e:
            send("SIGNAL %s déclenché, mais le plan de sortie a été refusé : %s" % (label, e), a.dry_run)
            done.append("error")
            save_state(a.state, st)
            continue
        reason = late_reason(entry, plan, a)
        if reason:
            send(late_message(label, entry, plan, reason, "entry" in done), a.dry_run)
            done.append("late")
        elif "entry" not in done:
            send(entry_message(label, ysym, entry, plan), a.dry_run)
            done.append("entry")
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
            print("%s (15:55 New York): done for today." % hm_local(utc_now()), flush=True)
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
    r = sub.add_parser("run", help="watch the symbols and send an entry alarm, then a too-late message")
    r.add_argument("--symbols", nargs="*", help="LABEL:YAHOO pairs, default %s" % " ".join(DEFAULT_SYMBOLS))
    r.add_argument("--every", type=int, default=60, help="seconds between checks (default 60)")
    r.add_argument("--target", default="2R", help="trader-exit target (default 2R)")
    r.add_argument("--late-r", type=float, default=0.5,
                   help="too late once the price is this many R above the entry (default 0.5)")
    r.add_argument("--late-minutes", type=int, default=10,
                   help="too late this many minutes after the signal bar closed (default 10)")
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
