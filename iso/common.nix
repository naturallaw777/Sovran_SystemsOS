{ config, pkgs, lib, modulesPath, ... }:

let
  sovranSource = builtins.path { path = ../.; name = "sovran-systemsos"; };

  pythonEnv = pkgs.python3.withPackages (ps: [ ps.pygobject3 ps.pycairo ]);

  installerPy = pkgs.writeShellScriptBin "sovran-install" ''
    export GI_TYPELIB_PATH=${pkgs.gtk4}/lib/girepository-1.0:${pkgs.libadwaita}/lib/girepository-1.0:${pkgs.glib}/lib/girepository-1.0:${pkgs.pango.out}/lib/girepository-1.0:${pkgs.gdk-pixbuf}/lib/girepository-1.0:${pkgs.graphene}/lib/girepository-1.0:${pkgs.cairo}/lib/girepository-1.0:${pkgs.harfbuzz}/lib/girepository-1.0:${pkgs.gobject-introspection}/lib/girepository-1.0
    export LD_LIBRARY_PATH=${pkgs.gtk4}/lib:${pkgs.libadwaita}/lib:${pkgs.glib}/lib:${pkgs.pango}/lib:${pkgs.gdk-pixbuf}/lib:${pkgs.graphene}/lib:${pkgs.cairo}/lib:${pkgs.harfbuzz}/lib
    export GDK_PIXBUF_MODULE_FILE="${pkgs.gdk-pixbuf}/lib/gdk-pixbuf-2.0/2.10.0/loaders.cache"
    export XDG_DATA_DIRS="${pkgs.gsettings-desktop-schemas}/share/gsettings-schemas/${pkgs.gsettings-desktop-schemas.name}:${pkgs.gtk4}/share:${pkgs.libadwaita}/share:${pkgs.adwaita-icon-theme}/share:${pkgs.hicolor-icon-theme}/share:$XDG_DATA_DIRS"
    exec ${pythonEnv}/bin/python3 /etc/sovran/installer.py
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

  nix-bitcoin.generateSecrets = lib.mkDefault true;
  
  nix.settings.experimental-features = [ "nix-command" "flakes" ]

  environment.systemPackages = with pkgs; [
    installerPy
    pythonEnv
    gtk4
    libadwaita
    gobject-introspection
    glib
    pango
    gdk-pixbuf
    graphene
    cairo
    harfbuzz
    gsettings-desktop-schemas
    adwaita-icon-theme
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
Exec=${installerPy}/bin/sovran-install
Terminal=false
X-GNOME-Autostart-enabled=true
'';
}
