# CryptoPredict — Backend

FastAPI backend per il prediction market CryptoPredict.

## Stack
- **FastAPI** + Uvicorn
- **Supabase** (PostgreSQL + Auth)
- **APScheduler** per cron jobs
- **httpx** per price feeds (Binance + CoinGecko)

## Setup VPS

```bash
# 1. Clona il repo
git clone https://github.com/MarshmallowSwap/cryptopredict-backend
cd cryptopredict-backend

# 2. Crea virtualenv
python3 -m venv venv
source venv/bin/activate

# 3. Installa dipendenze
pip install -r requirements.txt

# 4. Configura .env
cp .env.example .env
nano .env  # compila SUPABASE_URL, SUPABASE_SERVICE_KEY, ADMIN_TOKEN

# 5. Esegui le migration SQL su Supabase
# Vai su Supabase → SQL Editor → incolla supabase/migrations/001_initial_schema.sql

# 6. Avvia il server
python start.py
```

## Avvio con systemd (production)

```ini
# /etc/systemd/system/cryptopredict.service
[Unit]
Description=CryptoPredict API
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/cryptopredict-backend
ExecStart=/home/ubuntu/cryptopredict-backend/venv/bin/python start.py
Restart=always
RestartSec=5
EnvironmentFile=/home/ubuntu/cryptopredict-backend/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable cryptopredict
sudo systemctl start cryptopredict
sudo systemctl status cryptopredict
```

## Nginx reverse proxy

```nginx
server {
    server_name api.cryptopredict.app;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## API Endpoints

| Metodo | Path | Descrizione |
|--------|------|-------------|
| GET | `/api/v1/markets` | Lista mercati |
| GET | `/api/v1/markets/{id}` | Mercato singolo |
| POST | `/api/v1/markets` | Crea mercato |
| POST | `/api/v1/markets/{id}/bet` | Piazza scommessa |
| POST | `/api/v1/markets/{id}/resolve` | Risolvi mercato |
| GET | `/api/v1/users/{id}` | Profilo utente |
| GET | `/api/v1/users/{id}/stats` | Stats + yield share |
| POST | `/api/v1/users` | Crea utente |
| POST | `/api/v1/users/{id}/deposit` | Deposita USDC |
| GET | `/api/v1/yield/stats` | Stats yield globali |
| GET | `/api/v1/yield/market/{id}` | Yield per mercato |
| POST | `/api/v1/admin/cron/resolve-expired` | Auto-resolve (cron) |
| POST | `/api/v1/admin/cron/accrue-yield` | Accrua yield (cron) |

## Cron Jobs automatici
- **Ogni 5 min**: auto-resolve mercati price_target scaduti
- **00:05 ogni giorno**: accrua yield sui pool aperti + distribuisce rewards agli staker
