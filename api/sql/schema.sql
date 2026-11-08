create extension if not exists postgis;
create extension if not exists pg_trgm;

create table if not exists centers (
  id serial primary key,
  name text not null,
  kind text,
  geom geography(Point, 4326) not null
);

create table if not exists places (
  id serial primary key,
  name text not null,
  geom geography(Point, 4326) not null
);
create index if not exists places_name_trgm on places using gin (name gin_trgm_ops);

create table if not exists history (
  id bigserial primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  center_id int references centers(id),
  end_lat double precision,
  end_lon double precision,
  shortest_m real,
  fastest_s real,
  scenario text,
  created_at timestamptz default now()
);

create table if not exists favorites (
  id bigserial primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  center_id int references centers(id),
  end_lat double precision,
  end_lon double precision,
  label text,
  created_at timestamptz default now()
);

alter table centers enable row level security;
alter table places enable row level security;
alter table history enable row level security;
alter table favorites enable row level security;

drop policy if exists "lecture publique des centres" on centers;
create policy "lecture publique des centres" on centers
  for select using (true);

drop policy if exists "lecture publique des lieux" on places;
create policy "lecture publique des lieux" on places
  for select using (true);

drop policy if exists "historique personnel" on history;
create policy "historique personnel" on history
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "favoris personnels" on favorites;
create policy "favoris personnels" on favorites
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);


