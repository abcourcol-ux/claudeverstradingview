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
