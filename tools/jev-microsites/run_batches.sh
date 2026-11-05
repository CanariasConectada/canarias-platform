#!/usr/bin/env bash
# Runs analyze.py task by task, batch by batch, committing after each pair.
# Checks free disk space every 5 batches (50 sites) and stops under 10 GB.
set -euo pipefail
cd "$(dirname "$0")"
REPO="$(git rev-parse --show-toplevel)"
N_BATCHES=$(python3 -c "import analyze;print(len(analyze.Context().batches()))")
check_disk() {
  avail_gb=$(df -BG --output=avail / | tail -1 | tr -dc '0-9')
  echo "disk free: ${avail_gb} GB"
  if [ "$avail_gb" -lt 10 ]; then
    echo "- $(date -u +%H:%M) UTC — PARADA: quedan ${avail_gb} GB libres (<10 GB)." >> /home/odoo/Pending/jev-work/PENDIENTE.md
    exit 2
  fi
}
LABEL=(x "reviews audit" "section 1 proposals" "image proposals")
for T in 1 2 3; do
  for ((B=0; B<N_BATCHES; B++)); do
    if (( B % 5 == 0 )); then check_disk; fi
    python3 analyze.py --task "$T" --batch "$B"
    SITES=$(python3 -c "import json;print(json.load(open('/home/odoo/Pending/jev-work/data/progress.json'))['batches']['$B']['sites'])")
    git -C "$REPO" add tools/jev-microsites/PROGRESO.md tools/jev-microsites/cambios.csv tools/jev-microsites/revision.csv 2>/dev/null || true
    if ! git -C "$REPO" diff --cached --quiet; then
      git -C "$REPO" commit -q -m "chore(jev-microsites): task ${T} batch $(printf %02d "$B") ${LABEL[$T]} (sites ${SITES})"
    fi
  done
done
echo "done. total Jev cost: $(python3 -c 'import jev_client;print(jev_client.total_cost())')"
