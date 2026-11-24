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
| Arrêt de la nuit | **après le 1er SL, plus aucune entrée jusqu'à la nuit suivante** (ajouté le 22/11 : 3 mois +293 $ au lieu de +241 $ en 0,03 lot, drawdown 42 $ au lieu de 74 $, meilleur sur les deux moitiés) |

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

## Compte UFunded Captain 180 000 $ (Limited Edition, drawdown max fixe 10 000 $, partage 80 %)
| Paramètre EA (`mt5/GrokDeskNuit.mq5`) | Valeur |
|---|---|
| Mode de calcul du lot | Risque en % : **0,5 %** (≈ 1,80 lot, 1 SL ≈ 900 $) |
| Plancher d'equity | **170 000** (aucun trade si un SL passerait dessous) |
| Risque ÷ 2 si equity < plus haut − X | **5 000** |
| Arrêt après N SL | 1 · trades max par nuit 5 |

Backtest 6 mois (20/05–20/11, 141 trades) : ≈ +33 300 $ avant partage, ≈ 26 600 $ pour le trader (80 %) ; drawdown max 2 831 $.
Simulation 1 an : risque de toucher 170 000 $ ≈ 0,7 %. Pour raisonner en réel, prendre la moitié du backtest (≈ 2 200 $/mois pour le trader).
Mise en route : EA 2 à 4 semaines sur la démo Axi (0,03 lot), trades identiques au test papier → ensuite seulement sur le compte 180k.
