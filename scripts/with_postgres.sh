#!/usr/bin/env bash
# Run a command against an ephemeral local PostgreSQL (ADR-030, plan P2-D13), offline.
#
#   scripts/with_postgres.sh <command...>
#
# If ENERGY_PLATFORM_DSN is already set the command runs against that server and nothing is
# started. Otherwise a fresh cluster is created with initdb in a scratch directory, started on a
# Unix socket only (no TCP), exported as ENERGY_PLATFORM_DSN and ENERGY_PLATFORM_TEST_DSN, and
# stopped afterwards. Makefile convention: the binaries missing while migrations exist is a
# failure, never a fake pass.
set -euo pipefail

if [ -n "${ENERGY_PLATFORM_DSN:-}" ]; then
  export ENERGY_PLATFORM_TEST_DSN="${ENERGY_PLATFORM_TEST_DSN:-$ENERGY_PLATFORM_DSN}"
  exec "$@"
fi

find_bindir() {
  if command -v pg_ctl >/dev/null 2>&1; then dirname "$(command -v pg_ctl)"; return; fi
  if command -v pg_config >/dev/null 2>&1; then pg_config --bindir; return; fi
  for d in /usr/lib/postgresql/*/bin /opt/homebrew/opt/postgresql*/bin /usr/local/opt/postgresql*/bin; do
    if [ -x "$d/pg_ctl" ]; then echo "$d"; fi
  done | sort -V | tail -1
}

BINDIR="$(find_bindir)"
if [ -z "$BINDIR" ] || [ ! -x "$BINDIR/initdb" ]; then
  echo "with_postgres: PostgreSQL binaries (initdb, pg_ctl) not found; install PostgreSQL >= 16" >&2
  echo "               or set ENERGY_PLATFORM_DSN to an existing server (ADR-030)" >&2
  exit 1
fi

DIR="$(mktemp -d "${TMPDIR:-/tmp}/energy-platform-pg.XXXXXX")"
# macOS mktemp paths can exceed the Unix-socket path limit; keep the socket dir short.
SOCKDIR="$(mktemp -d /tmp/ep-pg.XXXXXX)"
cleanup() {
  "$BINDIR/pg_ctl" -D "$DIR" -m fast stop >/dev/null 2>&1 || true
  rm -rf "$DIR" "$SOCKDIR"
}
trap cleanup EXIT

"$BINDIR/initdb" -D "$DIR" -U postgres --auth=trust --no-sync -E UTF8 >"$DIR.initdb.log" 2>&1 \
  || { cat "$DIR.initdb.log" >&2; exit 1; }
"$BINDIR/pg_ctl" -D "$DIR" -w -l "$DIR.server.log" \
  -o "-k $SOCKDIR -c listen_addresses='' -c fsync=off -c synchronous_commit=off" start >/dev/null \
  || { cat "$DIR.server.log" >&2; exit 1; }

export ENERGY_PLATFORM_DSN="postgresql:///postgres?host=$SOCKDIR&user=postgres"
export ENERGY_PLATFORM_TEST_DSN="$ENERGY_PLATFORM_DSN"
echo "with_postgres: $("$BINDIR/pg_ctl" --version) on $SOCKDIR" >&2
"$@"
