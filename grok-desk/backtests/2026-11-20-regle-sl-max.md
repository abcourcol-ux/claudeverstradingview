# Backtest 20/11/2026 — règle SL = max(50 pips ; 1,5 × ATR 5 min), un trade à la fois

Données : bougies 5 min XAUUSD Axi (démo), 19/11 23h00 → 20/11 21h00 UTC. Le quota TradingView étant épuisé,
la stratégie « Grok Desk Strategy » v3.0 a été rejouée par `sim_day.py` (mêmes règles : pic d'amplitude ≥ 2 ATR,
côté VWAP, refus si > 3 ATR du VWAP, entrée à l'ouverture suivante, sortie par tiers 1R/2R/3R, BE après TP1).

| Fenêtre | Signal | Sens | Entrée | SL | Résultat |
|---|---|---|---|---|---|
| Nuit (00h30–04h Paris) | 01h00 UTC | Vente | 3593,44 | 3608,92 (154 pips, 1,5 ATR) | SL à 01h10 : −1R (−25 $) |
| NY (15h30–22h Paris) | aucun | — | — | — | les pics d'amplitude étaient soit dans le mauvais sens par rapport au VWAP, soit trop étendus |

Total stratégie automatique : **−1R (−25 $), 1 trade**.

À comparer : les 6 cartes Telegram du jour, relues avec la même règle de SL, donnent +3R. L'écart vient de ce que
ces cartes venaient de l'analyse du desk, qui est plus souple que le signal mécanique de l'indicateur.
Une journée ne prouve rien : il faut le backtest TradingView sept.–nov. dès que le quota revient.
