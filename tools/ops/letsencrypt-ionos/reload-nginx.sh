#!/usr/bin/env bash
# Certbot deploy hook: reload nginx after any certificate is renewed so the
# new certificate is served. Install in /etc/letsencrypt/renewal-hooks/deploy/
set -euo pipefail
nginx -t -q && systemctl reload nginx
logger -t certbot-deploy "nginx reloaded after renewal of ${RENEWED_LINEAGE:-unknown}"
