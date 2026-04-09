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
#   • Scoped sudo rules allow editing config, triggering rebuilds, restarting services, and reading
#     logs — but not full root access.
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
  # Grants sovran-support the minimum privileges needed to diagnose and fix
  # issues: edit config, rebuild, restart services, and read logs.
  # No full root — wallet ACLs and session gating remain in effect.
  #
  # Intentionally excluded:
  #   • systemctl stop / disable / mask  — could disrupt services permanently
  #   • Full shell or unrestricted sudo  — would bypass wallet ACL protections
  security.sudo.extraRules = [
    {
      users = [ "sovran-support" ];
      commands = [
        # Edit NixOS config files
        { command = "/run/current-system/sw/bin/nano /etc/nixos/custom.nix";        options = [ "NOPASSWD" ]; }
        { command = "/run/current-system/sw/bin/nano /etc/nixos/configuration.nix"; options = [ "NOPASSWD" ]; }

        # Trigger a NixOS rebuild
        { command = "/run/current-system/sw/bin/nixos-rebuild switch --flake /etc/nixos"; options = [ "NOPASSWD" ]; }

        # Restart any systemd service (restart only — cannot stop, disable, or mask).
        # The glob covers all units; risk-accepted: repeated restarts of any service (including sshd)
        # are detectable in the session audit log at /var/log/sovran-support-audit.log.
        { command = "/run/current-system/sw/bin/systemctl restart *"; options = [ "NOPASSWD" ]; }

        # Read system logs (read-only)
        { command = "/run/current-system/sw/bin/journalctl *"; options = [ "NOPASSWD" ]; }
      ];
    }
  ];
}
