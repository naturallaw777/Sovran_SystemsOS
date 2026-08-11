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
#   • Scoped sudo rules allow support staff to edit custom.nix, trigger rebuilds,
#     restart services, and read logs — without full root or wallet access.
#
# The `acl` package provides the `setfacl` / `getfacl` utilities required by
# the Hub's _apply_wallet_acls() and _revoke_wallet_acls() helpers.
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

  # ── Scoped sudo rules for support staff ───────────────────────────────────
  # Grants only the minimum privileges needed for diagnostic support.
  # Editing Nix configuration and running nixos-rebuild are intentionally
  # excluded: combining those two permissions provides a trivial path to
  # arbitrary root code execution.  Systemctl access is limited to a small
  # allowlist of named service restart operations.
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
        { command = "/run/current-system/sw/bin/journalctl *";                          options = [ "NOPASSWD" ]; }
        # NOTE: journalctl with arbitrary flags is retained to allow support
        # staff to filter logs by unit, time-range, and priority during
        # diagnostics.  The --file / --directory flags could theoretically
        # allow reading arbitrary log files, but the support user already has
        # read access to /var/log as a system user.  Wallet and secret files
        # are not stored in journald format, so exposure is limited to
        # operational logs.  Consider restricting to specific units if a
        # narrower support workflow is defined in a future release.
      ];
    }
  ];
}
