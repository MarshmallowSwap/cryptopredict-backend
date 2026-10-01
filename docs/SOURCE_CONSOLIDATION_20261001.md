# CryptoPredict — consolidamento nei repository originali

## Decisione del proprietario

Usare GitHub come unica fonte dei sorgenti. Riprendere le pagine e i servizi
esistenti, conservare la grafica approvata, non creare un prodotto parallelo e
non distribuire altri ZIP incrementali per ogni modifica. Il PC resta per ora
l'host di collaudo; il suo filesystem non si aggiorna automaticamente da GitHub.

Repository e branch correnti:
- frontend: `MarshmallowSwap/cryptopredict`, `work/recovery-frontend-20260930`;
- backend: `MarshmallowSwap/cryptopredict-backend`, `work/recovery-phase1-20260930`;
- contratti: `MarshmallowSwap/cryptopredict-contracts`, `work/recovery-contracts-20260930`.

## Prima integrazione effettuata

Il servizio di lettura che era in `launcher/market_reads.py` dell'add-on PC e che
ha alimentato il catalogo collaudato dal proprietario viene incorporato, senza
modifiche funzionali, in `app/services/chain_catalog.py`.

`app/routers/markets.py`, gia' presente nel backend originale, ora usa quel
servizio al posto del database legacy. `app/main.py` registra il router originale
e un alias per il percorso canonico del collaudo: entrambe le rotte condividono
la stessa istanza del catalogo. Non sono due backend distinti.

- `GET /api/v1/markets`: catalogo con filtri `status`, `category`, `limit`, `offset`;
- `GET /api/v1/markets/{id}`: dettaglio identificato dal nuovo contratto;
- `GET /api/v1/markets/images/all`: `{}` finche' non esiste un indice media legato
  a chain + contratto + id; niente associazione automatica alle immagini legacy;
- `GET /api/v1/recovery/markets` e `/{id}`: alias canonico senza filtri.

I vecchi handler di mutazione dei saldi simulati vengono conservati esattamente
in `legacy/markets_supabase_20260930.py.disabled`, ma non sono importati ne'
registrati. Nessuna tabella, saldo o transazione blockchain viene modificata.
Le scritture HTTP restano bloccate anche con token amministrativo.

## Contratto dei dati e compatibilita'

Lo schema canonico e' `cryptopredict-recovery-catalog-v1`. Gli importi sono stringhe
in unita' atomiche (`yes_pool_raw`, `no_pool_raw`, `deposited_raw`, `escrow_raw`),
con `currency_index`, `currency` e `decimals` separati. La quota dei depositi non
e' una probabilita', un prezzo AMM o una promessa di rendimento.

Le pagine originali devono essere adattate a questo contratto dei dati: non si
sostiene che la sola modifica al backend abbia gia' completato il frontend.
`title/pool_size/yield_info` del vecchio DB NON vengono ricostruiti o simulati.
Per la lista filtrata, `total` e `returned` riguardano la vista; `market_count`,
totali per valuta e `snapshot_digest` descrivono lo snapshot completo. `complete`
e' false quando la risposta contiene un sottoinsieme. L'alias canonico restituisce
sempre l'intero snapshot. Il gateway di test aggiunge ancora il suo `gateway_run_id`:
questo identificatore di sessione non e' una credenziale dell'API originale.

## Controlli conservati

Solo Base Sepolia, contratto e collateral fissi; receipt del deploy e bytecode;
letture allo stesso blocco `safe` con ricontrollo dell'hash; decimali verificati;
nessun signer o client Supabase nel catalogo; nessun fallback su dati legacy;
errori senza contenuto RPC o segreti; cache breve e limite a quattro richieste
catalogo ammesse contemporaneamente. Configurazioni con indirizzi diversi sono
rifiutate. Lo status di sistema non dichiara una lettura live mai effettuata.

## Verifiche di questa integrazione

Comando dal repository, con dipendenze installate:

```sh
python -m unittest discover -s tests -p 'test_*catalog*.py' -v
python -m unittest discover -s tests -p 'test_markets_native_api.py' -v
```

Eseguiti nell'ambiente di sviluppo:
- 46 test codec/catalogo, ripresi dall'add-on verificato;
- 26 test router FastAPI + RecoveryGuard: percorsi originali/alias, dettaglio,
  filtri, paginazione, cache condivisa, dati mancanti, errori, mutazioni bloccate,
  autenticazione privata, CORS e configurazioni incoerenti;
- 72/72 PASS; RPC simulato, nessun accesso alla rete o al database.

Ambiente: Python 3.13.5, FastAPI 0.128.2, Starlette 0.50.0, httpx 0.28.1.
Questi test NON sono un nuovo collaudo Windows, del tunnel o dell'intero stack
con tutte le dipendenze del requirements originale. I report reali precedenti
restano evidenza della versione effettivamente eseguita in quelle sessioni.

## Ordine di completamento — ancora aperto

1. Unificare provider EIP-6963 e sessione nei file comuni originali `web3.js`
   e `_shared.js`; le pagine non devono tornare al provider globale ambiguo.
2. Integrare catalogo e wallet in `mercati.html`, `market.html`, `portfolio.html`.
3. Riprendere `crea.html`: mantenere la funzione esistente, dichiarare se il
   mercato e' manuale o price-target, validare la regola e riabilitare solo il
   percorso effettivamente verificato. `targetPrice=0` non vieta la risoluzione
   manuale; non va confuso con una risoluzione automatica da prezzi.
4. Integrare le firme MetaMask nei flussi originali: create, bet, claim, refund.
   Nessuna private key nel backend; nessun nuovo deploy Solidity senza necessita'.
5. Portare anche l'avvio Windows/tunnel nei sorgenti del repository e migrare
   l'installazione locale una volta sola, preservando i segreti cifrati.
6. Restyling in pausa; AMM, secondario, staking, presale e governance conservati,
   ma abilitati soltanto dopo verifica della specifica funzione. I toggle di
   visibilita' non costituiscono autorizzazione o sicurezza on-chain.

Nessun merge a main, deploy di produzione, GitHub Actions, migrazione Supabase,
nuova puntata o operazione economica e' autorizzato da questo consolidamento.
