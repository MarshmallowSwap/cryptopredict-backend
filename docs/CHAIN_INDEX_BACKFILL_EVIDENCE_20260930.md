# CryptoPredict — chain → Supabase backfill evidence

Date: 30 September 2026  
Network: Base Sepolia (84532)  
PredictionMarket: `0x76f9660a8801f97a8F5D1AC2036b9a9C22495436`

## Result

A one-time server-side backfill was executed from the verified recovery contract
into the isolated recovery index tables.

Indexer state after the run:
- deployment block: `47487856`
- finalized block: `47510060`
- confirmations: `12`
- source of truth: Base Sepolia blockchain
- database role: index only

Indexed event counts:
- BetPlaced: 6
- FeesAccrued: 1
- MarketCancelled: 2
- MarketCreated: 3
- MarketResolved: 1
- MinCpredUpdated: 1
- PayoutClaimed: 1
- RefundClaimed: 2

## Market #2 reconciliation

The database index reconstructed the completed two-wallet test exactly:

1. MarketCreated #2
2. Wallet A BetPlaced YES: `100000000` raw MockUSDC = 100 USDC
3. Wallet B BetPlaced NO: `100000000` raw MockUSDC = 100 USDC
4. MarketResolved outcome = `2` (NO)
5. FeesAccrued:
   - creatorFee = `2000000` = 2 USDC
   - protocolFee = `2000000` = 2 USDC
6. PayoutClaimed by Wallet B:
   - `196000000` raw MockUSDC = 196 USDC

This matches the independent two-wallet smoke report and proves the recovery
index is projecting chain events rather than reconstructing balances from legacy
Supabase rows.

## One-time execution hardening

The temporary backfill path was shut down after the successful run:
- the internal invocation token was deleted;
- the temporary control table was dropped;
- `pg_net` was disabled again;
- the temporary Edge Function was replaced with a disabled version requiring JWT;
- Supabase Security Advisor returned **0 lints** after cleanup.

Future syncs must use the reviewed backend script:
`scripts/recovery_indexer.py`

That script:
- has no private key;
- indexes finalized blocks only;
- is idempotent on chain ID + contract + transaction hash + log index;
- writes only to recovery index tables;
- is not scheduled automatically during recovery.

## Remaining infrastructure gate

The backend recovery process still needs to be installed on the VPS behind
`https://api.cryptopredict.app` before continuous/manual operational syncs and
the resolver evidence endpoint are considered live.
