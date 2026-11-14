create extension if not exists postgis;
create extension if not exists pg_trgm;

-- Lieux recherchables (import depuis OpenStreetMap)
create table if not exists places (
  id serial primary key,
  name text not null,
  category text,
  geom geography(Point, 4326) not null
);
create index if not exists places_geom_gist on places using gist (geom);
create index if not exists places_name_trgm on places using gin (name gin_trgm_ops);

-- Pénalités posées par l'administrateur
create table if not exists penalties (
  id bigserial primary key,
  edge_ids int[] not null,
  way_id bigint,
  level text not null check (level in ('light', 'medium', 'high', 'closed')),
  factor real not null,
  reason text not null check (length(trim(reason)) > 0),
  starts_at timestamptz not null,
  ends_at timestamptz not null,
  created_by uuid references auth.users(id),
  created_at timestamptz default now(),
  deleted_at timestamptz,
  check (ends_at > starts_at)
);
create index if not exists penalties_ends_at on penalties (ends_at);

-- Rôles des comptes Supabase Auth
create table if not exists profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  role text not null default 'user' check (role in ('user', 'admin'))
);

-- Sécurité au niveau des lignes (RLS)
alter table places enable row level security;
alter table penalties enable row level security;
alter table profiles enable row level security;

drop policy if exists "lecture publique des lieux" on places;
create policy "lecture publique des lieux" on places
  for select using (true);

drop policy if exists "lecture publique des penalites" on penalties;
create policy "lecture publique des penalites" on penalties
  for select using (true);

drop policy if exists "lecture de son propre profil" on profiles;
create policy "lecture de son propre profil" on profiles
  for select using (auth.uid() = user_id);