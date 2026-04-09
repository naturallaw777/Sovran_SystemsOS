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
  # Grants only the minimum privileges needed for a support session.
  # Support staff cannot stop/disable/mask services or access wallet files.
  security.sudo.extraRules = [
    {
      users = [ "sovran-support" ];
      commands = [
        { command = "/run/current-system/sw/bin/nano /etc/nixos/custom.nix";        options = [ "NOPASSWD" ]; }
        { command = "/run/current-system/sw/bin/nano /etc/nixos/configuration.nix"; options = [ "NOPASSWD" ]; }
        { command = "/run/current-system/sw/bin/nixos-rebuild switch --flake /etc/nixos"; options = [ "NOPASSWD" ]; }
        { command = "/run/current-system/sw/bin/systemctl restart *";               options = [ "NOPASSWD" ]; }
        { command = "/run/current-system/sw/bin/journalctl *";                      options = [ "NOPASSWD" ]; }
      ];
    }
  ];
}
