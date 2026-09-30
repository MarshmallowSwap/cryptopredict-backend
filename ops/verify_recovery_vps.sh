#!/usr/bin/env bash
set -euo pipefail
DOMAIN="${CRYPTOPREDICT_API_DOMAIN:-api.cryptopredict.app}"
SERVICE=cryptopredict-recovery

echo "== service =="
systemctl is-active "$SERVICE"
systemctl --no-pager --full status "$SERVICE" | sed -n '1,18p'

echo "== local health =="
curl -fsS http://127.0.0.1:8000/health
echo
curl -fsS http://127.0.0.1:8000/api/v1/system/status
echo

echo "== local write guard =="
code="$(curl -sS -o /tmp/cp-write-check.json -w '%{http_code}' -X POST   -H 'Content-Type: application/json' -d '{}'   http://127.0.0.1:8000/api/v1/markets)"
[[ "$code" == "503" ]] || { cat /tmp/cp-write-check.json; echo; exit 1; }
cat /tmp/cp-write-check.json; echo

echo "== network exposure =="
ss -lntp | grep -E ':(8000|9000)\b' || true
if ss -lnt | awk '{print $4}' | grep -Eq '(^|:)(0\.0\.0\.0|\[::\]):(8000|9000)$'; then
  echo "ERROR: recovery backend port exposed publicly"; exit 1
fi

echo "== nginx =="
nginx -t

echo "== public HTTPS =="
if getent hosts "$DOMAIN" >/dev/null 2>&1; then
  curl -fsS "https://$DOMAIN/health"
  echo
  curl -fsS "https://$DOMAIN/api/v1/system/status"
  echo
else
  echo "$DOMAIN unresolved; HTTPS validation pending."
fi

echo "PASS recovery VPS verification"
