# Règles du desk — XAUUSD (à jour du 20/11/2026, validées sur sept.–nov.)

| Règle | Valeur |
|---|---|
| Fenêtre | **00h30–04h Paris uniquement** (la séance de New York perd sur les backtests) |
| Signal | bougie 5 min d'amplitude ≥ 2 × ATR14, clôture du côté du VWAP de séance, refus si > 3 ATR du VWAP |
| Entrée | ouverture de la bougie suivante (fourchette ± 0,25 ATR sur la carte) |
| Stop (SL) | **50 pips fixe** (5 $ sur l'or) |
| TP1 / TP2 / TP final | 1R / 2R / 3R, sortie par tiers ; tout ce qui reste est clôturé à 04h |
| BE | SL remonté au prix d'entrée dès TP1 touché |
| Risque | 25 $ par trade : taille = 25 $ / 5 $ = 5 onces (0,05 lot) |
| Positions simultanées | 1 seule, jamais deux trades en même temps ; 5 trades max par nuit |

Résultats (bougies Axi M5, comptage prudent, spread non compté ≈ −0,03R/trade) :
septembre (hors échantillon) +12,1R sur 42 trades · 20/10–20/11 +5,3R sur 32 trades · total +17,4R, PF 1,65, drawdown max 4R.
Détail : `backtests/2026-09-validation-nuit.md`. Le SL en ATR et le filtre 2 ATR ont été écartés (sur-optimisés).

Où la règle est appliquée :
- Test papier de nuit : `forward-test/night_pass.py` (cartes Telegram, journal `forward-test/AAAA-MM-JJ-nuit-papier.md`)
- Desk (Gestionnaire de risque) : or = SL ≥ 50 pips, une position à la fois (`src/config.js`, `src/risk.js`)
- Pine : « Grok Desk » / « Grok Desk Strategy » — SL 5 $, Stop ATR 0, fenêtre 1830-2200 heure de NY (= 00h30–04h Paris)

Étapes suivantes : forward test papier plusieurs nuits → démo Axi (chaque ordre confirmé par l'utilisateur) → réel seulement si les deux sont concluants.

## Banc d'essai (toujours les mêmes données)
Toute modification est rejouée sur les mêmes données avant d'être adoptée :
`python3 grok-desk/backtests/month.py --data data_sep --window nuit --prudent --pips 50 --k 0` (septembre) et `--data data` (20/10–20/11),
ainsi que `backtests/banc/bench.py` (cartes du 20/11). Une variante n'est retenue que si elle gagne sur les **deux** périodes.
