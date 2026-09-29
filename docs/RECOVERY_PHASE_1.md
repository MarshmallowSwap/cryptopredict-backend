# CryptoPredict — Fase 1: recupero in sola lettura

## Scopo e perimetro

Questa release prepara un backend di recupero. **Non ripristina il trading e non
mette in sicurezza i contratti gia pubblicati.** Non modifica lo schema o i dati
del database e non firma transazioni. L'installazione su un branch GitHub non
modifica il processo gia in esecuzione sul VPS.

Baseline backend: `5b2ee5edde006c06cd70a3e8e3e295de1c2bd201`.
Il codice monetario storico resta consultabile nel commit padre. Nessun valore
storico viene cancellato, azzerato o promosso a saldo verificato.

## Cambiamenti

- API: tutte le richieste diverse da GET/HEAD/OPTIONS ricevono HTTP 503 con
  `RECOVERY_READ_ONLY`, prima della lettura del body e del dispatch ai router.
- Letture pubbliche: health, stato, catalogo mercati, immagini e stime dello yield.
  Le altre letture, inclusi utenti, amministrazione e OpenAPI, richiedono un nuovo
  `RECOVERY_ADMIN_TOKEN` via `Authorization: Bearer ...`. Le credenziali nelle URL
  non sono accettate. Questo non e un sistema di login degli utenti.
- Il vecchio token admin predefinito e rimosso; l'impostazione legacy non concede
  accesso. Token recovery assente = letture private disabilitate. Non usare il
  token recovery nel browser pubblico o nel codice frontend.
- Il client Supabase usato dai router e una facade che espone SELECT e filtri,
  non insert/update/delete/upsert/RPC/storage. **E difesa applicativa, non un
  ruolo SQL read-only e non un sostituto di RLS.** La chiave sottostante conserva
  i propri privilegi. Restano da verificare privilegi e funzioni del database.
- Nessuno scheduler parte da `start.py`. Accrual e distribuzione reward diretti
  sono bloccati; il resolver non carica chiavi ne crea transazioni. Non esiste un
  flag per riattivare questi percorsi nella presente release.
- Le stime dello yield restano compatibili nei campi numerici ma vengono marcate
  `legacy_simulation`, `redeemable: false`, `funding_verified: false`.
- Il webhook separato non esegue piu comandi di pull/install/restart, anche per
  una consegna firmata valida. Il secret predefinito e rimosso. La firma viene
  comunque verificata e il body e limitato a 1 MiB.
- API e webhook partono su loopback, per un reverse proxy locale controllato.

## Incompatibilita intenzionali

Creazione mercati, upload, puntate, depositi, risoluzioni, cancellazioni e accrediti
via API non sono utilizzabili in questa release. I vecchi link amministrativi con
`admin_token` nella query non funzionano: occorre un client operatore con header.
Il frontend continua a poter inviare transazioni direttamente alla blockchain:
**il blocco API non blocca i contratti o un wallet.** Non presentare l'app pubblica
come pronta a operare perche la sola API e in recovery.

## Verifica locale

```sh
python -m unittest discover -s tests -v
python -m compileall -q app tests start.py webhook.py
```

La suite esegue HTTP ASGI reali contro il middleware e usa spy per verificare che
richieste negate e operazioni DB vietate non raggiungano l'handler/SDK. Non chiama
Supabase, price feed o blockchain. Non e un test end-to-end del prodotto.
Il workflow CI esegue anche l'import dell'app completa usando i router del repo.

## Gate prima di una installazione in staging

1. Verificare/ruotare tutte le credenziali esposte storicamente, incluse service
   key, admin e webhook. La rimozione dal codice non revoca una credenziale.
2. Verificare un backup e una prova di ripristino separata. Un conteggio tabelle
   o una scheda di progetto NON e un backup.
3. Identificare la release/processo VPS effettivo e disabilitare job esterni,
   altri worker e vecchi servizi di auto-deploy: questa patch non li arresta.
4. Usare un ambiente isolato e credenziali a privilegio minimo. Non caricare la
   chiave privata del resolver nel processo recovery. Rivedere le policy RLS.
5. Configurare HTTPS anche sul collegamento proxy/backend prima di inviare token
   amministrativi. Il vecchio proxy a HTTP non e un canale sicuro per i token.
6. Importare l'app completa, verificare le letture con lo SDK Supabase reale e
   confrontare conteggi e dati prima/dopo. Collaudare il frontend in recovery.
7. Verificare autorizzazione Vercel del team corretto. Nessun deploy automatico
   e autorizzato o avviato da questa PR.

## Scaletta successiva e criteri di uscita

### Fase 2 — Un solo mercato con valuta di test

Riconciliare rete + indirizzo contratto + marketId + ABI + sorgente/bytecode.
Recuperare il sorgente AMM e il manifest deployment prima di ricollegarli.
Non risolvere oggi mercati scaduti usando il prezzo di oggi.

Correggere payout/refund nella valuta del mercato, fee aggregate, liquidita
iniziale del creatore e copertura delle passivita; escludere yield non finanziato.
Eseguire prove su rete locale, poi Base Sepolia senza fondi reali: YES/NO, piu
partecipanti, 6/18 decimali, doppio claim, annullamento, zero vincitori, trasferimenti
falliti e tentativi non autorizzati. Nessun deploy del contratto prima dei test.

### Fase 3 — Riconciliazione e interfaccia

Indicizzazione idempotente degli eventi, gestione reorg, storico verificabile e
stato UI separato da simulazione. Correggere il doppio `positionMarket` nel
frontend solo dopo aver identificato il contratto giusto; non attivarlo alla cieca.
Il database non deve diventare fonte autonoma di fondi spendibili.

### Fase 4 — Estensioni

Solo dopo un ciclo completo verificato: mercato secondario, AMM, staking,
presale e nuove categorie di oracoli. Revisione indipendente prima di mainnet.
