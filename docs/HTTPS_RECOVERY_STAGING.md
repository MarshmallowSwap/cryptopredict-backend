# CryptoPredict recovery — HTTPS backend staging

This runbook prepares the existing VPS for a **read-only recovery API** behind
TLS. It does not authorize production traffic or re-enable monetary writes.

## Target topology

```
browser / Vercel preview
        |
        | HTTPS
        v
api.cryptopredict.app :443
        |
        | loopback HTTP only
        v
127.0.0.1:8000  -> FastAPI recovery
```

The public network must not expose ports 8000 or 9000.

## Recovery contract configuration

The recovery backend now points to:

- PredictionMarket: `0x76f9660a8801f97a8F5D1AC2036b9a9C22495436`
- CPRED: `0xEc937bF3123874115EDcBBE1b3802C95f572e8E5`
- MockUSDC: `0x8A54f0e841CFCA5fA654912AF33cCD121D182311`
- MockUSDT: `0xaBB48e1693Df04fb894843e52B239D5C5d0ab871`
- PositionMarket: zero address
- AMM: zero address
- PresaleStaking: zero address

The API remains read-only regardless of these addresses.

## VPS steps

1. Create DNS record `api.cryptopredict.app` pointing to the VPS.
2. Install the recovery branch in a separate directory or checkout:
   `work/recovery-phase1-20260930`.
3. Configure a fresh `RECOVERY_ADMIN_TOKEN` and the required Supabase
   credentials. Do not reuse historical admin/webhook credentials.
4. Ensure `start.py` binds only to `127.0.0.1:8000`.
5. Install `ops/nginx-recovery.conf` as the Nginx site.
6. Obtain a TLS certificate, for example:
   `certbot --nginx -d api.cryptopredict.app`.
7. Restrict the firewall so only 22/80/443 are public as needed; 8000/9000
   must not be internet-accessible.
8. Validate:
   - `https://api.cryptopredict.app/health`
   - `https://api.cryptopredict.app/api/v1/system/status`
   - POST to any API path returns recovery read-only error.
   - private GET without bearer token is denied.

## Do not do yet

- do not point production Vercel to this hostname;
- do not start legacy scheduler/auto-resolver;
- do not load a resolver private key;
- do not enable AMM, staking, presale or secondary-market addresses;
- do not treat Supabase balances as verified on-chain funds.

The frontend recovery can use the blockchain directly while this API staging
path is being validated.
