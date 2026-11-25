# Copieur de signaux Telegram — phase papier

Lit un groupe de signaux avec ton compte Telegram et note chaque signal, **sans passer d'ordre**. On mesure d'abord ses résultats réels pendant 2 à 4 semaines ; l'exécution sur les comptes ne sera branchée qu'ensuite.

| Fichier | Rôle |
|---|---|
| `parse.py` | lit un message : pré-alerte, ouverture (sens, symbole, entrée, SL, TP1–3), « SL à BE », clôture, note |
| `listen.py` | tourne sur ton PC ou un VPS : écoute le groupe, enregistre `signals.jsonl`, relaie chaque signal à ton bot (`/sig …`) |
| `evaluate.py` | résultat papier des signaux sur les bougies M5 Axi (sorties par tiers, BE au message, comptage prudent) |

## Mise en route (sur ton PC)
1. Va sur my.telegram.org → **API development tools** → crée une appli → note `api_id` et `api_hash` (ne les envoie à personne).
2. Dans `grok-desk/.env`, ajoute :
   ```
   TG_API_ID=...
   TG_API_HASH=...
   COPIER_CHATS=Nom exact du groupe
   COPIER_FORWARD_TO=@nom_de_ton_bot
   ```
3. Installe et lance :
   ```
   pip install telethon python-dotenv
   python3 grok-desk/copier/listen.py --list     (affiche tes groupes, pour copier le nom exact)
   python3 grok-desk/copier/listen.py
   ```
   La 1re fois, Telegram t'envoie un code : tape-le dans le terminal. Une session est enregistrée dans `copier/copier.session` (jamais committée : c'est un accès à ton compte).

Les signaux relayés à ton bot sont récupérés par `src/tg-inbox.js` dans `copier/inbox.jsonl`, puis notés avec `evaluate.py`.
