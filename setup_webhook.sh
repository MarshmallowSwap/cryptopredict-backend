#!/bin/bash
set -e
echo "=== Setup GitHub Webhook Auto-Deploy ==="

# Copia i file
cd /root/cryptopredict-backend
git pull

# Install dipendenze webhook
pip install fastapi uvicorn --break-system-packages -q

# Crea service systemd
cat > /etc/systemd/system/cp-webhook.service << 'SVCEOF'
[Unit]
Description=CryptoPredict GitHub Webhook
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/cryptopredict-backend
Environment="WEBHOOK_SECRET=cp-webhook-2026"
ExecStart=/usr/bin/python3 /root/cryptopredict-backend/webhook.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVCEOF

# Abilita e avvia
systemctl daemon-reload
systemctl enable cp-webhook
systemctl restart cp-webhook

# Apri porta 9000 su nginx
echo ""
echo "=== Aggiorna Nginx per esporre /webhook ==="
echo "Aggiungi nel blocco server di nginx:"
echo ""
echo "  location /webhook/ {"
echo "    proxy_pass http://127.0.0.1:9000;"
echo "    proxy_set_header Host \$host;"
echo "  }"
echo ""
echo "Poi: nginx -t && systemctl reload nginx"
echo ""
echo "=== Webhook URL ==="
echo "  http://95.217.10.201/webhook/github"
echo "  Secret: cp-webhook-2026"
echo ""
systemctl status cp-webhook --no-pager
