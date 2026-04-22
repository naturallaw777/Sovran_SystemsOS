# ── modules/core/no-sleep.nix ─────────────────────────────────────────────────
# Prevents the machine from ever sleeping or suspending at the system level.
#
# Only applies to server_plus_desktop and node roles. Desktop-only installs
# retain normal OS sleep/suspend behaviour.
#
# This operates at two layers below GNOME:
#   1. systemd-logind  — ignores all hardware power events (lid, suspend key, etc.)
#   2. systemd targets — masks sleep/suspend/hibernate targets so nothing can
#                        trigger them, not even `systemctl suspend` or D-Bus calls.
#
# This is intentional for a 24/7 server/node. The GNOME-layer power settings in
# sovran_systemsos-desktop.nix remain in place as a belt-and-suspenders complement
# for active user sessions.
{ config, lib, ... }:

{
  config = lib.mkIf (!config.sovran_systemsOS.roles.desktop) {

    # ── Layer 1: logind hardware event handling ──────────────────────────────
    services.logind = {
      lidSwitch = "ignore";
      lidSwitchDocked = "ignore";
      lidSwitchExternalPower = "ignore";
      settings.Login = {
        HandleSuspendKey = "ignore";
        HandleHibernateKey = "ignore";
        HandlePowerKey = "ignore";
        IdleAction = "ignore";
        IdleActionSec = 0;
      };
    };

    # ── Layer 2: mask systemd sleep targets ─────────────────────────────────
    # Nothing on the system can suspend/hibernate — not root, not GNOME, not D-Bus.
    systemd.targets.sleep.enable = false;
    systemd.targets.suspend.enable = false;
    systemd.targets.hibernate.enable = false;
    systemd.targets.hybrid-sleep.enable = false;
  };
}
