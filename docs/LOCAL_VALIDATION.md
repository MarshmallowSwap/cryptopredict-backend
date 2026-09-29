# Verifica locale — senza GitHub Actions

Aggiornamento del 30 settembre 2026: il proprietario ha chiesto di non usare
GitHub Actions, per assenza di crediti. Il workflow introdotto per il recupero
è stato spostato da `.github/workflows/` a `docs/ci-disabled/` con estensione
`.yml.txt`: è solo documentazione e non va eseguito automaticamente.
Non sono stati modificati impostazioni dell'account, branch protection o main.

Questo documento sostituisce i riferimenti alla CI come prerequisito operativo
in `RECOVERY_PHASE_1.md` e nella descrizione iniziale della PR. I vecchi errori
Actions non vanno ulteriormente diagnosticati per proseguire il recupero.
Le verifiche tecniche restano necessarie, ma possono essere eseguite localmente.

## Verifica rieseguita

- Python 3.13.5: **32 test di regressione superati**.
- Eseguiti sui file estratti dal pacchetto della Fase 1, con la suite originale.
- Nessun runner remoto, connessione a Supabase o transazione blockchain.
- Non è stata rieseguita la prova di importazione dell'applicazione completa:
  il pacchetto locale contiene le modifiche, non il repository intero.
- Non è stata verificata l'installazione pulita di `requirements.txt`.

Dalla radice del repository, in un ambiente Python isolato con dipendenze già
installate:

```sh
python -m unittest discover -s tests -v
python -m compileall -q app tests start.py webhook.py
```

La suite imposta configurazioni fittizie. Non copiare chiavi reali nell'ambiente
di test e non avviare il vecchio processo VPS per eseguire questi controlli.
L'installazione delle dipendenze richiede l'accesso al registry, non crediti Actions.

## Gate ancora aperti

Test su installazione pulita delle dipendenze fissate, importazione dell'app
completa, backup e ripristino, rotazione delle credenziali storiche, permessi del
database, HTTPS del backend e verifica end-to-end in ambiente separato.
Il progetto frontend corretto è `vaultworlds-projects/cryptopredict`; il vecchio
errore di autorizzazione sul team `mash` non è un blocco per il progetto corretto.

Nessun merge, deploy, modifica ai dati o abilitazione di operazioni monetarie.
