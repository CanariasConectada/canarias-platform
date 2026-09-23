#!/usr/bin/env bash
# Daily safety net: warn when a certificate that should auto-renew is close to
# expiring (renewal normally happens 30 days before). Install in /etc/cron.daily/
# Writes to syslog (tag cert-expiry) and to /var/log/cert-expiry.log.
set -uo pipefail
WARN_DAYS=21
SKIP="${CERT_EXPIRY_SKIP:-exagon.es}"   # space-separated certificate names to ignore
now=$(date +%s)
for conf in /etc/letsencrypt/renewal/*.conf; do
  name=$(basename "$conf" .conf)
  case " $SKIP " in *" $name "*) continue ;; esac
  cert="/etc/letsencrypt/live/$name/cert.pem"
  [ -r "$cert" ] || continue
  end=$(date -d "$(openssl x509 -in "$cert" -noout -enddate | cut -d= -f2)" +%s)
  days=$(( (end - now) / 86400 ))
  if [ "$days" -lt "$WARN_DAYS" ]; then
    msg="WARNING certificate $name expires in $days days - automatic renewal did not happen"
    logger -t cert-expiry "$msg"
    echo "$(date -u +%FT%TZ) $msg" >> /var/log/cert-expiry.log
  fi
done
