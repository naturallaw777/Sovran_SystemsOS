{ config, lib, pkgs, ... }:

let
  cfg = config.services.postgresql;
  targetMajor = cfg.package.psqlSchema;
  targetMajorNumber = builtins.fromJSON targetMajor;
  dataDir = toString cfg.dataDir;
  dataRoot = builtins.dirOf dataDir;
  stateFile = "${dataRoot}/.sovran-postgresql-upgrade-${targetMajor}.state";
  logFile = "${dataRoot}/.sovran-postgresql-upgrade-${targetMajor}.log";

  # Keep the old major-version tools in this system closure so a first boot
  # does not depend on binaries surviving in a previous generation or on Nix
  # garbage-collection timing. Include every installed numeric major >= 14
  # that is older than the configured target.
  oldPackageNames = builtins.filter
    (name:
      let match = builtins.match "postgresql_([0-9]+)" name;
      in match != null
        && builtins.fromJSON (builtins.head match) >= 14
        && builtins.fromJSON (builtins.head match) < targetMajorNumber
    )
    (builtins.attrNames pkgs);

  oldPackages = map
    (name:
      let
        match = builtins.match "postgresql_([0-9]+)" name;
        major = builtins.head match;
        basePackage = builtins.getAttr name pkgs;
        jitPackage = if cfg.enableJIT then basePackage.withJIT else basePackage.withoutJIT;
        finalPackage = jitPackage.withPackages cfg.extensions;
      in
      {
        inherit major;
        bin = "${finalPackage}/bin";
      }
    )
    oldPackageNames;

  oldBinaryEnvironment = builtins.listToAttrs (map
    (package: {
      name = "SOVRAN_PG_OLD_BIN_${package.major}";
      value = package.bin;
    })
    oldPackages);

  initdbArgumentEnvironment = builtins.listToAttrs (builtins.genList
    (index: {
      name = "SOVRAN_PG_INITDB_ARG_${toString index}";
      value = builtins.elemAt cfg.initdbArgs index;
    })
    (builtins.length cfg.initdbArgs));

  migrationEnvironment = {
    SOVRAN_PG_TARGET_MAJOR = targetMajor;
    SOVRAN_PG_DATA_DIR = dataDir;
    SOVRAN_PG_DATA_ROOT = dataRoot;
    SOVRAN_PG_NEW_BIN = "${cfg.finalPackage}/bin";
    SOVRAN_PG_STATE_FILE = stateFile;
    SOVRAN_PG_LOG_FILE = logFile;
    SOVRAN_PG_INITDB_ARG_COUNT = toString (builtins.length cfg.initdbArgs);
  } // oldBinaryEnvironment // initdbArgumentEnvironment;

  postUpgradeMaintenance = ''
    set -euo pipefail
    TARGET_MAJOR=${lib.escapeShellArg targetMajor}
    TARGET_DATA_DIR=${lib.escapeShellArg dataDir}
    STATE_FILE=${lib.escapeShellArg stateFile}
    UPDATE_SQL=${lib.escapeShellArg "${dataDir}/update_extensions.sql"}

    # Never apply target-major extension SQL to an old or alternate server if
    # this setup unit is invoked outside the normal PostgreSQL restart order.
    server_major="$(psql -X -qAt -v ON_ERROR_STOP=1 -d postgres -c "SELECT current_setting('server_version_num')::integer / 10000")"
    server_data_dir="$(psql -X -qAt -v ON_ERROR_STOP=1 -d postgres -c 'SHOW data_directory')"
    server_data_dir_real="$(readlink -f -- "$server_data_dir")"
    target_data_dir_real="$(readlink -f -- "$TARGET_DATA_DIR")"
    if [[ "$server_major" != "$TARGET_MAJOR" || "$server_data_dir_real" != "$target_data_dir_real" ]]; then
      echo "Skipping PostgreSQL upgrade maintenance: server/data directory do not match the configured target."
      exit 0
    fi

    write_state() {
      local tmp="''${STATE_FILE}.tmp.$$"
      printf '%s\n' "$1" > "$tmp"
      mv -f -- "$tmp" "$STATE_FILE"
    }

    state="$(cat "$STATE_FILE" 2>/dev/null || true)"
    while :; do
      case "$state" in
        MIGRATED)
          echo "PostgreSQL major upgrade: updating extensions"
          if [ -f "$UPDATE_SQL" ]; then
            psql -X -v ON_ERROR_STOP=1 -f "$UPDATE_SQL"
          else
            echo "No update_extensions.sql was generated; skipping extension updates"
          fi
          write_state EXTENSIONS_DONE
          ;;
        EXTENSIONS_DONE)
          echo "PostgreSQL major upgrade: analyzing all databases"
          vacuumdb --all --analyze-in-stages --missing-stats-only
          vacuumdb --all --analyze-only
          write_state COMPLETE
          ;;
        COMPLETE|"")
          exit 0
          ;;
        IN_PROGRESS)
          echo "ERROR: PostgreSQL migration is incomplete; refusing to start dependent services" >&2
          exit 1
          ;;
        *)
          echo "ERROR: unrecognized PostgreSQL migration state '$state'" >&2
          exit 1
          ;;
      esac
      state="$(cat "$STATE_FILE" 2>/dev/null || true)"
    done
  '';
in
lib.mkIf (cfg.enable && targetMajorNumber >= 14) {
  assertions = [
    {
      assertion = builtins.baseNameOf dataDir == targetMajor;
      message = ''
        Automatic PostgreSQL major upgrades require a versioned dataDir whose
        final path component matches services.postgresql.package.psqlSchema
        (for example /var/lib/postgresql/18). Keep older clusters as numeric
        sibling directories, or provide a separate, tested migration plan.
      '';
    }
  ];

  # Run the migration in PostgreSQL's own preStart hook. On a NixOS switch,
  # systemd first stops the old postgresql.service instance, then runs this
  # ExecStartPre hook before the new service's initdb preStart. That guarantees
  # the source is offline and avoids relying on a separate dependency unit being
  # ordered around a restart of an already-active PostgreSQL service.
  systemd.services.postgresql = {
    # Use the switcher's stop/activate/start sequence so the old server and
    # PartOf clients are fully down before the new preStart gate runs.
    stopIfChanged = true;
    environment = migrationEnvironment;
    path = [
      pkgs.coreutils
      pkgs.diffutils
      pkgs.findutils
      pkgs.gawk
      pkgs.gnugrep
      pkgs.util-linux
    ];
    preStart = lib.mkBefore ''
      ${pkgs.bash}/bin/bash ${./../scripts/postgresql-major-upgrade.sh}
    '';
    # A copy upgrade can take hours; do not let systemd kill this pre-start
    # migration at its normal service-start timeout. Retain the usual bound for
    # PostgreSQL's orderly shutdown.
    serviceConfig = {
      TimeoutStartSec = "infinity";
      TimeoutStopSec = "120";
    };
  };

  # The NixOS setup unit runs after the new server is ready. Re-run it whenever
  # PostgreSQL itself restarts, so extension/statistics work is not skipped by
  # its RemainAfterExit state after an in-place major-version switch.
  systemd.services.postgresql-setup = {
    path = [ pkgs.coreutils ];
    script = lib.mkAfter postUpgradeMaintenance;
    partOf = [ "postgresql.service" ];
    restartTriggers = [
      (pkgs.writeText "postgresql-major-setup-trigger" targetMajor)
    ];
  };
}
