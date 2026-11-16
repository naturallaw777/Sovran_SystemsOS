# PostgreSQL major-version upgrades

This repository runs one shared PostgreSQL cluster for enabled services such as
Matrix Synapse and Nextcloud; other enabled or locally configured services may
also use it. A major-version upgrade affects **every database and role in that
cluster**, not just one application.

## Normal automatic path

Users do **not** need to run `initdb`, `pg_upgrade`, or other database migration
commands. When a Sovran_SystemsOS update changes the configured PostgreSQL major,
a pre-start gate inside `postgresql.service` runs before NixOS's ordinary
initialization code can create or start the target cluster. On an in-place
switch, systemd first stops the old PostgreSQL service; the gate then migrates
the offline source before the new server starts. On reboot, the gate runs before
the new server's first start.

The gate keeps the old PostgreSQL binaries available in the new system
closure for supported installed majors (PostgreSQL 14 and newer in the current
pin), checks compatibility with `pg_upgrade --check --copy`, initializes a
matching target cluster (including locale, encoding, and checksum settings),
and performs the copy-mode upgrade. It briefly starts the old cluster with a
private Unix socket and no TCP listener to read its actual locale settings,
then stops it before copying. Older source majors, unsupported locale providers,
or incompatible extensions stop safely rather than start an empty cluster.
`pg_upgrade --copy` retains the old data directory and never deletes it. The
automatic path expects the
standard versioned layout: the target directory ends in the configured major
(e.g. `/var/lib/postgresql/18`) and older numeric-major directories are siblings.
A custom root is fine if it keeps that layout and the PostgreSQL `postgres`
account can write in the parent directory; NixOS evaluation rejects a
non-versioned `dataDir` rather than risk starting an empty cluster beside an
undetected source. If a target-major cluster already exists without an unfinished
migration marker, it is treated as authoritative and is never overwritten.
Once the target server is up,
PostgreSQL setup updates extensions, runs
`vacuumdb --all --analyze-in-stages --missing-stats-only` followed by
`vacuumdb --all --analyze-only`, and only then allows Synapse and Nextcloud to
connect. Those client units stop with PostgreSQL on a restart and require the
setup unit before starting again. Any locally added PostgreSQL-consuming unit
must use the same `After=postgresql-setup.service` and
`Requires=postgresql-setup.service` ordering and stop/restart with
`postgresql.service`; otherwise it could reconnect before maintenance ends.

Copy mode needs available disk space of roughly the old cluster's size plus
10% and 1 GiB of headroom. If compatibility, space, or another safety check
fails, the migration stops before PostgreSQL starts; the old cluster is
preserved so the system can be booted back into its previous generation or the
problem can be investigated. Do not remove the old cluster until the new system
and all databases have been verified and a separate backup is available.

To inspect progress or a failure (not as a routine migration step):

```bash
sudo systemctl status postgresql.service
sudo journalctl -u postgresql.service -b
sudo cat /var/lib/postgresql/.sovran-postgresql-upgrade-18.state
sudo tail -n 200 /var/lib/postgresql/.sovran-postgresql-upgrade-18.log
sudo journalctl -u postgresql-setup.service -b
```

With the repository's default data directory, replace `18` with the target
major configured on the machine. If a local configuration overrides
`services.postgresql.dataDir`, the state and log files are stored next to that
data directory instead. The migration runs during PostgreSQL's pre-start, so
its progress appears in the `postgresql.service` journal and dedicated log; the
state file is authoritative. The state moves from `IN_PROGRESS` to `MIGRATED`,
then through extension/statistics maintenance to `COMPLETE`. A failed or
interrupted copy is retried automatically from the untouched source cluster on
a subsequent activation or reboot.

## Version policy

- `configuration.nix` pins `services.postgresql.package` to
  `pkgs.postgresql_18`. Keep the major explicit: do not rely on the default
  inferred from `system.stateVersion` or on the moving `pkgs.postgresql` alias.
- Keep `system.stateVersion = "22.05"` unchanged. It is a NixOS compatibility
  baseline, not a PostgreSQL upgrade control. In the repository's pinned
  nixpkgs module, that value would otherwise select PostgreSQL 14.
- Nixpkgs updates within PostgreSQL 18 (for example, 18.6 to 18.7) do not need a
  major data migration. Changing the configured major version does and invokes
  the automatic path above. Schedule major-version changes before the selected
  major reaches end of support; a `flake.lock` makes builds reproducible but
  does not make an EOL package a safe long-term choice.

## Manual recovery only: preflight before intervention

The command-by-command procedure below is **not part of a routine Sovran update**.
Use it only when the PostgreSQL pre-start migration reports an unsupported
cluster or failure and an administrator has decided on manual recovery. Do not
run manual commands while `postgresql.service` is starting or running. Prefer
booting the previous system generation first; keep the source cluster untouched.

1. **Back up the database and test that the backup is restorable.** Prefer the
   Sovran Hub full backup (which creates a PostgreSQL logical dump) or another
   PostgreSQL-aware backup stored off the system disk. A live `rsnapshot`/`rsync`
   copy of `/var/lib/postgresql` alone is not a substitute for a database-aware
   backup.
2. Record the server version, actual data directory, and each database's
   encoding and locale while PostgreSQL is running:

   ```bash
   sudo -u postgres psql -Atc 'SHOW server_version'
   sudo -u postgres psql -Atc 'SHOW data_directory'
   sudo -u postgres psql -c \
     'SELECT datname, pg_encoding_to_char(encoding), datcollate, datctype FROM pg_database ORDER BY 1'
   ```

3. Inventory all databases, their sizes, and current clients. Check installed
   extensions in every database and make sure the matching PostgreSQL 18
   extension packages are available. Stop *all* services that write to this
   cluster for the migration—not just the service whose database looks largest.
4. Check free space. Copy mode needs room for a second data directory while
   preserving the old one. Before changing system generations, record the old
   binary directory (the command prints a store path ending in `/bin`):

   ```bash
   OLD_BIN="$(dirname "$(readlink -f /run/current-system/sw/bin/postgres)")"
   printf '%s\n' "$OLD_BIN"
   ```

   Keep the old system generation until the migration is validated; Nix garbage
   collection can remove its PostgreSQL binaries later.
5. Set the new package in the NixOS configuration and **build, do not switch**:

   ```bash
   sudo nixos-rebuild build --flake .#nixos
   ```

   With this repository's default `dataDir` (unless a local configuration
   overrides it), PostgreSQL 18 uses `/var/lib/postgresql/18`; the old
   versioned directory remains `/var/lib/postgresql/<old-major>`. Building a
   generation alone does not run migration; the automatic pre-start gate runs
   when that generation is activated by switch or boot.

## Manual recovery only: match the target cluster

The repository config sets UTF-8 and the configured system locale in
`services.postgresql.initdbArgs` for **new clusters**. PostgreSQL 18 enables data
checksums by default. For `pg_upgrade`, the new cluster must match the old
cluster's encoding, locale settings, bootstrap superuser, locale provider where
applicable, and checksum state. Older clusters often have checksums disabled.

During the maintenance window, after stopping all database clients and stopping
`postgresql.service` cleanly, inspect the old cluster offline with its old
`pg_controldata` binary:

```bash
OLD_DATA=/var/lib/postgresql/14  # replace 14 with the recorded old data directory
"$OLD_BIN/pg_controldata" "$OLD_DATA" | grep -i 'Data page checksum version'
```

The `Data page checksum version` is `0` when checksums are off and `1` when they
are on. Also use the recorded database locale/encoding information above to
choose the locale for the new cluster. For example, the repository's default
system locale is `en_US.UTF-8`, but use the old cluster's actual setting rather
than assuming it matches today's configuration.

Resolve the PostgreSQL 18 binary directory from the build result. If the result
is in the current checkout:

```bash
NEW_BIN="$(dirname "$(readlink -f ./result/sw/bin/pg_upgrade)")"
printf '%s\n' "$NEW_BIN"
```

If the result is under `/root`, resolve it with root privileges (for example,
`sudo readlink -f /root/result/sw/bin/pg_upgrade`) and use the containing
`/nix/store/.../bin` directory. Do not ask the `postgres` user to traverse a
root-only build-result path; invoke binaries by their resolved store paths.

Before initializing the target, inspect it. If the new data directory already
contains `PG_VERSION` or any unexpected files, stop and investigate; do not
reinitialize or delete it blindly. For a fresh, unused target directory, run
PostgreSQL 18's `initdb` once as `postgres`, matching the old cluster settings.
For the example 14-to-18 layout:

```bash
OLD_DATA=/var/lib/postgresql/14       # replace with the recorded old path
NEW_DATA=/var/lib/postgresql/18       # replace if dataDir is customized
CLUSTER_ENCODING=UTF8                 # use the old cluster's actual encoding
CLUSTER_LOCALE=en_US.UTF-8            # use the old cluster's actual locale
CHECKSUM_VERSION=0                    # set to the pg_controldata value: 0 or 1
CHECKSUM_ARGS=()
if [[ "$CHECKSUM_VERSION" == "0" ]]; then
  CHECKSUM_ARGS=(--no-data-checksums)
elif [[ "$CHECKSUM_VERSION" != "1" ]]; then
  echo "Unexpected checksum version; stop and investigate" >&2
  exit 1
fi
sudo install -d -o postgres -g postgres -m 0700 "$NEW_DATA"
sudo -u postgres "$NEW_BIN/initdb" \
  --pgdata="$NEW_DATA" \
  --username=postgres \
  --encoding="$CLUSTER_ENCODING" \
  --locale="$CLUSTER_LOCALE" \
  "${CHECKSUM_ARGS[@]}"
```

Set `CHECKSUM_VERSION` from the actual old cluster. For value `0`, this adds
`--no-data-checksums`; for value `1`, PostgreSQL 18's default remains enabled.
Do not add `--no-data-checksums` to the repository's normal fresh-cluster
configuration merely to migrate one older installation. If the source used
non-default initdb options or a non-default locale provider, account for those
as well and let `pg_upgrade --check` verify compatibility.

Keep database-specific collations too. For example, a Synapse or Nextcloud
database created with `LC_COLLATE = 'C'` can coexist with a cluster initialized
with `en_US.UTF-8`; the per-database settings are preserved by `pg_upgrade`.

## Manual recovery only: run `pg_upgrade --copy`

`pg_upgrade` moves the complete cluster. Copy mode needs additional disk space
but leaves the old data files intact. `--link` is faster and uses less space,
but once the new cluster starts the old cluster is not a usable rollback copy.
`--clone` only works on supported reflink filesystems.

1. Stop every enabled client service that writes to PostgreSQL, using its real
   systemd unit name on this machine, then stop the database cleanly. Keep all
   clients stopped through the upgrade and post-upgrade database maintenance:

   ```bash
   sudo systemctl stop postgresql.service
   ```

   If any client unit starts during the NixOS switch, stop it again before
   running extension or statistics maintenance.
2. Confirm the old cluster is offline, inspect its checksum setting as above,
   and initialize the new versioned data directory as described above.
3. From a directory writable by `postgres` (for example the new data directory),
   run the compatibility check with the absolute paths recorded above. Keep
   these variables set in the same shell; pass them explicitly to the `postgres`
   user so the root-only build-result symlink is not traversed:

   ```bash
   sudo -u postgres env \
     OLD_DATA="$OLD_DATA" NEW_DATA="$NEW_DATA" \
     OLD_BIN="$OLD_BIN" NEW_BIN="$NEW_BIN" \
     bash -c '
       cd "$NEW_DATA"
       exec "$NEW_BIN/pg_upgrade" \
         --old-datadir "$OLD_DATA" \
         --new-datadir "$NEW_DATA" \
         --old-bindir "$OLD_BIN" \
         --new-bindir "$NEW_BIN" \
         --check --copy
     '
   ```

4. Only if the check reports that the clusters are compatible, run the same
   command again without `--check` and with `--copy` retained. If it fails,
   stop and resolve the reported issue; do not delete or alter the old cluster.
5. Before the new server is allowed to start, mark the manually completed
   `pg_upgrade` so the automatic pre-start gate will preserve the target and
   let PostgreSQL setup run its normal extension/statistics maintenance. Use the
   state-file location reported in the PostgreSQL journal; with the default data
   directory and target PostgreSQL 18 it is:

   ```bash
   sudo -u postgres sh -c 'printf "%s\n" MIGRATED > /var/lib/postgresql/.sovran-postgresql-upgrade-18.state'
   ```

   This marker is specifically for an independently completed manual copy. Do
   not set it if `pg_upgrade` did not finish successfully.
6. Switch to the built NixOS generation. PostgreSQL setup will apply
   `update_extensions.sql` (when generated) and run both analysis passes before
   Synapse, Nextcloud, and other configured clients are allowed to connect:

   ```bash
   sudo nixos-rebuild switch --flake .#nixos
   sudo systemctl is-active postgresql.service
   sudo systemctl is-active postgresql-setup.service
   sudo -u postgres psql -Atc 'SHOW server_version'
   sudo -u postgres psql -Atc 'SHOW data_directory'
   sudo cat /var/lib/postgresql/.sovran-postgresql-upgrade-18.state
   ```

   Confirm PostgreSQL reports major 18, the data directory is the expected new
   path, and the state reaches `COMPLETE`. If setup fails, inspect
   `journalctl -u postgresql-setup.service -b`; dependent services remain held
   until setup succeeds.
7. After maintenance completes, validate every enabled dependent service
   (including Synapse, Nextcloud, and any locally configured clients): confirm
   service health, check application/database logs, and exercise the relevant
   application functions. Also check `sudo systemctl --failed --no-pager` and
   verify the expected databases and extensions.
8. Keep the old data directory and a tested backup until the new cluster and all
   dependent services have been validated. **Do not run `delete_old_cluster.sh`
   immediately.** Once applications write to the new cluster, the old copied
   cluster is stale, not a current rollback point. Keep the old NixOS generation
   until its binaries are no longer needed.

The old/new version numbers, binary store paths, checksum flag, locale, and
service list vary by machine. Do not copy example paths or a checksum choice
without checking the installed cluster. A build alone does not activate the
new service; a normal switch or boot runs the automatic migration gate. These
manual recovery commands bypass its state machine, which is why the `MIGRATED`
marker above must be written only after a successful manual `pg_upgrade`.

## Separate authentication follow-up

The current base configuration uses PostgreSQL `trust` rules for local socket
and loopback connections. This guide does not change authentication because
changing it during a database migration can lock out services. Review those
rules separately: `trust` lets a local client claim a database role without
proving that identity, so plan a least-privilege authentication change as its
own tested maintenance task.
