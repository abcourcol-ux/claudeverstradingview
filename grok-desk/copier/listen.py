"""Écoute un groupe de signaux Telegram avec TON compte Telegram — MODE PAPIER : aucun ordre n'est passé.
Chaque message (nouveau ou modifié) est lu par parse.py :
  - enregistré dans copier/signals.jsonl (avec l'heure exacte, l'id du message et celui du message auquel il répond) ;
  - transmis à ton bot Grok Desk sous la forme « /sig {json} » pour que le test papier et le bilan l'utilisent.

Installation (une fois, sur ton PC ou un VPS) :
  pip install telethon python-dotenv
  Dans grok-desk/.env, ajoute :
    TG_API_ID=...            (my.telegram.org → API development tools)
    TG_API_HASH=...
    COPIER_CHATS=Nom exact du groupe        (plusieurs : séparés par « | »)
    COPIER_FORWARD_TO=@nom_de_ton_bot       (le bot Grok Desk)
Lancer :  python3 grok-desk/copier/listen.py        (1re fois : Telegram t'envoie un code de connexion)
Lister tes groupes pour trouver le nom exact :  python3 grok-desk/copier/listen.py --list
"""
import asyncio, json, os, sys
from datetime import timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from parse import parse  # noqa: E402

try:
    from dotenv import load_dotenv
    load_dotenv(HERE.parent / '.env')
except ImportError:
    pass
from telethon import TelegramClient, events  # noqa: E402

API_ID, API_HASH = os.environ.get('TG_API_ID'), os.environ.get('TG_API_HASH')
CHATS = [c.strip() for c in os.environ.get('COPIER_CHATS', '').split('|') if c.strip()]
FORWARD = os.environ.get('COPIER_FORWARD_TO', '').strip()
LOG = HERE / 'signals.jsonl'
if not API_ID or not API_HASH:
    sys.exit('TG_API_ID / TG_API_HASH manquants dans grok-desk/.env (voir en tête de ce fichier)')

client = TelegramClient(str(HERE / 'copier.session'), int(API_ID), API_HASH)


async def handle(ev, edited):
    m = ev.message
    p = parse(m.message or '')
    if p['kind'] == 'other':
        return
    rec = {'at': m.date.astimezone(timezone.utc).isoformat(), 'msg': m.id, 'reply_to': m.reply_to_msg_id,
           'edited': edited, 'chat': ev.chat_id, **{k: v for k, v in p.items() if k != 'text' or p['kind'] == 'note'}}
    with LOG.open('a', encoding='utf-8') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    print(('✏️ ' if edited else '📩 ') + json.dumps(rec, ensure_ascii=False))
    if FORWARD:
        await client.send_message(FORWARD, '/sig ' + json.dumps(rec, ensure_ascii=False))


async def main():
    await client.start()
    if '--list' in sys.argv:
        async for d in client.iter_dialogs():
            if d.is_group or d.is_channel:
                print(f'{d.id}\t{d.name}')
        return
    if not CHATS:
        sys.exit('COPIER_CHATS vide : mets le nom exact du groupe (python3 listen.py --list pour le trouver)')
    wanted = []
    async for d in client.iter_dialogs():
        if d.name in CHATS or str(d.id) in CHATS:
            wanted.append(d.id)
    if not wanted:
        sys.exit(f'Groupe introuvable : {CHATS} (python3 listen.py --list)')
    client.add_event_handler(lambda e: handle(e, False), events.NewMessage(chats=wanted))
    client.add_event_handler(lambda e: handle(e, True), events.MessageEdited(chats=wanted))
    print(f'Écoute de {len(wanted)} groupe(s) en mode papier — Ctrl+C pour arrêter')
    await client.run_until_disconnected()

asyncio.run(main())
