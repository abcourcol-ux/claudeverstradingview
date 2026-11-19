# Grok Desk 🔎📰🎯🛡️😈👑

Six bots Grok (xAI) qui débattent dans un groupe Telegram pendant la séance de New York, avec TradingView comme source de données, d'indicateur et de backtest.

> **Paper trading uniquement.** L'app ne passe aucun ordre réel : elle tient un journal de positions fictives. Ce n'est pas un conseil financier.

## Comment se passe un tour (toutes les 15 min en séance)

| Bot | Rôle | Ce qui est calculé en code / ce que fait Grok |
|---|---|---|
| 🔎 **Scanner** | repère les volumes inhabituels | volume relatif à la même heure vs les 4 jours d'avant, pic de la bougie 5 min, VWAP, ATR, plus la lecture de l'indicateur TradingView → Grok choisit le titre et le présente |
| 📰 **News** | lit l'actu | titres récents (Yahoo Finance RSS) → Grok dit s'il y a un catalyseur |
| 🎯 **Planificateur** | fixe entrée / stop / objectif | Grok propose un plan JSON ; il a **une révision** si le Risque refuse |
| 🛡️ **Risque** | refuse les plans trop risqués | **règles dures en code** (R:R, stop max, stop dans le bruit, distance d'entrée, taille, positions ouvertes, quota/jour, perte du jour, horaires) + avis de Grok. Une violation = refus, sans appel |
| 😈 **Sceptique** | attaque chaque idée | Grok cherche le meilleur argument contre le plan et note sa gravité |
| 👑 **Chef** | tranche | GO / NO_GO / WATCH. Un verrou en code l'empêche de dire GO si le Risque a refusé |

En cas de GO : carte d'ordre papier dans le groupe (et capture du graphique TradingView si la source est `tradingview`). Ensuite l'app suit la position chaque minute (exécution, stop, objectif, expiration) et coupe tout 5 min avant la clôture. Cloche d'ouverture et bilan du jour automatiques. Calendrier NYSE 2026-2027 (jours fériés et demi-séances) inclus.

## Installation

```bash
npm install
```

```bash
cp grok-desk/.env.example grok-desk/.env
```

1. **xAI** : crée une clé sur console.x.ai → `XAI_API_KEY`.
2. **Telegram** : avec @BotFather, crée 6 bots (Scanner, News, Planificateur, Risque, Sceptique, Chef) et mets chaque token dans le `.env`. Ajoute les 6 bots au groupe. Pour récupérer `TELEGRAM_CHAT_ID`, écris dans le groupe puis ouvre `https://api.telegram.org/bot<TOKEN_CHEF>/getUpdates`. Un seul bot (`TELEGRAM_TOKEN`) marche aussi.
3. Essai sans rien configurer (marché et Grok simulés, sortie console) :

```bash
npm run desk:demo
```

## Lancer le desk

```bash
npm run desk
```

Options : `--source tradingview` · `--dry-run` (console au lieu de Telegram) · `--once --focus NVDA` (un tour immédiat sur un titre, même marché fermé, pour tester).

Commandes dans le groupe : `/status`, `/scan [TICKER]`, `/positions`, `/pause`, `/resume`, `/ask ta question` (réponse du Chef).

## TradingView

Lance TradingView Desktop avec CDP (voir `SETUP_GUIDE.md` / `scripts/launch_tv_debug_*`), puis :

### 1. Source de données
`DESK_SOURCE=tradingview` : le desk lit les bougies 5 min depuis ton graphique (il change le symbole tour à tour, donc mieux vaut un onglet/layout dédié). Les news restent sur Yahoo, TradingView ne les expose pas via CDP.

### 2. Indicateur « Grok Desk » (`pine/grok_desk_indicator.pine`)
Même logique que les bots : volume relatif à la même heure + pic de volume (Scanner), entrée/stop ATR/objectif R:R (Planificateur), stop max, R:R min, fenêtres horaires, quota (Risque), refus si le prix est trop loin du VWAP (Sceptique). Il dessine VWAP, signaux, lignes entrée/stop/objectif, et un tableau que le Scanner lit pendant le débat. Il fournit aussi des alertes (`alertcondition` + `alert()` JSON pour webhook).

```bash
npm run desk:tv -- indicator
```

### 3. Backtest (`pine/grok_desk_strategy.pine`)
La stratégie applique les mêmes règles dans le Strategy Tester : taille = risque % / distance du stop, sortie avant clôture, coupe-circuit de perte journalière, commissions et slippage.

```bash
npm run desk:tv -- backtest NVDA AMD TSLA --telegram
```

Ça pousse la stratégie dans l'éditeur Pine (le contenu précédent de l'éditeur est sauvegardé dans `grok-desk/data/pine-backup/`), la fait tourner sur chaque symbole et écrit un rapport dans `grok-desk/data/backtests/`. Avec `--telegram`, le Chef poste le bilan, puis le Sceptique et le Risque critiquent sa robustesse.

**Une seule config pour tout** : les valeurs du `.env` (seuils du Scanner, règles du Risque) sont injectées dans les deux scripts Pine (lignes marquées `// @desk`), donc les bots, l'indicateur et le backtest appliquent les mêmes règles. Pour copier-coller les scripts à la main :

```bash
npm run desk:tv -- export
```

Limites : la profondeur d'historique en 5 min dépend de ton abonnement TradingView (Deep Backtesting sur les plans payants). News et Chef ne sont pas dans le backtest, qui mesure donc l'avantage « brut » des règles Scanner/Planificateur/Risque/Sceptique.

## Fichiers

```
grok-desk/
  src/index.js         boucle principale, horaires, suivi des positions, commandes Telegram
  src/debate.js        un tour de débat entre les six bots
  src/personas.js      les prompts système des six personnages
  src/risk.js          règles dures du Gestionnaire de risque
  src/scanner.js       volume relatif, pics, VWAP, ATR
  src/providers.js     Yahoo, TradingView (CDP) et marché simulé
  src/grok.js          client xAI + faux Grok pour les tests
  src/telegram.js      envoi multi-bots, photos, écoute des commandes
  src/journal.js       journal de paper trading
  src/market-hours.js  calendrier NYSE
  src/tradingview.js   export / indicateur / backtest
  pine/                indicateur et stratégie Pine v6
```

Tests : `node --test tests/grok-desk.test.js`
