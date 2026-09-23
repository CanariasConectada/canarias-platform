#!/usr/bin/env bash
# Run aplicar.py or revertir.py with the production credentials from the
# private env file, without printing them.
#   bash con_credenciales.sh aplicar.py [flags...]
#   bash con_credenciales.sh revertir.py [flags...]
set -euo pipefail
ENV_FILE="${JEV_ENV_FILE:-/home/odoo/Pending/jev-work/.env.jev}"
cd "$(dirname "$0")"
case "${1:-}" in
  aplicar.py|revertir.py) ;;
  *) echo "usage: $0 aplicar.py|revertir.py [flags...]" >&2; exit 2 ;;
esac
[ -r "$ENV_FILE" ] || { echo "missing $ENV_FILE" >&2; exit 2; }
perm=$(stat -c %a "$ENV_FILE")
[ "$perm" = "600" ] || { echo "$ENV_FILE must be chmod 600 (is $perm)" >&2; exit 2; }
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a
if [ -z "${ODOO_LOGIN:-}" ] || [ -z "${ODOO_PASSWORD:-}" ]; then
  echo "ODOO_LOGIN / ODOO_PASSWORD are empty in $ENV_FILE" >&2
  exit 2
fi
script="$1"
shift
exec python3 "$script" --url "$ODOO_URL" --db "$ODOO_DB" "$@"
