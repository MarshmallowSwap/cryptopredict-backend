-- CryptoPredict recovery chain index — applied 2026-09-30.
-- This file records the schema already applied to Supabase project ezcnodxtqwcwwsdmwbsf.
-- It is intentionally additive and does not mutate legacy financial rows.

create table if not exists public.recovery_chain_events (
  id bigint generated always as identity primary key,
  chain_id bigint not null,
  contract_address text not null,
  block_number bigint not null,
  block_hash text not null,
  tx_hash text not null,
  tx_index integer not null,
  log_index integer not null,
  event_name text not null,
  market_id numeric(78,0),
  actor text,
  side boolean,
  amount_raw numeric(78,0),
  currency smallint,
  outcome smallint,
  payload jsonb not null default '{}'::jsonb,
  block_timestamp timestamptz not null,
  canonical boolean not null default true,
  indexed_at timestamptz not null default now(),
  constraint recovery_chain_events_identity
    unique (chain_id, contract_address, tx_hash, log_index)
);
create index if not exists recovery_chain_events_market_idx
  on public.recovery_chain_events (chain_id, contract_address, market_id, block_number, log_index);
create index if not exists recovery_chain_events_block_idx
  on public.recovery_chain_events (chain_id, contract_address, block_number, log_index);

create table if not exists public.recovery_indexer_state (
  chain_id bigint not null,
  contract_address text not null,
  deployment_tx_hash text,
  start_block bigint not null,
  last_finalized_block bigint not null,
  last_finalized_hash text,
  confirmations smallint not null default 12 check (confirmations >= 1),
  updated_at timestamptz not null default now(),
  primary key (chain_id, contract_address)
);

alter table public.recovery_chain_events enable row level security;
alter table public.recovery_indexer_state enable row level security;

drop policy if exists recovery_chain_events_deny_public on public.recovery_chain_events;
create policy recovery_chain_events_deny_public
on public.recovery_chain_events for all to anon, authenticated
using (false) with check (false);

drop policy if exists recovery_indexer_state_deny_public on public.recovery_indexer_state;
create policy recovery_indexer_state_deny_public
on public.recovery_indexer_state for all to anon, authenticated
using (false) with check (false);

revoke all on table public.recovery_chain_events from public, anon, authenticated;
revoke all on table public.recovery_indexer_state from public, anon, authenticated;
grant select, insert, update, delete on table public.recovery_chain_events to service_role;
grant select, insert, update, delete on table public.recovery_indexer_state to service_role;
grant usage, select on sequence public.recovery_chain_events_id_seq to service_role;
