#!/usr/bin/env bash
# Invoked as postgres from postgresql.service's preStart hook, after any old
# service instance has stopped and before NixOS's normal initdb preStart. The
# old cluster is never modified by pg_upgrade --copy; interrupted attempts are
# safely restarted from that source on the next activation or boot.
set -Eeuo pipefail
umask 077
export LC_ALL=C

: "${SOVRAN_PG_TARGET_MAJOR:?missing target PostgreSQL major}"
: "${SOVRAN_PG_DATA_DIR:?missing target data directory}"
: "${SOVRAN_PG_DATA_ROOT:?missing versioned data-directory root}"
: "${SOVRAN_PG_NEW_BIN:?missing target PostgreSQL binaries}"
: "${SOVRAN_PG_STATE_FILE:?missing migration state path}"
: "${SOVRAN_PG_LOG_FILE:?missing migration log path}"

TARGET_MAJOR="$SOVRAN_PG_TARGET_MAJOR"
TARGET_DATA="$SOVRAN_PG_DATA_DIR"
DATA_ROOT="$SOVRAN_PG_DATA_ROOT"
NEW_BIN="$SOVRAN_PG_NEW_BIN"
STATE_FILE="$SOVRAN_PG_STATE_FILE"
LOG_FILE="$SOVRAN_PG_LOG_FILE"

log() {
  printf '[%s] %s\n' "$(date --iso-8601=seconds)" "$*"
}

die() {
  log "ERROR: $*"
  exit 1
}

write_state() {
  local value="$1"
  local tmp="${STATE_FILE}.tmp.$$"
  printf '%s\n' "$value" > "$tmp"
  mv -f -- "$tmp" "$STATE_FILE"
}

MIGRATION_STARTED=0
mark_failed_state() {
  local rc="$1"
  if (( rc != 0 && MIGRATION_STARTED )); then
    write_state FAILED || true
  fi
}
trap 'rc=$?; mark_failed_state "$rc"' EXIT

# A fresh installation has no old versioned data directory; let the normal
# NixOS postgresql.service initdb path create its first cluster.
if [[ ! -d "$DATA_ROOT" ]]; then
  log "No PostgreSQL data root yet; nothing to migrate."
  exit 0
fi
[[ ! -L "$TARGET_DATA" ]] || die "target data directory is a symlink; refusing to migrate through it"

# Pick the newest older cluster in the standard versioned layout. Ignore
# snapshots and temporary names (for example 18.checksums-on).
SOURCE_DATA=""
SOURCE_MAJOR=0
NEWER_DATA=""
shopt -s nullglob
for candidate in "$DATA_ROOT"/[0-9]*; do
  [[ -d "$candidate" && -f "$candidate/PG_VERSION" ]] || continue
  base="${candidate##*/}"
  [[ "$base" =~ ^[0-9]+$ ]] || continue
  version="$(<"$candidate/PG_VERSION")"
  [[ "$version" =~ ^[0-9]+$ && "$version" == "$base" ]] || continue
  [[ "$candidate" == "$TARGET_DATA" ]] && continue
  if (( version > TARGET_MAJOR )); then
    NEWER_DATA="$candidate"
  elif (( version < TARGET_MAJOR && version > SOURCE_MAJOR )); then
    SOURCE_DATA="$candidate"
    SOURCE_MAJOR="$version"
  fi
done

STATE=""
if [[ -f "$STATE_FILE" ]]; then
  STATE="$(<"$STATE_FILE")"
fi

TARGET_VERSION=""
if [[ -f "$TARGET_DATA/PG_VERSION" ]]; then
  TARGET_VERSION="$(<"$TARGET_DATA/PG_VERSION")"
fi

if [[ "$TARGET_VERSION" == "$TARGET_MAJOR" ]]; then
  case "$STATE" in
    IN_PROGRESS|FAILED)
      # The service never started the target cluster while this marker was set.
      # The common retry block below removes only this incomplete target copy.
      [[ -n "$SOURCE_DATA" ]] || die "interrupted upgrade has no source cluster to retry from"
      ;;
    MIGRATED|EXTENSIONS_DONE|COMPLETE|"")
      log "PostgreSQL $TARGET_MAJOR data directory is already initialized; no migration needed."
      exit 0
      ;;
    *)
      die "unrecognized migration state '$STATE'; preserving all data directories"
      ;;
  esac
elif [[ -n "$TARGET_VERSION" ]]; then
  die "target path $TARGET_DATA contains PostgreSQL $TARGET_VERSION, expected $TARGET_MAJOR; refusing an in-place downgrade or overwrite"
fi

# initdb can fail after creating files but before writing PG_VERSION. Treat any
# non-empty target as disposable only when our own unfinished state proves it
# was created by this copy-mode attempt and the untouched source is available.
if [[ "$STATE" == "IN_PROGRESS" || "$STATE" == "FAILED" ]] && [[ -e "$TARGET_DATA" ]]; then
  [[ -n "$SOURCE_DATA" ]] || die "incomplete migration state exists but no old source was found; preserving target data"
  [[ ! -L "$TARGET_DATA" ]] || die "target data directory is a symlink; refusing to remove it"
  [[ -d "$TARGET_DATA" ]] || die "incomplete target path is not a directory; refusing to remove it"
  log "Found an incomplete target from a previous copy-mode attempt; rebuilding it from the untouched source."
  rm -rf -- "$TARGET_DATA"
fi

if [[ -n "$NEWER_DATA" ]]; then
  die "found newer cluster $NEWER_DATA; automatic downgrade to PostgreSQL $TARGET_MAJOR is not supported"
fi

if [[ -z "$SOURCE_DATA" ]]; then
  if [[ -n "$STATE" ]]; then
    die "migration state '$STATE' exists but no older versioned source cluster was found"
  fi
  # If the target is absent/empty this is an ordinary fresh cluster.
  if [[ -e "$TARGET_DATA" ]] && [[ -n "$(find "$TARGET_DATA" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
    die "target directory $TARGET_DATA is non-empty but has no PG_VERSION; refusing to initialize over it"
  fi
  log "No older versioned cluster found; no migration needed."
  exit 0
fi

# Re-enter the migration only for a known in-progress marker. An unexpected
# pre-existing target is never deleted.
if [[ -e "$TARGET_DATA" && "$STATE" != "IN_PROGRESS" && "$STATE" != "FAILED" ]]; then
  [[ ! -L "$TARGET_DATA" ]] || die "target data directory is a symlink; refusing to use it"
  if [[ -n "$(find "$TARGET_DATA" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
    die "target directory $TARGET_DATA already contains files; refusing to initialize over them"
  fi
fi

mkdir -p -- "${LOG_FILE%/*}"
: >> "$LOG_FILE"
exec > >(tee -a "$LOG_FILE") 2>&1
write_state IN_PROGRESS
MIGRATION_STARTED=1

log "Automatic PostgreSQL major upgrade: $SOURCE_MAJOR -> $TARGET_MAJOR"
log "Source: $SOURCE_DATA"
log "Target: $TARGET_DATA"
log "Mode: pg_upgrade --check --copy, then pg_upgrade --copy"

OLD_BIN_VAR="SOVRAN_PG_OLD_BIN_${SOURCE_MAJOR}"
OLD_BIN="${!OLD_BIN_VAR:-}"
[[ -n "$OLD_BIN" ]] || die "no PostgreSQL $SOURCE_MAJOR upgrade binaries are available in this system generation"
[[ -x "$OLD_BIN/pg_controldata" && -x "$OLD_BIN/pg_ctl" && -x "$OLD_BIN/psql" ]] \
  || die "the PostgreSQL $SOURCE_MAJOR binary directory is incomplete: $OLD_BIN"
[[ -x "$NEW_BIN/initdb" && -x "$NEW_BIN/pg_upgrade" ]] \
  || die "the target PostgreSQL $TARGET_MAJOR binaries are incomplete: $NEW_BIN"

# Leave headroom for WAL and temporary files rather than starting a copy that
# is likely to fill the system disk. The source cluster remains untouched.
source_kb="$(du -sk -- "$SOURCE_DATA" | awk '{print $1}')"
target_parent="${TARGET_DATA%/*}"
[[ -d "$target_parent" ]] || die "target parent $target_parent does not exist"
available_kb="$(df -Pk -- "$target_parent" | awk 'END {print $4}')"
required_kb=$((source_kb + source_kb / 10 + 1048576)) # source size + 10% + 1 GiB
if (( available_kb < required_kb )); then
  die "not enough free space for copy mode (available ${available_kb} KiB; require about ${required_kb} KiB)"
fi

# Read template1's actual encoding and default collations from the source
# catalog. Use a private Unix socket and no TCP listener so no application can
# attach to this temporary read-only-purpose inspection instance.
SOCKET_DIR="$(mktemp -d --tmpdir="$DATA_ROOT" ".sovran-pg-upgrade-${TARGET_MAJOR}.socket.XXXXXX")"
HBA_FILE="$SOCKET_DIR/pg_hba.conf"
OLD_SERVER_LOG="$DATA_ROOT/.sovran-pg-upgrade-${TARGET_MAJOR}.old-server.log"
SOCKET_PORT=55432
chmod 0700 "$SOCKET_DIR"
printf 'local all all trust\n' > "$HBA_FILE"
OLD_SERVER_START_ATTEMPTED=0
stop_old_server() {
  # Never stop a pre-existing server we did not start. The systemd ordering
  # requires the old service to be offline before this unit runs; if pg_ctl's
  # start attempt partially succeeds, clean up only that attempt here.
  if (( OLD_SERVER_START_ATTEMPTED )) && "$OLD_BIN/pg_ctl" -D "$SOURCE_DATA" status >/dev/null 2>&1; then
    "$OLD_BIN/pg_ctl" -D "$SOURCE_DATA" -m fast -w stop >> "$LOG_FILE" 2>&1 || true
  fi
  OLD_SERVER_START_ATTEMPTED=0
}
cleanup_inspection_files() {
  stop_old_server
  rm -rf -- "$SOCKET_DIR"
  rm -f -- "$HBA_FILE"
}
on_exit_with_inspection() {
  local rc=$?
  trap - EXIT
  cleanup_inspection_files
  mark_failed_state "$rc"
  exit "$rc"
}
trap on_exit_with_inspection EXIT

if "$OLD_BIN/pg_ctl" -D "$SOURCE_DATA" status >/dev/null 2>&1; then
  die "the source cluster is already running; refusing to inspect or stop an active server"
fi
OLD_SERVER_START_ATTEMPTED=1
if ! "$OLD_BIN/pg_ctl" -D "$SOURCE_DATA" \
    -l "$OLD_SERVER_LOG" \
    -o "-c listen_addresses='' -c unix_socket_directories='$SOCKET_DIR' -c port=$SOCKET_PORT -c hba_file='$HBA_FILE'" \
    -w start; then
  die "could not start the old cluster briefly to read its locale/encoding; source data was not modified by pg_upgrade"
fi

locale_row="$("$OLD_BIN/psql" -X -h "$SOCKET_DIR" -p "$SOCKET_PORT" -U postgres -d template1 -A -t -F '|' \
  -c "SELECT pg_encoding_to_char(encoding), datcollate, datctype FROM pg_database WHERE datname = 'template1'")"
IFS='|' read -r CLUSTER_ENCODING CLUSTER_COLLATE CLUSTER_CTYPE <<< "$locale_row"
[[ -n "$CLUSTER_ENCODING" && -n "$CLUSTER_COLLATE" && -n "$CLUSTER_CTYPE" ]] \
  || die "could not read template1 encoding/collation from the old cluster"

# PostgreSQL 15+ records the locale provider. This automatic path currently
# supports libc (the provider used by Sovran's PostgreSQL 14 clusters and by
# this configuration); fail safely rather than silently changing providers.
if (( SOURCE_MAJOR >= 15 )); then
  LOCALE_PROVIDER="$("$OLD_BIN/psql" -X -h "$SOCKET_DIR" -p "$SOCKET_PORT" -U postgres -d template1 -A -t \
    -c "SELECT datlocprovider FROM pg_database WHERE datname = 'template1'")"
  [[ "$LOCALE_PROVIDER" == "c" ]] \
    || die "source locale provider '$LOCALE_PROVIDER' is not supported by the automatic migration; source cluster is preserved"
fi

stop_old_server
cleanup_inspection_files
trap 'rc=$?; mark_failed_state "$rc"' EXIT

checksum_version="$("$OLD_BIN/pg_controldata" "$SOURCE_DATA" | awk -F: '/^Data page checksum version:/ { gsub(/[[:space:]]/, "", $2); print $2; exit }')"
case "$checksum_version" in
  0) log "Source checksums are off; initializing target with --no-data-checksums." ;;
  1) log "Source checksums are on; initializing target with --data-checksums." ;;
  *) die "could not determine source checksum version (reported '$checksum_version')" ;;
esac

initdb_args=()
initdb_arg_count="${SOVRAN_PG_INITDB_ARG_COUNT:-0}"
[[ "$initdb_arg_count" =~ ^[0-9]+$ ]] || die "invalid initdb argument count"
for ((i = 0; i < initdb_arg_count; i++)); do
  arg_name="SOVRAN_PG_INITDB_ARG_${i}"
  initdb_args+=("${!arg_name-}")
done
# Source catalog settings override fresh-install defaults for this one-time
# target initialization. Strip any configured checksum choice before matching
# the old cluster explicitly.
filtered_initdb_args=()
skip_initdb_value=0
for arg in "${initdb_args[@]}"; do
  if (( skip_initdb_value )); then
    skip_initdb_value=0
    continue
  fi
  case "$arg" in
    --data-checksums|--no-data-checksums|--no-locale) ;;
    --encoding=*|--locale=*|--lc-collate=*|--lc-ctype=*|--locale-provider=*|--icu-locale=*|-E?*) ;;
    --encoding|-E|--locale|--lc-collate|--lc-ctype|--locale-provider|--icu-locale)
      skip_initdb_value=1
      ;;
    *) filtered_initdb_args+=("$arg") ;;
  esac
done
initdb_args=("${filtered_initdb_args[@]}" \
  "--encoding=$CLUSTER_ENCODING" \
  "--lc-collate=$CLUSTER_COLLATE" \
  "--lc-ctype=$CLUSTER_CTYPE")
# PostgreSQL 14 does not recognize --locale-provider; PostgreSQL 15+
# supports it. Older source clusters have only the libc provider, while the
# explicit provider setting is needed only when that target option exists.
if (( TARGET_MAJOR >= 15 )); then
  initdb_args+=(--locale-provider=libc)
fi
if [[ "$checksum_version" == "0" ]]; then
  initdb_args+=(--no-data-checksums)
else
  initdb_args+=(--data-checksums)
fi

mkdir -m 0700 -p -- "$TARGET_DATA"
"$NEW_BIN/initdb" -D "$TARGET_DATA" -U postgres "${initdb_args[@]}"

# Run the check and the real migration with the PostgreSQL OS account (this
# unit already runs as postgres) and from a writable target directory.
cd "$TARGET_DATA"
"$NEW_BIN/pg_upgrade" \
  --old-datadir "$SOURCE_DATA" \
  --new-datadir "$TARGET_DATA" \
  --old-bindir "$OLD_BIN" \
  --new-bindir "$NEW_BIN" \
  --check --copy
"$NEW_BIN/pg_upgrade" \
  --old-datadir "$SOURCE_DATA" \
  --new-datadir "$TARGET_DATA" \
  --old-bindir "$OLD_BIN" \
  --new-bindir "$NEW_BIN" \
  --copy

write_state MIGRATED
MIGRATION_STARTED=0
log "pg_upgrade --copy completed. PostgreSQL $TARGET_MAJOR post-start extension/statistics maintenance is pending."
