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

  isoImage.isoName = "Sovran_SystemsOS.iso";

  users.users.free = {
    isNormalUser = true;
    description = "free";
    extraGroups = [ "wheel" "networkmanager" ];
    initialPassword = "free";
  };

  services.displayManager.autoLogin.enable = true;
  services.displayManager.autoLogin.user = lib.mkForce "free";
  
  nix-bitcoin.generateSecrets = true;


  environment.systemPackages = with pkgs; [
    installer
    zenity
    util-linux
    parted
    dosfstools
    e2fsprogs
    gptfdisk
    nixos-install-tools
    git
    curl
  ];

  environment.etc."sovran/flake".source = sovranSource;

  environment.etc."xdg/autostart/sovran-installer.desktop".text = ''
    [Desktop Entry]
    Type=Application
    Name=Sovran Guided Installer
    Exec=${installer}/bin/sovran-install
    Terminal=false
    X-GNOME-Autostart-enabled=true
  '';
}
