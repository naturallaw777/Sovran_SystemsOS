{ config, lib, pkgs, ... }:

{
  # ── Always-on localhost SSH ────────────────────────────────────
  # Provides "ssh root@localhost" for local root access and Hub
  # operations. Binds exclusively to 127.0.0.1 — zero network exposure.
  # The sshd *feature flag* in sshd.nix extends this to 0.0.0.0 and
  # opens port 22 on the firewall when the user enables remote SSH.

  services.openssh = {
    enable = true;
    # sshd listens on 127.0.0.1 only here, so there is nothing for the firewall
    # to let in. NixOS opens sshd's ports by default (openFirewall = true)
    # whether or not sshd listens on them, which left port 22 open on every
    # role, Desktop Only included. The roles that do publish SSH open it
    # themselves: the sshd feature (sshd.nix) and remote deploy
    # (remote-deploy.nix) both add 22 explicitly.
    openFirewall = lib.mkDefault false;
    listenAddresses = lib.mkDefault [
      { addr = "127.0.0.1"; port = 22; }
    ];
    settings = {
      PasswordAuthentication = false;
      KbdInteractiveAuthentication = false;
      PermitRootLogin = "yes";
    };
  };
}