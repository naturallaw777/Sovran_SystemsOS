{ config, pkgs, lib, modulesPath, ... }:

let
  sovranSource = builtins.path { path = ../.; name = "sovran-systemsos"; };

  installerPy = pkgs.writeShellScriptBin "sovran-install" ''
    exec ${pkgs.python3.withPackages (ps: [ ps.pygobject3 ])}/bin/python3 /etc/sovran/installer.py
  '';
in
{
  imports = [
    "${modulesPath}/installer/cd-dvd/installation-cd-graphical-gnome.nix"
    ./branding.nix
  ];

  image.baseName = lib.mkForce "Sovran_SystemsOS";
  isoImage.splashImage = ./assets/splash-logo.png;

  services.gnome.gnome-initial-setup.enable = false;
  environment.gnome.excludePackages = with pkgs; [ gnome-tour gnome-user-docs ];

  security.sudo.wheelNeedsPassword = false;
  users.users.free = {
    isNormalUser = true;
    description = "free";
    extraGroups = [ "networkmanager" "wheel" ];
    initialPassword = "free";
  };

  services.displayManager.autoLogin.enable = true;
  services.displayManager.autoLogin.user = lib.mkForce "free";

  nix-bitcoin.generateSecrets = true;

  environment.systemPackages = with pkgs; [
    installerPy
    (python3.withPackages (ps: [ ps.pygobject3 ]))
    gtk4
    libadwaita
    gobject-introspection
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
  environment.etc."sovran/installer.py".source = ./installer.py;

  environment.etc."xdg/autostart/sovran-installer.desktop".text = ''
[Desktop Entry]
Type=Application
Name=Sovran Guided Installer
Exec=bash -c "DISPLAY=:0 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus ${installerPy}/bin/sovran-install"
Terminal=false
X-GNOME-Autostart-enabled=true
'';
}
