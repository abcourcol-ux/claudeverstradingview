# Règles du desk — XAUUSD (à jour du 20/11/2026)

| Règle | Valeur |
|---|---|
| Stop (SL) | **max(50 pips ; 1,5 × ATR 5 min)** — or : 1 pip = 0,10 $, donc 50 pips = 5 $ |
| Risque par trade | 25 $ fixe : la taille s'adapte à la distance du SL |
| TP1 / TP2 / TP final | 1R / 2R / 3R (ou cible de structure si plus loin que 2R), sortie par tiers |
| BE | SL remonté au prix d'entrée dès TP1 touché |
| Positions simultanées | **1 seule : jamais deux trades en même temps** |
| Fenêtre | Session de New York (9h30–16h NY) ; test de nuit 00h30–04h Paris |

Où la règle est appliquée :
- Cartes Telegram : `buildSignal({ slMinPips: 50, slAtrMult: 1.5, ... })` (`src/signal.js`)
- Desk (Gestionnaire de risque) : `minStopPips`, `stopAtrMult`, `maxOpenPositions: 1` (`src/config.js`, `src/risk.js`)
- TradingView : indicateur « Grok Desk » v4.0 (`SL minimum en $` = 5) et « Grok Desk Strategy » v3.0 (`pyramiding = 0`, pas de nouvelle entrée tant qu'une position est ouverte)

À valider : la relecture du 20/11 donne +3R avec ces règles, mais deux trades n'ont survécu au SL que d'environ 1 $.
Il faut un backtest calibré sur sept.–oct. puis vérifié sur novembre avant de passer en réel.

## Banc d'essai (toujours les mêmes trades)
Toute modification de la stratégie est d'abord rejouée sur les trades de référence :
`python3 grok-desk/backtests/banc/bench.py` (liste dans `backtests/banc/trades-reference.json`, enrichie chaque jour
avec les nouvelles cartes et leurs bougies M5). Une variante n'est retenue que si elle fait mieux sur le banc **et**
sur le backtest TradingView de plusieurs semaines.
