#!/bin/sh
set -eu
ATLAS_ROOT=${ATLAS_ROOT:-/opt/mbti-site}
export ATLAS_ROOT
umask 077
mkdir -p "$ATLAS_ROOT/backups"
ATLAS_BACKUP="$ATLAS_ROOT/backups/atlas-$(date -u +%Y%m%dT%H%M%SZ).dump"
"$ATLAS_ROOT/runtime/docker/docker" compose --project-directory "$ATLAS_ROOT/current" --env-file "$ATLAS_ROOT/.env" exec -T db pg_dump -U atlas -d atlas -Fc --exclude-table-data=resume_sessions --exclude-table-data=admin_sessions > "$ATLAS_BACKUP.partial"
mv "$ATLAS_BACKUP.partial" "$ATLAS_BACKUP"
printf '%s\n' "$ATLAS_BACKUP"
