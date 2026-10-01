#!/usr/bin/env bash
set -euo pipefail
systemctl stop cryptopredict-recovery 2>/dev/null || true
systemctl disable cryptopredict-recovery 2>/dev/null || true
rm -f /etc/nginx/sites-enabled/cryptopredict-recovery
nginx -t && systemctl reload nginx
echo "Recovery API stopped and nginx site disabled. Files and env preserved for audit."
