# CryptoPredict — Backend API

FastAPI backend per il prediction market CryptoPredict.

## Stack
- **FastAPI** + Uvicorn
- **Supabase** PostgreSQL (`ezcnodxtqwcwwsdmwbsf.supabase.co`)
- **APScheduler** — yield ogni 24h, auto-resolve ogni 5min
- **httpx** — price feeds Binance + CoinGecko

## Deploy su VPS

```bash
git clone https://github.com/MarshmallowSwap/cryptopredict-backend
cd cryptopredict-backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Crea .env
cp .env.example .env
nano .env   # aggiungi SUPABASE_SERVICE_KEY e ADMIN_TOKEN

# Avvia
python start.py
# → API live su http://0.0.0.0:8000
```

## Setup systemd (production)

```ini
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
```

## Nginx

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

## Endpoints

| Metodo | Path | Descrizione |
|--------|------|-------------|
| GET | `/` | Health check |
| GET | `/api/v1/markets` | Lista mercati |
| GET | `/api/v1/markets/{id}` | Mercato singolo + prezzo live |
| POST | `/api/v1/markets` | Crea mercato |
| POST | `/api/v1/markets/{id}/bet` | Piazza scommessa YES/NO |
| POST | `/api/v1/markets/{id}/resolve` | Risolvi + paga vincitori |
| GET | `/api/v1/users/{id}` | Profilo utente |
| GET | `/api/v1/users/{id}/stats` | Stats + yield share |
| GET | `/api/v1/users/{id}/positions` | Posizioni utente |
| GET | `/api/v1/users/{id}/transactions` | Transazioni |
| POST | `/api/v1/users` | Crea utente |
| POST | `/api/v1/users/{id}/deposit` | Deposita USDC |
| GET | `/api/v1/yield/stats` | Yield globale |
| GET | `/api/v1/yield/market/{id}` | Yield per mercato |
| POST | `/api/v1/admin/cron/resolve-expired` | Auto-resolve scaduti |
| POST | `/api/v1/admin/cron/accrue-yield` | Accrua yield |
| GET | `/api/v1/admin/markets/pending` | Mercati da risolvere |
| POST | `/api/v1/admin/markets/{id}/cancel` | Cancella + rimborsa |

## Cron automatici
- **Ogni 5 min** — auto-resolve mercati `price_target` scaduti
- **00:05 ogni giorno** — accrua yield + distribuisce rewards staker CPRED

## Database (Supabase)
8 tabelle: `users`, `markets`, `positions`, `transactions`, `yield_snapshots`, `staking_positions`, `presale_purchases`, `secondary_listings`
