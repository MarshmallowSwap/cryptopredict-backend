# CryptoPredict — riconciliazione Supabase recovery

Data: 30 settembre 2026  
Progetto Supabase: `ezcnodxtqwcwwsdmwbsf`

## Stato dati verificato

Conteggi reali:
- users: 32
- markets: 6
- positions: 3
- transactions: 174
- yield_snapshots: 329
- staking_positions: 1
- presale_purchases: 0
- secondary_listings: 0
- trading_orders: 0

Le 174 righe di `transactions` sono **tutte** `staking_reward`, dal
22 marzo al 20 maggio 2026. Non costituiscono evidenza di puntate o payout
on-chain. I 329 `yield_snapshots` appartengono al motore di yield simulato
legacy.

Tre mercati creati il 21 marzo contengono pool/stake/yield simulati e tre
posizioni DB. Non devono essere convertiti in saldi o posizioni del nuovo
PredictionMarket.

Due righe `Market #3` e `Market #4` hanno `onchain_id` 3 e 4, ma il solo
ID non è prova che corrispondano al nuovo contratto recovery. Non migrarle né
risolverle automaticamente.

## Catalogo recovery

`GET /api/v1/markets` nasconde i record legacy per default.

Per una consultazione amministrativa esplicita:
`GET /api/v1/markets?include_legacy=true`

Le righe vengono marcate:
- `legacy_unverified: true`
- `source: supabase_legacy`
- warning di mancata riconciliazione.

Il frontend recovery legge per ora il nuovo contratto direttamente e non usa il
database come fonte monetaria.

## Hardening Supabase applicato

Verifica advisor iniziale:
- `public.update_updated_at()` era `SECURITY DEFINER` e aveva EXECUTE per
  anon/authenticated.

Correzione applicata:
```sql
revoke execute on function public.update_updated_at()
from public, anon, authenticated;
```

Verifica successiva:
- anon execute = false
- authenticated execute = false
- service_role execute = true

La funzione resta disponibile ai trigger esistenti.

Le precedenti policy pubbliche di lettura su `users` e `positions` sono state
rimosse. Queste tabelle contengono dati come Telegram ID, wallet, saldi legacy,
PnL e puntate e non devono essere leggibili direttamente dal client.

Policy recovery applicate:
```sql
create policy users_recovery_deny_public
on public.users for all to anon, authenticated
using (false) with check (false);

create policy positions_recovery_deny_public
on public.positions for all to anon, authenticated
using (false) with check (false);
```

Dopo le modifiche, gli advisor Supabase di sicurezza riportano **0 lint**.

## Cosa NON è stato modificato

- nessuna riga di users/markets/positions/transactions è stata cancellata;
- nessun saldo DB è stato azzerato o trasferito on-chain;
- nessun mercato legacy è stato risolto;
- nessun yield legacy è stato reso spendibile;
- nessuna tabella è stata migrata al nuovo schema eventi.

## Prossimo passo dati

Dopo il test due-wallet su Base Sepolia:
1. definire una tabella/event index separata per il nuovo contratto;
2. indicizzare gli eventi del nuovo PredictionMarket in modo idempotente;
3. usare chainId + contract address + tx hash/log index come identità;
4. gestire reorg e conferme;
5. mantenere il DB come indice/storico, non come fonte autonoma di fondi.

Le modifiche RLS/DCL sopra sono state applicate direttamente al progetto durante
la recovery. Non esiste ancora nel repository una struttura Supabase migrations
ufficiale; catturare queste modifiche in una migration versionata prima del
rilascio è un gate aperto.
