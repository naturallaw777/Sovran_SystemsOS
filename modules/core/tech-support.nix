{ config, lib, pkgs, ... }:

# ── Tech Support — restricted support user & tooling ─────────────────────────
#
# This module declaratively provisions the `sovran-support` system account that
# the Sovran Hub uses when a user enables remote tech support access.
#
# Security design:
#   • Support staff log in as `sovran-support`, not as root.
#   • Protected directories (LND, bitcoind, nix-bitcoin-secrets, /home) are locked with POSIX ACLs
#     (u:sovran-support:---) by the Hub API as soon as a session is started.
#   • The Hub web UI lets the user grant time-limited access to wallet files
#     and view a full audit log of every session event.
#   • Scoped sudo rules allow support staff to restart specific services and
#     read logs — without full root, wallet access, Nix editing, or rebuilds.
#   • journalctl access is provided only through the root-owned
#     sovran-journal-helper script (see below) with an allowlist of safe flags.
{
  # ── System packages ────────────────────────────────────────────────────────
  environment.systemPackages = [ pkgs.acl ];

  # ── Restricted support user and group ─────────────────────────────────────
  users.groups.sovran-support = {};

  users.users.sovran-support = {
    isSystemUser  = true;
    group         = "sovran-support";
    description   = "Sovran Systems restricted tech support account";
    home          = "/var/lib/sovran-support";
    createHome    = false;
    # Use a real interactive shell so support staff can run diagnostic commands;
    # the Hub API limits *when* they can connect (key present only while active).
    shell         = pkgs.bashInteractive;
  };

  # ── Home and SSH directories ───────────────────────────────────────────────
  # tmpfiles ensures the directories exist at boot with the correct ownership
  # even before the first support session is started.
  systemd.tmpfiles.rules = [
    "d /var/lib/sovran-support      0700 sovran-support sovran-support -"
    "d /var/lib/sovran-support/.ssh 0700 sovran-support sovran-support -"
  ];

  # ── Restricted journal helper ─────────────────────────────────────────────
  # The helper is root-owned, not writable by any user, and accepts only a
  # narrow allowlist of safe journalctl flags.  It is the sole mechanism by
  # which the support user may read journal logs.
  environment.etc."sovran/sovran-journal-helper.py" = {
    source = ./sovran-journal-helper.py;
    mode   = "0500";
    user   = "root";
    group  = "root";
  };

  # ── Scoped sudo rules for support staff ───────────────────────────────────
  # Grants only the minimum privileges needed for diagnostic support.
  # Editing Nix configuration and running nixos-rebuild are intentionally
  # excluded: combining those two permissions provides a trivial path to
  # arbitrary root code execution.  Systemctl access is limited to a small
  # allowlist of named service restart operations.  journalctl is available
  # only through the restricted helper above.
  security.sudo.extraRules = [
    {
      users = [ "sovran-support" ];
      commands = [
        { command = "/run/current-system/sw/bin/systemctl restart sovran-hub.service";  options = [ "NOPASSWD" ]; }
        { command = "/run/current-system/sw/bin/systemctl restart caddy.service";       options = [ "NOPASSWD" ]; }
        { command = "/run/current-system/sw/bin/systemctl restart bitcoind.service";    options = [ "NOPASSWD" ]; }
        { command = "/run/current-system/sw/bin/systemctl restart lnd.service";         options = [ "NOPASSWD" ]; }
        { command = "/run/current-system/sw/bin/systemctl status sovran-hub.service";   options = [ "NOPASSWD" ]; }
        { command = "/run/current-system/sw/bin/systemctl status caddy.service";        options = [ "NOPASSWD" ]; }
        { command = "/run/current-system/sw/bin/systemctl status bitcoind.service";     options = [ "NOPASSWD" ]; }
        { command = "/run/current-system/sw/bin/systemctl status lnd.service";          options = [ "NOPASSWD" ]; }
        # Restricted journal helper: accepts only safe flags (--unit, --lines,
        # --priority, --since, --until, --output).  Rejects paths, directories,
        # namespaces, roots, and arbitrary output destinations.
        { command = "/run/current-system/sw/bin/python3 /etc/sovran/sovran-journal-helper.py *"; options = [ "NOPASSWD" ]; }
      ];
    }
  ];
}
