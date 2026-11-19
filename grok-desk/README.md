# Grok Desk 🔎📰🎯🛡️😈👑

Six bots Grok (xAI) qui débattent dans un groupe Telegram pendant la séance de New York, avec TradingView comme source de données, d'indicateur et de backtest.

> Par défaut en **paper trading** (journal fictif). L'exécution sur MetaTrader 5 est réservée au compte **démo** sauf autorisation explicite (voir plus bas). Ce n'est pas un conseil financier.

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

Sous Windows, une seule commande depuis le dossier du projet fait tout : installe Node et Python, les dépendances, te pose les questions pour remplir le `.env`, détecte l'ID du groupe Telegram, vérifie MetaTrader 5, lance un essai et peut démarrer le desk à chaque ouverture de session.

```bash
powershell -ExecutionPolicy Bypass -File grok-desk\setup-windows.ps1
```

Installation manuelle :

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

## Sur ton téléphone (app Lovable)

Le desk publie en direct tout ce qui se passe : débat des bots, décisions, positions, P&L, état du marché et du compte. Une app Lovable l'affiche sur ton téléphone et permet de le piloter (pause, reprise, scanner un titre, poser une question au Chef). L'app ne passe aucun ordre elle-même.

Tout est dans `grok-desk/lovable/PROMPT.md` : un seul prompt à coller dans Lovable (schéma de base, fonction `desk-sync`, interface), puis deux lignes à ajouter au `.env` (`DESK_SYNC_URL`, `DESK_SYNC_SECRET`). Seul ton e-mail peut lire les données. Si l'app est injoignable, le desk continue de tourner normalement.

## Exécution sur Axi (MetaTrader 5) — démo d'abord

Par défaut le desk est en papier. Avec `DESK_BROKER=mt5`, chaque GO du Chef devient un **ordre au marché** sur le terminal MetaTrader 5 ouvert sur ton PC, **avec stop et objectif attachés côté serveur** : même si l'app plante, la position reste protégée.

Garde-fous :
- le pont **refuse de démarrer sur un compte réel** tant que `MT5_ALLOW_LIVE=YES_REAL_MONEY` n'est pas dans le `.env` ;
- avec `MT5_LOGIN`, il refuse tout autre compte connecté au terminal ;
- la taille est recalculée sur l'**équité réelle** du compte avant chaque tour ;
- l'ordre est annulé si le prix MT5 s'est éloigné de l'entrée prévue de plus de `RISK_MAX_ENTRY_DISTANCE_PCT` ;
- seules les positions du desk (numéro magique 770077) sont suivies et fermées 5 min avant la clôture ;
- seuls les titres présents dans `MT5_SYMBOLS` sont scannés.

Installation (Windows) :

1. Installe MetaTrader 5 d'Axi, connecte-toi au **compte démo** et coche *Outils → Options → Expert Advisors → Autoriser le trading algorithmique*.
2. Installe Python 3, puis le paquet MetaTrader5 :

```bash
pip install MetaTrader5
```

3. Dans `grok-desk/.env` : `DESK_BROKER=mt5`, `MT5_LOGIN=<ton login démo>`, `MT5_SYMBOLS=NVDA:NVIDIA+,...`
4. Vérifie (aucun ordre passé) :

```bash
npm run desk:mt5 -- check
```

```bash
npm run desk:mt5 -- symbols "*TESLA*"
```

Les symboles d'actions Axi portent souvent le nom de la société (`NVIDIA+`), pas le ticker : la commande `symbols` permet de les trouver.

**Passage en réel** : seulement quand le backtest et plusieurs semaines de démo sont concluants. Il suffit alors de changer de compte dans MT5, de mettre son login dans `MT5_LOGIN` et d'ajouter `MT5_ALLOW_LIVE=YES_REAL_MONEY`. Le Chef annonce dans le groupe sur quel compte (DÉMO/RÉEL) il est connecté.

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
  src/broker-mt5.js    exécution MetaTrader 5 (Axi)
  src/mt5.js           vérification du compte et recherche de symboles
  mt5/mt5_bridge.py    pont Python ↔ terminal MetaTrader 5
  src/dashboard.js     publication vers l'app mobile
  lovable/             prompt Lovable, schéma SQL, fonction Edge desk-sync
  pine/                indicateur et stratégie Pine v6
```

Tests : `node --test tests/grok-desk.test.js`
