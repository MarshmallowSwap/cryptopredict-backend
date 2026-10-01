# CryptoPredict recovery — oracle and resolution plan

Date: 30 September 2026

## Decision

The recovery release does **not** use the historical auto-resolver and does not
load a resolver private key in the API process.

The old repository contains Chainlink Functions source files. They are legacy
artifacts only. Chainlink Functions was sunset in 2026 and must not be restored
as the new architecture.

## Recovery resolution flow

1. Market configuration is read from the verified Base Sepolia
   PredictionMarket.
2. The backend may generate a **resolution candidate** only when:
   - the market is still Open;
   - the market has expired;
   - the on-chain market contains sufficient deterministic rule data;
   - the configured evidence source is available.
3. For supported crypto price targets, the recovery policy uses the close price
   of the 1-minute Binance candle containing `expiresAt`.
4. The evidence payload includes source, symbol, candle timestamps, observed
   close, target, rule, candidate and a deterministic SHA-256 evidence hash.
5. The backend never submits `resolveMarket`.
6. The operator opens `recovery-admin.html`, connects MetaMask, and the UI
   verifies that the wallet is the on-chain owner or an authorized resolver.
7. Resolution remains disabled until valid evidence exists.
8. The operator reviews the evidence and signs the on-chain transaction.

## Fail-closed rules

- `targetPrice == 0` => no automatic candidate.
- Unsupported/missing asset => no automatic candidate.
- Price source unavailable => no automatic candidate.
- Market not expired => no automatic candidate.
- Market not Open => no automatic candidate.
- No backend private key exists for resolution.
- If a winning side has zero stake, the contract itself cancels the market and
  keeps a fee-free refund path.

## Creation gate

The legacy Create Market frontend currently passed `targetPrice=0` for every
market. The recovery branch gates that page until creation stores correct
on-chain target/rule data. This prevents new markets that cannot later be
resolved deterministically.

## Chain index

The database is an index, not the monetary source of truth.

Tables:
- `recovery_chain_events`
- `recovery_indexer_state`

Identity:
`chain_id + contract_address + tx_hash + log_index`

Only finalized blocks are indexed. The indexer has no private key and is run
manually during recovery; no scheduler is enabled.

## Future production oracle

A production design can use Chainlink Data Feeds for supported price markets and
a current Chainlink CRE workflow or another independently reviewed oracle system
for non-price events. That design is a separate gate and must be reviewed against
the actually supported networks at deployment time.
