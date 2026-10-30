#!/usr/bin/env bash
set -eu

(
  cd /app/uis/website
  exec node node_modules/next/dist/bin/next "${NEXTJS_MODE:-start}" --hostname 0.0.0.0 --port "${WEBSITE_PORT:-3000}"
) &
website_pid=$!

(
  cd /app/uis/backoffice
  exec node node_modules/next/dist/bin/next "${NEXTJS_MODE:-start}" --hostname 0.0.0.0 --port "${BACKOFFICE_PORT:-3001}"
) &
backoffice_pid=$!

cleanup() {
  kill "$website_pid" "$backoffice_pid" 2>/dev/null || true
  wait "$website_pid" "$backoffice_pid" 2>/dev/null || true
}

trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

status=0
wait -n "$website_pid" "$backoffice_pid" || status=$?
exit "$status"