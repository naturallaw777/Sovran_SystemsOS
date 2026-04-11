{ config, lib, pkgs, ... }:

{
  # ── Legacy Cleanup ─────────────────────────────────────────────
  # Removes deprecated apps and folders from the old Sovran_Systems
  # repo that are no longer needed under staging_alpha.
  # This runs on every activation but is idempotent (no-ops if
  # the files are already gone).

  system.activationScripts.cleanupLegacySovran = lib.stringAfter [ "users" ] ''
    echo "── Cleaning up legacy Sovran_Systems artifacts ──"

    # Remove deprecated .desktop files
    for f in \
      /home/free/.local/share/applications/Sovran_SystemsOS_External_Backup.desktop \
      /home/free/.local/share/applications/Sovran_SystemsOS_Updater.desktop \
      /home/free/.local/share/applications/Sovran_SystemsOS_Resetter.desktop
    do
      if [ -f "$f" ]; then
        rm -f "$f"
        echo "  Removed: $f"
      fi
    done

    # Remove legacy Sovran_Systems folder (skip if it's a symlink)
    if [ -d /home/free/.Sovran_Systems ] && [ ! -L /home/free/.Sovran_Systems ]; then
      rm -rf /home/free/.Sovran_Systems
      echo "  Removed: /home/free/.Sovran_Systems/"
    fi

    echo "── Legacy cleanup complete ──"
  '';
}
