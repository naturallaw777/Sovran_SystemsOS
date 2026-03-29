{ config, pkgs, lib, modulesPath, ... }:

let
  sovranSource = builtins.path { path = ../.; name = "sovran-systemsos"; };

  pythonEnv = pkgs.python3.withPackages (ps: [ ps.pygobject3 ]);

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
    pythonEnv
    libadwaita
    gtk4
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

  # libadwaita and gtk4 typelibs into the session
  environment.sessionVariables = {
    GI_TYPELIB_PATH = "${pkgs.libadwaita}/lib/girepository-1.0:${pkgs.gtk4}/lib/girepository-1.0:${pkgs.glib}/lib/girepository-1.0:${pkgs.pango}/lib/girepository-1.0:${pkgs.gdk-pixbuf}/lib/girepository-1.0:${pkgs.graphene}/lib/girepository-1.0";
    LD_LIBRARY_PATH = "${pkgs.libadwaita}/lib:${pkgs.gtk4}/lib:${pkgs.glib}/lib:${pkgs.pango}/lib:${pkgs.gdk-pixbuf}/lib:${pkgs.graphene}/lib";
  };

  environment.etc."sovran/logo.png".source = ./assets/splash-logo.png;
  environment.etc."sovran/flake".source = sovranSource;
  environment.etc."sovran/installer.py".source = ./installer.py;

  environment.etc."xdg/autostart/sovran-installer.desktop".text = ''
[Desktop Entry]
Type=Application
Name=Sovran Guided Installer
Exec=${pythonEnv}/bin/python3 /etc/sovran/installer.py
Terminal=false
X-GNOME-Autostart-enabled=true
'';
}
