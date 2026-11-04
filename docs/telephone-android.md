# Alertes Telegram sur un téléphone Android (Termux)

Tout se fait sur le téléphone. Copiez chaque commande, appui long dans Termux > Paste, puis Entrée.
Ne montrez jamais le token sur une capture d'écran.

## 0. Repartir de zéro (si une installation précédente existe)

```bash
rm -rf ~/claudeverstradingview-claude-nice-dirac-po90ha
sed -i '/TELEGRAM_/d' ~/.bashrc
```

## 1. Installer Python

```bash
pkg update -y && pkg install -y python unzip
termux-setup-storage
```

## 2. Télécharger le projet

Dans Chrome (connecté à GitHub) : branche `claude/nice-dirac-po90ha` du dépôt, bouton vert **Code > Download ZIP**.
Supprimez d'abord l'ancien ZIP dans Téléchargements pour éviter un nom en « (1) ».

```bash
cd ~ && unzip -o -q ~/storage/downloads/claudeverstradingview-claude-nice-dirac-po90ha.zip
```

## 3. Enregistrer le bot (remplacez les valeurs, gardez les guillemets)

```bash
echo 'export TELEGRAM_BOT_TOKEN="votre-token"' >> ~/.bashrc
echo 'export TELEGRAM_CHAT_ID="votre-numero"' >> ~/.bashrc
source ~/.bashrc
clear
```

## 4. Tester puis lancer

```bash
cd ~/claudeverstradingview-claude-nice-dirac-po90ha
python scripts/trader_signal_telegram.py test
termux-wake-lock
python scripts/trader_signal_telegram.py run
```

## 5. Réglage Android

Paramètres > Applications > Termux > Batterie > **Non restreinte**. Laissez Termux ouvert en arrière-plan
et le téléphone en charge la nuit. Arrêtez le script sur le PC pour éviter les doublons.

## Les jours suivants

```bash
termux-wake-lock
cd ~/claudeverstradingview-claude-nice-dirac-po90ha && python scripts/trader_signal_telegram.py run
```

Fenêtres (heure d'Andorre) : XAUUSD 00:30-02:30 et 14:00-22:00, BTCUSD 14:00-22:00, du lundi au vendredi.
Aucun ordre n'est jamais passé. Ce n'est pas un conseil financier.
