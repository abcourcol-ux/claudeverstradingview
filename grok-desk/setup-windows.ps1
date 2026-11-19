# Grok Desk - installation Windows en une commande.
# Depuis le dossier du projet :
#   powershell -ExecutionPolicy Bypass -File grok-desk\setup-windows.ps1
#
# Ce script : installe Node.js et Python si besoin (winget), installe les dependances,
# remplit grok-desk\.env en te posant les questions (Entree = garder la valeur actuelle),
# verifie MetaTrader 5, lance un essai, et peut demarrer le desk automatiquement a l'ouverture de session.
# Il ne passe AUCUN ordre.

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$envFile = Join-Path $root 'grok-desk\.env'

function Title($t) { Write-Host ''; Write-Host "== $t ==" -ForegroundColor Cyan }
function Ok($t) { Write-Host "  OK  $t" -ForegroundColor Green }
function Warn($t) { Write-Host "  !!  $t" -ForegroundColor Yellow }

function Refresh-Path {
  $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
}

function Ensure-Tool($cmd, $wingetId, $label) {
  if (Get-Command $cmd -ErrorAction SilentlyContinue) { Ok "$label present"; return }
  Write-Host "  Installation de $label..."
  winget install -e --id $wingetId --accept-source-agreements --accept-package-agreements | Out-Host
  Refresh-Path
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { throw "$label introuvable apres installation : ferme et rouvre PowerShell puis relance le script." }
  Ok "$label installe"
}

# ---------- .env : lecture / ecriture ----------
function Read-EnvLines { if (Test-Path $envFile) { return [System.Collections.ArrayList]@(Get-Content $envFile) } else { return [System.Collections.ArrayList]@() } }

function Get-EnvValue($name) {
  foreach ($l in (Read-EnvLines)) { if ($l -match "^$name=(.*)$") { return $Matches[1] } }
  return ''
}

function Set-EnvValue($name, $value) {
  $lines = Read-EnvLines
  $found = $false
  for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match "^#?\s*$name=") { $lines[$i] = "$name=$value"; $found = $true; break }
  }
  if (-not $found) { [void]$lines.Add("$name=$value") }
  [System.IO.File]::WriteAllLines($envFile, [string[]]$lines, (New-Object System.Text.UTF8Encoding($false)))
}

function Ask($name, $question, [switch]$Secret, $default = '') {
  $cur = Get-EnvValue $name
  if (-not $cur) { $cur = $default }
  $shown = ''
  if ($cur) { if ($Secret) { $shown = ' [deja renseigne]' } else { $shown = " [$cur]" } }
  if ($Secret) {
    $s = Read-Host -AsSecureString "  $question$shown"
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)
    $v = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
  } else {
    $v = Read-Host "  $question$shown"
  }
  if (-not $v) { $v = $cur }
  Set-EnvValue $name $v
  return $v
}

function New-Secret {
  $bytes = New-Object byte[] 32
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  return ([BitConverter]::ToString($bytes) -replace '-', '').ToLower()
}

# ---------- 1. Outils ----------
Title '1/6 Outils'
Ensure-Tool node 'OpenJS.NodeJS.LTS' 'Node.js'
$py = $null
if (Get-Command py -ErrorAction SilentlyContinue) { $py = 'py' }
else {
  Ensure-Tool py 'Python.Python.3.12' 'Python 3.12'
  $py = 'py'
}
$pyExe = (& $py -3 -c "import sys; print(sys.executable)").Trim()
$pyBits = (& $py -3 -c "import struct; print(struct.calcsize('P') * 8)").Trim()
if ($pyBits -ne '64') { Warn "Python $pyBits bits : MetaTrader5 demande Python 64 bits" }
Ok "Python : $pyExe"

# ---------- 2. Dependances ----------
Title '2/6 Dependances'
npm install --no-fund --no-audit | Out-Host
& $py -3 -m pip install --upgrade --quiet MetaTrader5
Ok 'npm + MetaTrader5'

# ---------- 3. Configuration ----------
Title '3/6 Configuration (Entree = garder la valeur actuelle)'
if (-not (Test-Path $envFile)) { Copy-Item (Join-Path $root 'grok-desk\.env.example') $envFile; Ok '.env cree' }
Set-EnvValue 'MT5_PYTHON' $pyExe

Write-Host ''
Write-Host '  xAI : cle sur https://console.x.ai' -ForegroundColor Gray
[void](Ask 'XAI_API_KEY' 'Cle API xAI' -Secret)
[void](Ask 'GROK_MODEL' 'Modele Grok' -default 'grok-4')

Write-Host ''
Write-Host '  Telegram : bots crees avec @BotFather, tous ajoutes au groupe' -ForegroundColor Gray
$six = Read-Host '  Un bot par personnage (6 tokens) ? o/N'
if ($six -match '^[oOyY]') {
  foreach ($b in @('SCANNER', 'NEWS', 'PLANNER', 'RISK', 'SKEPTIC', 'CHEF')) { [void](Ask "TELEGRAM_TOKEN_$b" "Token du bot $b" -Secret) }
  $chefToken = Get-EnvValue 'TELEGRAM_TOKEN_CHEF'
} else {
  [void](Ask 'TELEGRAM_TOKEN' 'Token du bot unique' -Secret)
  $chefToken = Get-EnvValue 'TELEGRAM_TOKEN'
}
if (-not (Get-EnvValue 'TELEGRAM_CHAT_ID') -and $chefToken) {
  Read-Host '  Ecris un message (par ex. /status) dans le groupe Telegram, puis appuie sur Entree' | Out-Null
  try {
    $u = Invoke-RestMethod "https://api.telegram.org/bot$chefToken/getUpdates"
    $chat = $u.result | ForEach-Object { $_.message.chat } | Where-Object { $_.type -like '*group*' } | Select-Object -Last 1
    if ($chat) { Set-EnvValue 'TELEGRAM_CHAT_ID' $chat.id; Ok "Groupe detecte : $($chat.title) ($($chat.id))" }
    else { Warn 'Groupe non detecte (le bot est-il bien dans le groupe ?)' }
  } catch { Warn "Telegram : $($_.Exception.Message)" }
}
[void](Ask 'TELEGRAM_CHAT_ID' 'ID du groupe Telegram (negatif)')

Write-Host ''
Write-Host '  MetaTrader 5 Axi : le terminal doit etre ouvert, connecte au compte DEMO,' -ForegroundColor Gray
Write-Host '  avec Outils > Options > Expert Advisors > Autoriser le trading algorithmique.' -ForegroundColor Gray
[void](Ask 'DESK_WATCHLIST' 'Que trader ? (ex. XAUUSD, ou NVDA,TSLA)' -default 'XAUUSD')
$login = Ask 'MT5_LOGIN' 'Login du compte DEMO MT5 (vide = rester en papier)'
if ($login) {
  Set-EnvValue 'DESK_BROKER' 'mt5'
  Set-EnvValue 'DESK_SOURCE' 'mt5'
  [void](Ask 'MT5_SYMBOLS' 'Correspondances ticker:symbole Axi' -default 'XAUUSD:XAUUSD')
  if (Get-EnvValue 'MT5_ALLOW_LIVE') { Warn 'MT5_ALLOW_LIVE est defini : le compte REEL serait autorise. Retire cette ligne pour rester en demo.' }
} else { Set-EnvValue 'DESK_BROKER' 'paper' }

Write-Host ''
Write-Host '  Telephone (app Lovable, voir grok-desk\lovable\PROMPT.md) - laisser vide pour plus tard' -ForegroundColor Gray
$syncUrl = Ask 'DESK_SYNC_URL' 'URL de la fonction desk-sync'
if ($syncUrl -and -not (Get-EnvValue 'DESK_SYNC_SECRET')) {
  $sec = New-Secret
  Set-EnvValue 'DESK_SYNC_SECRET' $sec
  Write-Host "  Secret genere. Dans Lovable > Cloud > Secrets, cree DESK_SYNC_SECRET = $sec" -ForegroundColor Yellow
  Read-Host '  Appuie sur Entree une fois fait' | Out-Null
}

# ---------- 4. Verification MT5 ----------
Title '4/6 Verification MetaTrader 5'
if ((Get-EnvValue 'DESK_BROKER') -eq 'mt5') {
  node grok-desk/src/mt5.js check
  if ($LASTEXITCODE -ne 0) { Warn 'Verification MT5 echouee : corrige puis relance ce script (tes reponses sont gardees).' }
  Write-Host '  Pour trouver un symbole : npm run desk:mt5 -- symbols "*TESLA*"' -ForegroundColor Gray
} else { Ok 'Mode papier : pas de MT5' }

# ---------- 5. Essai ----------
Title '5/6 Essai (marche et Grok simules)'
node grok-desk/src/index.js --mock --once --dry-run
Ok 'Demo terminee (si DESK_SYNC_URL est rempli, regarde ton telephone)'

# ---------- 6. Demarrage automatique ----------
Title '6/6 Demarrage automatique'
$launcher = Join-Path $root 'grok-desk\start-desk.cmd'
$auto = Read-Host '  Lancer le desk automatiquement a chaque ouverture de session Windows ? o/N'
if ($auto -match '^[oOyY]') {
  $action = New-ScheduledTaskAction -Execute $launcher -WorkingDirectory $root
  $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
  $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5)
  Register-ScheduledTask -TaskName 'Grok Desk' -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
  Ok "Tache 'Grok Desk' creee (journal : grok-desk\data\desk.log). Supprimer : Unregister-ScheduledTask 'Grok Desk'"
}

Write-Host ''
Write-Host 'Termine. Lancer le desk maintenant :  npm run desk' -ForegroundColor Green
Write-Host 'Il debat de 15h30 a 22h (heure de Paris) les jours de bourse ; le PC doit rester allume.' -ForegroundColor Green
