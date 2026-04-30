# ── modules/core/cpu-performance.nix ──────────────────────────────────────────
# Forces all CPU cores to run at maximum frequency on node and server_plus_desktop
# roles. Desktop-only installs retain normal OS power management behaviour.
#
# Three layers:
#   1. power-profiles-daemon disabled  — removes the GNOME power profile picker;
#                                        no user can switch profiles
#   2. cpufreq performance governor    — pins every core to max frequency via
#                                        kernel, enforced at boot by a oneshot unit
#   3. systemd oneshot enforcement     — belt-and-suspenders; applies the governor
#                                        after every boot even if module loads late
{ config, lib, pkgs, ... }:

{
  config = lib.mkIf (!config.sovran_systemsOS.roles.desktop) {

    # ── Layer 1: disable power-profiles-daemon ───────────────────────────────
    # This removes the power-profile switcher from GNOME Settings entirely.
    services.power-profiles-daemon.enable = false;

    # ── Layer 2: set cpufreq governor to performance ─────────────────────────
    # Pins all cores to max frequency. Works on Intel (intel_pstate) and AMD
    # (amd-pstate / acpi-cpufreq) alike.
    powerManagement.cpuFreqGovernor = "performance";

    # ── Layer 3: enforce at boot via systemd oneshot ─────────────────────────
    # Belt-and-suspenders: ensures the governor is applied after every boot even
    # if the kernel module loads late.
    systemd.services.cpu-performance = {
      description = "Set CPU governor to performance on all cores";
      wantedBy    = [ "multi-user.target" ];
      after       = [ "systemd-modules-load.service" ];
      serviceConfig = {
        Type            = "oneshot";
        RemainAfterExit = true;
      };
      script = ''
        found=0
        for gov in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
          if [ -w "$gov" ]; then
            echo performance > "$gov"
            found=1
          fi
        done
        if [ "$found" -eq 0 ]; then
          echo "cpu-performance: no writable cpufreq governors found (VM or unsupported hardware)" >&2
        fi
      '';
    };

  };
}
