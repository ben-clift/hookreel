-- Run once in Supabase: SQL Editor > New query > paste > Run.

create table if not exists public.records (
  id bigint generated always as identity primary key,
  kind text not null,
  data jsonb not null,
  created_at timestamptz not null default now()
);
create index if not exists records_kind_id on public.records (kind, id);

-- Only the app's secret key may touch it: switch on RLS and add no public policies.
alter table public.records enable row level security;

-- Private bucket for finished ads (the free plan caps a single file at 50 MB).
insert into storage.buckets (id, name, public) values ('ads', 'ads', false)
on conflict (id) do nothing;
