# Modifications testées — règle de nuit, 20/08 → 20/11/2026 (lot 0,03, spread déduit, comptage prudent)

Retenue seulement si meilleure que la règle actuelle sur les deux moitiés (≥ +1 $ sur chacune). Script : `variants.py`.

| Variante | Trades | 20/08–04/10 | 05/10–20/11 | Total | PF | Drawdown | Verdict |
|---|---|---|---|---|---|---|---|
| Règle actuelle | 84 | +88 $ | +153 $ | **+241 $** | 1.50 | 74 $ | référence |
| BE après TP2 (au lieu de TP1) | 79 | +64 $ | +105 $ | **+169 $** | 1.30 | 86 $ | ❌ |
| BE 1 $ sous l'entrée | 82 | +80 $ | +130 $ | **+210 $** | 1.44 | 77 $ | ❌ |
| BE 2 $ sous l'entrée | 82 | +112 $ | +136 $ | **+248 $** | 1.52 | 80 $ | ❌ |
| 2 sorties (1R / 2R) | 86 | +124 $ | +129 $ | **+254 $** | 1.51 | 71 $ | ❌ |
| 4 sorties (1R → 4R) | 83 | +93 $ | +156 $ | **+250 $** | 1.54 | 79 $ | ✅ mieux sur les 2 |
| Max 3 trades par nuit | 84 | +88 $ | +153 $ | **+241 $** | 1.50 | 74 $ | ❌ |
| Arrêt après 2 SL dans la nuit | 81 | +99 $ | +169 $ | **+268 $** | 1.60 | 63 $ | ✅ mieux sur les 2 |
| Arrêt après 1 SL dans la nuit | 70 | +111 $ | +182 $ | **+293 $** | 1.82 | 42 $ | ✅ mieux sur les 2 |
| Filtre tendance EMA 50 (5 min) | 80 | +69 $ | +143 $ | **+212 $** | 1.46 | 64 $ | ❌ |
| Filtre tendance EMA 200 (5 min) | 64 | +10 $ | +85 $ | **+94 $** | 1.23 | 58 $ | ❌ |
| Fenêtre 00h00–04h | 89 | +73 $ | +91 $ | **+164 $** | 1.29 | 79 $ | ❌ |
| Fenêtre 00h30–05h | 94 | +29 $ | +216 $ | **+245 $** | 1.44 | 89 $ | ❌ |
| Fenêtre 00h30–03h | 52 | +14 $ | +127 $ | **+142 $** | 1.42 | 67 $ | ❌ |
| Pic d'amplitude ≥ 1,8 ATR | 109 | +313 $ | +106 $ | **+419 $** | 1.73 | 83 $ | ❌ |
| Pic d'amplitude ≥ 2,2 ATR | 61 | +164 $ | +139 $ | **+302 $** | 1.93 | 70 $ | ❌ |
| SL 40 pips | 90 | -8 $ | +39 $ | **+31 $** | 1.06 | 98 $ | ❌ |
| SL 60 pips | 83 | +115 $ | +116 $ | **+231 $** | 1.42 | 131 $ | ❌ |

À retenir : « arrêt après 1 SL dans la nuit » améliore les deux moitiés et divise le drawdown par ~2 (74 → 42 $). « 4 sorties » ne gagne que 9 $ : bruit. Les autres sont écartées. Rien n'est appliqué sans accord.
