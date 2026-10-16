#!/bin/sh
# Explicit operator action: replaces application database content.
set -eu
: "${1:?Usage: restore.sh /absolute/path/to/atlas.dump}"
ATLAS_ROOT=${ATLAS_ROOT:-/opt/mbti-site}
ATLAS_DOCKER="$ATLAS_ROOT/runtime/docker/docker"
"$ATLAS_DOCKER" compose --project-directory "$ATLAS_ROOT/current" --env-file "$ATLAS_ROOT/.env" stop api web
"$ATLAS_DOCKER" compose --project-directory "$ATLAS_ROOT/current" --env-file "$ATLAS_ROOT/.env" exec -T db pg_restore -U atlas -d atlas --clean --if-exists --no-owner --exit-on-error < "$1"
"$ATLAS_DOCKER" compose --project-directory "$ATLAS_ROOT/current" --env-file "$ATLAS_ROOT/.env" up -d --no-build --wait
