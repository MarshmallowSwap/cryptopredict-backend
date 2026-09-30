#!/usr/bin/env bash
set -euo pipefail

DOMAIN="${CRYPTOPREDICT_API_DOMAIN:-api.cryptopredict.app}"
BRANCH="${CRYPTOPREDICT_BRANCH:-work/recovery-phase1-20260930}"
REPO="${CRYPTOPREDICT_REPO:-https://github.com/MarshmallowSwap/cryptopredict-backend.git}"
ROOT=/opt/cryptopredict-recovery
APP="$ROOT/current"
VENV="$ROOT/venv"
ENV_FILE=/etc/cryptopredict-recovery.env
SERVICE=cryptopredict-recovery
NGINX_SITE=/etc/nginx/sites-available/cryptopredict-recovery

die(){ echo "ERROR: $*" >&2; exit 1; }
need(){ command -v "$1" >/dev/null 2>&1 || die "$1 not found"; }

[[ $EUID -eq 0 ]] || die "Run as root."
need git
need python3
need nginx
need openssl
need curl

echo "== CryptoPredict recovery VPS installer =="
echo "Domain: $DOMAIN"
echo "Branch: $BRANCH"

if ! id cryptopredict >/dev/null 2>&1; then
  useradd --system --home "$ROOT" --shell /usr/sbin/nologin cryptopredict
fi
install -d -o cryptopredict -g cryptopredict -m 0750 "$ROOT"

if [[ -d "$APP/.git" ]]; then
  sudo -u cryptopredict git -C "$APP" fetch origin "$BRANCH"
  sudo -u cryptopredict git -C "$APP" checkout "$BRANCH"
  sudo -u cryptopredict git -C "$APP" reset --hard "origin/$BRANCH"
else
  rm -rf "$APP"
  sudo -u cryptopredict git clone --branch "$BRANCH" --single-branch "$REPO" "$APP"
fi

python3 -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install --requirement "$APP/requirements.txt"

[[ -f "$ENV_FILE" ]] || die "$ENV_FILE missing. Create it first from ops/cryptopredict-recovery.env.example."
chown root:cryptopredict "$ENV_FILE"
chmod 0640 "$ENV_FILE"

install -m 0644 "$APP/ops/cryptopredict-recovery.service" "/etc/systemd/system/$SERVICE.service"
sed "s/api\.cryptopredict\.app/$DOMAIN/g" "$APP/ops/nginx-recovery.conf" > "$NGINX_SITE"
ln -sfn "$NGINX_SITE" /etc/nginx/sites-enabled/cryptopredict-recovery

nginx -t
systemctl daemon-reload
systemctl enable "$SERVICE"
systemctl restart "$SERVICE"

for i in {1..20}; do
  if curl -fsS http://127.0.0.1:8000/health >/dev/null; then break; fi
  sleep 1
done
curl -fsS http://127.0.0.1:8000/health >/dev/null || {
  journalctl -u "$SERVICE" -n 100 --no-pager
  die "Local API health check failed"
}

echo "Local API healthy."

SERVER_IP="$(curl -4fsS https://api.ipify.org || true)"
DNS_IP="$(getent ahostsv4 "$DOMAIN" | awk 'NR==1{print $1}')"
echo "Server public IP: ${SERVER_IP:-unknown}"
echo "DNS $DOMAIN: ${DNS_IP:-unresolved}"

if [[ -n "$SERVER_IP" && "$DNS_IP" == "$SERVER_IP" ]]; then
  if command -v certbot >/dev/null 2>&1; then
    certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --redirect       --register-unsafely-without-email || die "certbot failed"
    nginx -t
    systemctl reload nginx
    curl -fsS "https://$DOMAIN/health" >/dev/null || die "Public HTTPS health check failed"
    echo "HTTPS API healthy: https://$DOMAIN/health"
  else
    echo "DNS is ready but certbot is not installed. Install python3-certbot-nginx and rerun."
  fi
else
  echo "DNS is not yet pointing to this server. TLS step skipped safely."
  echo "Create/update an A record: $DOMAIN -> ${SERVER_IP:-<this VPS IP>}, then rerun installer."
fi

echo "Recovery API install complete. No legacy scheduler or webhook auto-deploy enabled."
