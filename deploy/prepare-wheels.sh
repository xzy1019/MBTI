#!/bin/sh
# Run on a connected machine with Python 3.12 and pip before preparing an offline release.
set -eu
mkdir -p .offline/wheels
python3.12 -m pip download --platform manylinux_2_28_x86_64 --platform manylinux_2_17_x86_64 --implementation cp --python-version 312 --only-binary=:all: -r backend/requirements.lock -d .offline/wheels
