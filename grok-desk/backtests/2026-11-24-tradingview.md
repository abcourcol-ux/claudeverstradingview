# Vérification sur TradingView — 24/11/2026

Données : OANDA:XAUUSD 5 min, Strategy Tester de TradingView (cloud).
Période : 04/10 → 24/11/2026 (≈ 7 semaines). Le Deep Backtesting n'est pas inclus dans l'abonnement, donc les 3 mois complets ne sont pas disponibles.
Paramètres : règle validée (RULES.md) — fenêtre 00h30–04h Paris, amplitude ≥ 2 ATR, VWAP moyenne simple, SL 5 $, tiers 1R/2R/3R + BE, arrêt après 1 SL.
Taille : 125 $/R ; commission 1 $ par ordre ; glissement 2 ticks.

| Version du script | Trades | Résultat | PF |
|---|---|---|---|
| VWAP pondéré volume + bug arrêt SL | 74 | +554 $ | 1,12 |
| VWAP pondéré volume + source « Auto » (bug corrigé) | ~50 | +189 $ (≈ +1,5R) | 1,06 |
| **Règle validée (VWAP moyenne, amplitude seule)** | **~41 (123 sorties)** | **+1 340 $ ≈ +10,7R** | **1,62** |

Règle validée : drawdown max 645 $ (≈ 5,2R) ; 43 % des sorties gagnantes ; achats +1 113 $, ventes +227 $.
En 0,03 lot (≈ 15 $/R après commission), cela fait environ +160 $. Sur les mêmes dates, le simulateur Axi donne ≈ +14,7R hors coûts : les résultats concordent.

Corrections apportées au Pine (sauvegardées sur TradingView : stratégie v4.0, indicateur v5.0) :
- l'arrêt après 1 SL est vérifié avant le signal. Avant, des trades continuaient après un SL ;
- le VWAP de séance est par défaut la moyenne simple, comme sur Axi (le mode « Volume » reste disponible) ;
- la source d'activité est par défaut « Amplitude », car le volume de ticks d'OANDA ajoutait de faux signaux.

Limites :
- Le flux de prix compte. Le 23/11 à 23h50 UTC, OANDA a déclenché un SL sur une vente, et l'arrêt après 1 SL a bloqué l'achat de 01h30 qui gagnait sur Axi.
- Ce n'est pas un replay manuel bougie par bougie : aucun PC avec TradingView Desktop n'est connecté.
