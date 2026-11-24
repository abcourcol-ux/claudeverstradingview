# EA « GrokDeskNuit » — MetaTrader 5

Il applique la règle de `RULES.md` sans IA : fenêtre 00h30–04h Paris, signal d'amplitude ≥ 2 ATR du bon côté du VWAP de séance, SL 50 pips, sortie en tiers 1R/2R/3R, BE après TP1, arrêt de la nuit après 1 SL. Tout est fermé à 03h55.

## Installation (5 min)
1. Dans MT5 : **Fichier → Ouvrir le dossier des données → MQL5 → Experts**. Copie-y `GrokDeskNuit.mq5`.
2. Ouvre-le avec **MetaEditor** (F4), puis clique sur **Compiler** (F7). Il ne doit y avoir aucune erreur (sinon envoie-moi le message).
3. Dans MT5, clique sur le bouton **Algo Trading** pour qu'il soit vert.
4. Ouvre un graphique **XAUUSD** (n'importe quelle unité de temps, l'EA lit lui-même le M5) et glisse l'EA dessus.
5. Onglet **Commun** : coche « Autoriser le trading algorithmique ». Onglet **Paramètres** : voir ci-dessous.
6. Le PC (ou un VPS) doit rester allumé et MT5 ouvert toute la nuit.

## Paramètres par compte
| Compte | Mode de calcul du lot | Valeur | Plancher d'equity | Risque ÷ 2 si DD ≥ |
|---|---|---|---|---|
| Démo Axi (test, 1 à 2 semaines) | Lot fixe | 0,03 | 0 | 0 |
| Prop 180 000 $ (limite fixe 10 000 $) | Risque en % | 0,5 % (≈ 1,80 lot) | 170 000 | 5 000 |

« Plancher d'equity » : l'EA ne prend pas un trade si un SL faisait passer l'equity sous ce montant.
Fuseau du serveur : laisser « New York + 7 h » (Axi et la plupart des brokers MT5). Au démarrage, l'onglet **Experts** affiche « heure de Paris maintenant HH:MM ». Si ce n'est pas la bonne heure, choisis le décalage manuel.

## Vérifications avant le compte réel
- **Testeur de stratégie** (Ctrl+R), XAUUSD, M5, « Chaque tick basé sur des ticks réels », période 20/05–20/11/2026 : le résultat doit être proche de `backtests/2026-11-24-six-mois.md` (141 trades, ≈ +41R).
- **Démo Axi** 1 à 2 semaines : chaque trade de l'EA doit correspondre aux cartes Telegram du test papier.
- Ensuite seulement sur le compte prop. Avant, vérifie aussi que le symbole s'appelle bien XAUUSD (sinon, mets l'EA sur le bon symbole, par ex. XAUUSD.r).

Notifications : avec l'app MT5 mobile, renseigne ton MetaQuotes ID dans **Outils → Options → Notifications** pour recevoir chaque entrée, TP et sortie.
