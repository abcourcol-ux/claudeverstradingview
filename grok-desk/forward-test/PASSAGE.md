# Passage du test papier de nuit (procédure suivie à chaque réveil)

Aucun ordre Axi : lecture seule. Depuis la racine du repo.

1. Écouteur Telegram : `pgrep -f "tg-inbox.js --watch"` ; sinon `(NODE_USE_ENV_PROXY=1 NODE_NO_WARNINGS=1 nohup node grok-desk/src/tg-inbox.js --watch 240 > grok-desk/data/tg-watch.log 2>&1 &)`.
2. Bougies M5 : `get_mt5_candles` (compte us50-demo_10072219, XAUUSD, M5) depuis J-12 00:00Z jusqu'à maintenant (la réponse est sauvegardée en fichier), puis
   `python3 -I grok-desk/forward-test/ingest.py < fichier` et `NODE_USE_ENV_PROXY=1 python3 grok-desk/forward-test/night_pass.py`.
3. Pré-alerte (seulement entre 00h45 et 03h15 Paris, sans position ouverte) : `get_mt5_candles` M1 sur les 24 dernières heures (fichier), puis
   `python3 -I grok-desk/forward-test/prealert.py fichier`.
4. `git add grok-desk/forward-test && git commit && git push` (jamais grok-desk/.env).
5. Prochain passage (send_later, même consigne « suivre grok-desk/forward-test/PASSAGE.md ») :
   - position ouverte → dans 2 min ;
   - entre 00h40 et 03h15 Paris sans position → au prochain de ces instants : clôture de bougie + 1 min (xx:x1, xx:x6) ou + 3 min (xx:x3, xx:x8) ;
   - avant 00h40 → dans 10 min ;
   - SL touché (nuit arrêtée) ou après 03h15 sans position → bilan à 04h06 Paris.
6. Bilan (04h06 Paris) : Telegram `node grok-desk/src/notify.js --text "..."` avec les trades de la nuit et le cumul du test papier,
   ligne de bilan dans `grok-desk/forward-test/AAAA-MM-JJ-nuit-papier.md`, commit + push. Ne pas reprogrammer.
Marché fermé (pas de nouvelle bougie depuis plus d'une heure) : ne rien envoyer, arrêter la chaîne.
