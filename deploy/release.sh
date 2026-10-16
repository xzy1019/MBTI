#!/bin/sh
# Usage: release.sh /opt/mbti-site/releases/RELEASE
set -eu
: "${1:?Provide the absolute prepared release directory}"
ATLAS_ROOT=${ATLAS_ROOT:-/opt/mbti-site}
ATLAS_RELEASE=$1
ATLAS_DOCKER="$ATLAS_ROOT/runtime/docker/docker"
test -f "$ATLAS_RELEASE/compose.yaml"
test -f "$ATLAS_ROOT/.env"
test -f "$ATLAS_RELEASE/frontend/dist/index.html"
test -d "$ATLAS_RELEASE/.offline/wheels"
export DOCKER_BUILDKIT=0
"$ATLAS_DOCKER" compose --project-directory "$ATLAS_RELEASE" --env-file "$ATLAS_ROOT/.env" config --quiet
"$ATLAS_DOCKER" compose --project-directory "$ATLAS_RELEASE" --env-file "$ATLAS_ROOT/.env" build
if [ -L "$ATLAS_ROOT/current" ]; then
    readlink "$ATLAS_ROOT/current" > "$ATLAS_ROOT/previous-release"
fi
ln -sfn "$ATLAS_RELEASE" "$ATLAS_ROOT/current.next"
mv -Tf "$ATLAS_ROOT/current.next" "$ATLAS_ROOT/current"
"$ATLAS_DOCKER" compose --project-directory "$ATLAS_ROOT/current" --env-file "$ATLAS_ROOT/.env" up -d --no-build --wait --wait-timeout 180
