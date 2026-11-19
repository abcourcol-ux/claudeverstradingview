# Prompt Lovable — Grok Desk mobile

Copie tout ce qui est entre les deux lignes `=====` dans un nouveau projet Lovable (avec Lovable Cloud activé).
Avant de coller, remplace `TON_EMAIL@exemple.com` (2 fois) par l'e-mail avec lequel tu te connecteras.

=====
Construis une web app mobile-first en français, installable sur l'écran d'accueil (PWA, icône, plein écran, thème sombre par défaut),
appelée « Grok Desk ». C'est le tableau de bord d'un desk de trading automatisé : six bots IA (Scanner, News, Planificateur,
Risque, Sceptique, Chef) débattent des actions US pendant la séance de New York. Un programme sur mon PC écrit les données dans
la base ; l'app ne fait que LIRE ces données en temps réel et ENVOYER des commandes. Elle ne passe jamais d'ordre elle-même.

## Backend (Lovable Cloud)
1. Exécute exactement ce SQL (migration) :

```sql
-- Grok Desk — base du tableau de bord mobile (Supabase / Lovable Cloud).
-- Remplace TON_EMAIL@exemple.com par l'e-mail du compte avec lequel tu te connecteras à l'app :
-- c'est le seul compte autorisé à lire les données et à envoyer des commandes.

create table if not exists public.desk_messages (
  id bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  bot text not null check (bot in ('scanner','news','planner','risk','skeptic','chef')),
  text text not null
);

create table if not exists public.desk_rounds (
  id bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  ny_time text,
  focus text,
  decision text,
  quiet boolean default false,
  plan jsonb,
  risk jsonb,
  error text
);

create table if not exists public.desk_positions (
  id text primary key,
  ticker text not null,
  direction text not null,
  status text not null,
  shares numeric,
  entry numeric,
  stop numeric,
  target numeric,
  exit numeric,
  pnl numeric,
  reason text,
  broker text,
  ticket bigint,
  created_at timestamptz,
  filled_at timestamptz,
  updated_at timestamptz not null default now()
);

create table if not exists public.desk_status (
  id int primary key default 1 check (id = 1),
  data jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create table if not exists public.desk_commands (
  id bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  command text not null check (command in ('pause','resume','scan','status','positions','ask')),
  arg text,
  status text not null default 'pending' check (status in ('pending','taken','done')),
  result text,
  done_at timestamptz
);

create index if not exists desk_messages_created_idx on public.desk_messages (created_at desc);
create index if not exists desk_rounds_created_idx on public.desk_rounds (created_at desc);
create index if not exists desk_commands_pending_idx on public.desk_commands (status) where status = 'pending';

-- Sécurité : lecture et commandes réservées au propriétaire. Les écritures du desk passent par
-- la fonction Edge desk-sync (clé service), jamais par le navigateur.
alter table public.desk_messages  enable row level security;
alter table public.desk_rounds    enable row level security;
alter table public.desk_positions enable row level security;
alter table public.desk_status    enable row level security;
alter table public.desk_commands  enable row level security;

create or replace function public.is_desk_owner() returns boolean
language sql stable as $$ select coalesce(auth.jwt() ->> 'email', '') = 'TON_EMAIL@exemple.com' $$;

create policy "owner reads messages"  on public.desk_messages  for select to authenticated using (public.is_desk_owner());
create policy "owner reads rounds"    on public.desk_rounds    for select to authenticated using (public.is_desk_owner());
create policy "owner reads positions" on public.desk_positions for select to authenticated using (public.is_desk_owner());
create policy "owner reads status"    on public.desk_status    for select to authenticated using (public.is_desk_owner());
create policy "owner reads commands"  on public.desk_commands  for select to authenticated using (public.is_desk_owner());
create policy "owner sends commands"  on public.desk_commands  for insert to authenticated
  with check (public.is_desk_owner() and status = 'pending');

-- Temps réel pour l'app
alter publication supabase_realtime add table public.desk_messages, public.desk_rounds, public.desk_positions, public.desk_status, public.desk_commands;
```

2. Crée une fonction Edge nommée exactement `desk-sync`, avec la vérification JWT désactivée (verify_jwt = false),
   et ce code exact :

```ts
// Fonction Edge Supabase "desk-sync" : seule porte d'entrée du desk (PC) vers la base.
// Secret requis : DESK_SYNC_SECRET (le même que dans grok-desk/.env). Désactiver la vérification JWT (verify_jwt = false).
import { createClient } from "npm:@supabase/supabase-js@2";

const BOTS = new Set(["scanner", "news", "planner", "risk", "skeptic", "chef"]);
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

Deno.serve(async (req) => {
  const secret = Deno.env.get("DESK_SYNC_SECRET");
  if (req.method !== "POST" || !secret || req.headers.get("x-desk-secret") !== secret) {
    return json({ error: "unauthorized" }, 401);
  }
  const sb = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
  const { action, data } = await req.json().catch(() => ({}));
  let error = null;

  switch (action) {
    case "message":
      if (!BOTS.has(data?.bot)) return json({ error: "bad bot" }, 400);
      ({ error } = await sb.from("desk_messages").insert({ bot: data.bot, text: String(data.text).slice(0, 4000) }));
      break;
    case "round":
      ({ error } = await sb.from("desk_rounds").insert(data));
      break;
    case "positions":
      if (Array.isArray(data) && data.length) {
        ({ error } = await sb.from("desk_positions").upsert(data.map((p) => ({ ...p, updated_at: new Date().toISOString() }))));
      }
      break;
    case "status":
      ({ error } = await sb.from("desk_status").upsert({ id: 1, data, updated_at: new Date().toISOString() }));
      break;
    case "commands": {
      const { data: rows, error: e } = await sb.from("desk_commands").select("id, command, arg")
        .eq("status", "pending").order("created_at").limit(10);
      if (e) return json({ error: e.message }, 500);
      if (rows?.length) await sb.from("desk_commands").update({ status: "taken" }).in("id", rows.map((r) => r.id));
      return json({ commands: rows ?? [] });
    }
    case "command_done":
      ({ error } = await sb.from("desk_commands").update({ status: "done", result: data?.result ?? "ok", done_at: new Date().toISOString() }).eq("id", data?.id));
      break;
    default:
      return json({ error: "unknown action" }, 400);
  }
  return error ? json({ error: error.message }, 500) : json({ ok: true });
});
```

3. Crée un secret `DESK_SYNC_SECRET` (je te donnerai la valeur) utilisé par cette fonction.
4. Authentification : e-mail + mot de passe, seul TON_EMAIL@exemple.com est autorisé (refuse poliment les autres comptes à l'écran).

## Interface
En-tête fixe (toujours visible) :
- pastille marché : « Ouvert · 10:42 NY · clôture dans 3 h 18 » (vert) ou « Fermé · réouverture lun. 15:30 (Paris) » (gris),
  calculée depuis `desk_status.data` (market_open, ny_time, minutes_to_close, next_open) ;
- badge d'exécution depuis `data.execution` : « PAPIER » (gris), « MT5 DÉMO » (bleu), « MT5 RÉEL » (rouge vif, clignotant discret) ;
- équité (`data.equity`, `data.currency`), P&L du jour (`data.day_pnl`, vert/rouge), trades `data.trades_today`/`data.max_trades` ;
- si `desk_status.updated_at` date de plus de 3 minutes : bandeau orange « Desk hors ligne depuis X min » ;
- si `data.paused` : bandeau jaune « Desk en pause ».

Barre d'onglets en bas, 4 onglets :

1. **Débat** (par défaut) : fil façon messagerie de `desk_messages` en temps réel (Supabase Realtime), plus récents en bas,
   défilement automatique. Chaque bulle : avatar emoji + nom + heure (Paris) + texte. Couleurs par bot :
   scanner 🔎 cyan, news 📰 jaune, planner 🎯 « Planificateur » bleu, risk 🛡️ « Risque » orange, skeptic 😈 « Sceptique » violet,
   chef 👑 « Chef » doré (bulle plus large, bordure dorée). Séparateur « Tour de 10:45 NY — NVDA » quand une nouvelle ligne
   arrive dans `desk_rounds`. Charge les 200 derniers messages, puis « charger plus » en haut.

2. **Positions** : cartes des positions `desk_positions` avec status open/pending en haut (ticker, LONG vert / SHORT rouge,
   actions, entrée, stop, objectif, une barre horizontale stop → entrée → objectif, badge broker/ticket),
   puis « Clôturées aujourd'hui » avec P&L coloré et raison (stop, objectif, clôture). Total du jour en bas.

3. **Décisions** : liste de `desk_rounds` (plus récent en haut) : heure NY, ticker, badge décision (GO vert, NO_GO gris,
   WATCH bleu, BROKER_REJECTED rouge), R:R, taille, et si refusé la liste `risk.violations`. Les tours `quiet` sont masqués
   (interrupteur pour les afficher). Petit graphique du P&L cumulé du jour à partir des positions clôturées.

4. **Pilotage** : gros boutons qui insèrent une ligne dans `desk_commands` :
   « ⏸ Pause » (command=pause), « ▶️ Reprendre » (resume), « 🔎 Scanner un titre » (champ ticker en majuscules → command=scan, arg),
   « 👑 Demander au Chef » (champ texte → command=ask, arg), « 📋 État » (status). Afficher les 10 dernières commandes avec
   leur statut en temps réel (pending → taken → done + result). Confirmation avant Pause. Rappel en bas en petit :
   « L'app ne passe aucun ordre : seules les décisions du Chef sur le PC le font, avec les garde-fous du Risque. »

Design : sombre, sobre, lisible au soleil, gros chiffres, police monospace pour les prix, animations légères à l'arrivée
d'un message, retour haptique (navigator.vibrate) quand le Chef dit GO ou qu'un stop est touché si l'utilisateur l'a activé.
Tout en français, heures affichées en heure de Paris sauf mention « NY ».
=====

## Après la création

1. Dans Lovable : *Cloud → Secrets*, crée `DESK_SYNC_SECRET` avec une longue valeur aléatoire (ex. générée par un gestionnaire de mots de passe).
2. Récupère l'URL de la fonction : `https://<projet>.supabase.co/functions/v1/desk-sync` (Lovable l'affiche dans *Cloud → Edge Functions*).
3. Sur le PC, dans `grok-desk\.env` :
   ```
   DESK_SYNC_URL=https://<projet>.supabase.co/functions/v1/desk-sync
   DESK_SYNC_SECRET=<la même valeur>
   ```
4. Teste sans marché ouvert : `npm run desk:demo` → les messages de la démo doivent apparaître dans l'onglet Débat.
5. Sur le téléphone : ouvre l'URL publiée de l'app → *Partager → Sur l'écran d'accueil*.
