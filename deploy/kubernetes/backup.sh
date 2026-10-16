#!/usr/bin/env bash
set -euo pipefail
export KUBECONFIG=${KUBECONFIG:-/etc/kubernetes/admin.conf}
ATLAS_ROOT=${ATLAS_ROOT:-/opt/mbti-site}
umask 077
exec 9>/run/mbti-k8s-backup.lock
flock -n 9 || { echo 'MBTI backup already running.' >&2; exit 1; }
mkdir -p "$ATLAS_ROOT/backups"
ATLAS_BACKUP="$ATLAS_ROOT/backups/atlas-$(date -u +%Y%m%dT%H%M%SZ).dump"
trap 'rm -f "$ATLAS_BACKUP.partial"' EXIT
kubectl -n mbti-site exec deployment/postgres -- pg_dump -U atlas -d atlas -Fc \
  --exclude-table-data=resume_sessions --exclude-table-data=admin_sessions > "$ATLAS_BACKUP.partial"
test -s "$ATLAS_BACKUP.partial"
mv "$ATLAS_BACKUP.partial" "$ATLAS_BACKUP"
printf '%s\n' "$ATLAS_BACKUP"
