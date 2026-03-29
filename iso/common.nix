{ config, pkgs, lib, modulesPath, ... }:

let
  sovranSource = builtins.path { path = ../.; name = "sovran-systemsos"; };
  installer = pkgs.writeShellScriptBin "sovran-install" (builtins.readFile ./installer.sh);
in
{
  imports = [
    "${modulesPath}/installer/cd-dvd/installation-cd-graphical-gnome.nix"
    ./branding.nix
  ];

  image.baseName = lib.mkForce "Sovran_SystemsOS";
  isoImage.splashImage = ./assets/splash-logo.png;

  # Disable GNOME first-run tour and initial setup so the installer autostarts instead
  services.gnome.gnome-initial-setup.enable = false;
  environment.gnome.excludePackages = with pkgs; [ gnome-tour gnome-user-docs ];

  users.users.free = {
    isNormalUser = true;
    description = "free";
    extraGroups = [ "networkmanager" ];
    initialPassword = "free";
  };

  services.displayManager.autoLogin.enable = true;
  services.displayManager.autoLogin.user = lib.mkForce "free";

  nix-bitcoin.generateSecrets = true;

  environment.systemPackages = with pkgs; [
    installer
    zenity
    util-linux
    disko
    parted
    dosfstools
    e2fsprogs
    gptfdisk
    nixos-install-tools
    git
    curl
  ];

  environment.etc."sovran/logo.png".source = ./assets/splash-logo.png;

  environment.etc."sovran/flake".source = sovranSource;

  environment.etc."xdg/autostart/sovran-installer.desktop".text = ''
    [Desktop Entry]
    Type=Application
    Name=Sovran Guided Installer
    Exec=gnome-terminal -- bash -c "${installer}/bin/sovran-install; exec bash"
    Terminal=false
    X-GNOME-Autostart-enabled=true
  '';
}
