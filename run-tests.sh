#!/bin/sh
# Runs the tests inside the Home Assistant image (same Python and HA version).
set -e
cd "$(dirname "$0")"
docker run --rm -v "$(pwd -P)":/repo -w /repo --entrypoint sh \
  ghcr.io/home-assistant/home-assistant:stable -c '
    uv pip install -q --index-strategy unsafe-best-match -r requirements_test.txt >/dev/null 2>&1
    python3 -m pytest -q -p no:cacheprovider "$@"
  ' sh "$@"
