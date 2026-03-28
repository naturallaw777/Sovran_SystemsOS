{ config, pkgs, lib, ... }:

{
  imports = [
    # Base ISO profile
    "${pkgs.path}/nixos/modules/installer/cd-dvd/installation-cd-minimal.nix"

    # Your full system config + modules
    ./configuration.nix
  ];

  # ISO tweaks
  isoImage.isoName = "Sovran_SystemsOS.iso";

  # Convenience: enable SSH in live ISO
  services.openssh.enable = true;
  services.openssh.settings.PermitRootLogin = "yes";
  services.openssh.settings.PasswordAuthentication = true;

  # Optional: default password for ISO login only
  users.users.nixos.password = "nixos";
}