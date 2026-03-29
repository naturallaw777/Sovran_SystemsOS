{ config, pkgs, lib, ... }: 

let

  customWallpaper = pkgs.stdenvNoCC.mkDerivation {
    pname = "sovran-systemsos-wallpaper";
    version = "1.0";
    src = pkgs.fetchurl {
      url = "https://git.sovransystems.com/Sovran_Systems/Sovran_SystemsOS_iso/raw/branch/main/post-install-scripts/Wallpaper_Dark_Wide.png";
      sha256 = "0609gy0vp92fywl7pcr4y3mg05ca6pwxsnlsax14jd371fj4y7fn";
    };
    dontUnpack = true;
    installPhase = ''
      mkdir -p $out/share/backgrounds/sovran
      cp $src $out/share/backgrounds/sovran/Wallpaper_Dark_Wide.png
      '';
  };

in 

{

  environment.systemPackages = [ customWallpaper ];

  programs.dconf.enable = true;

  programs.dconf.profiles.user.databases = [
  {
    settings = {

      "org/gnome/desktop/background" = {
        picture-uri = "file:///run/current-system/sw/share/backgrounds/sovran/Wallpaper_Dark_Wide.png";
        picture-uri-dark = "file:///run/current-system/sw/share/backgrounds/sovran/Wallpaper_Dark_Wide.png";
        picture-options = "zoom"; # Options: none, centered, scaled, stretched, zoom, spanned
        primary-color = "#000000";
        secondary-color = "#000000";
      };

      "org/gnome/desktop/input-sources" = {
        sources = [ (lib.gvariant.mkTuple [ "xkb" "us" ]) ];
        xkb-options = lib.gvariant.mkEmptyArray lib.gvariant.type.string;
      };

      "org/gnome/desktop/interface" = {
        color-scheme = "prefer-dark";
        enable-animations = true;
        icon-theme = "Papirus-Dark";
      };

      "org/gnome/evolution-data-server" = {
        migrated = true;
      };

      "org/gnome/mutter" = {
        edge-tiling = false;
      };

      "org/gnome/nautilus/icon-view" = {
        default-zoom-level = "large";
      };

      "org/gnome/nautilus/preferences" = {
        default-folder-viewer = "icon-view";
        migrated-gtk-settings = true;
        search-filter-time-type = "last_modified";
      };
      
      "org/gnome/shell" = {
        disabled-extensions = [ "just-perfection-desktop@just-perfection" ];
        
        enabled-extensions = [
          "appindicatorsupport@rgcjonas.gmail.com"
          "dash-to-dock-cosmic-@halfmexicanhalfamazing@gmail.com"
          "Vitals@CoreCoding.com"
          "dash-to-dock@micxgx.gmail.com"
          "pop-shell@system76.com"
          "date-menu-formatter@marcinjakubowski.github.com"
          "systemd-manager@hardpixel.eu"
          "light-style@gnome-shell-extensions.gcampax.github.com"
        ];

        favorite-apps = [
          "brave-browser.desktop"
          "org.gnome.Settings.desktop"
          "org.gnome.Nautilus.desktop"
          "Sovran_SystemsOS_Updater.desktop"
          "org.gnome.Software.desktop"
          "org.gnome.Geary.desktop"
          "org.gnome.Contacts.desktop"
          "org.gnome.Calendar.desktop"
          "sparrow-desktop.desktop"
          "Bisq.desktop"
          "bisq2.desktop"
        ];

        welcome-dialog-last-shown-version = "48.4";
      };

      "org/gnome/shell/extensions/dash-to-dock" = {
        background-color = "rgb(0,0,0)";
        background-opacity = 0.50000000000000001;
        custom-background-color = true;
        dash-max-icon-size = lib.gvariant.mkInt32 47;
        dock-position = "BOTTOM";
        height-fraction = 0.90000000000000002;
        preferred-monitor = lib.gvariant.mkInt32 (-2);
        preferred-monitor-by-connector = "Virtual-1";
        show-trash = false;
        transparency-mode = "FIXED";
      };

      "org/gnome/shell/extensions/date-menu-formatter" = {
        font-size = lib.gvariant.mkInt32 12;
        pattern = "EEEE,  MMM d  h:mm a";
        text-align = "center";
        update-level = lib.gvariant.mkInt32 1;
      };

      "org/gnome/shell/extensions/just-perfection" = {
        support-notifier-showed-version = lib.gvariant.mkInt32 34;
        support-notifier-type = lib.gvariant.mkInt32 0;
      };

      "org/gnome/shell/extensions/pop-shell" = {
        tile-by-default = true;
      };

      "org/gnome/shell/extensions/systemd-manager" = {
        command-method = "systemctl";
        systemd = [
          "{\"name\":\"Bitcoind\",\"service\":\"bitcoind.service\",\"type\":\"system\"}"
          "{\"name\":\"Electrs\",\"service\":\"electrs.service\",\"type\":\"system\"}"
          "{\"name\":\"CLN\",\"service\":\"clightning.service\",\"type\":\"system\"}"
          "{\"name\":\"LND\",\"service\":\"lnd.service\",\"type\":\"system\"}"
          "{\"name\":\"Ride The Lightning\",\"service\":\"rtl.service\",\"type\":\"system\"}"
          "{\"name\":\"BTCPayserver\",\"service\":\"btcpayserver.service\",\"type\":\"system\"}"
          "{\"name\":\"Matrix-Synapse\",\"service\":\"matrix-synapse.service\",\"type\":\"system\"}"
          "{\"name\":\"Coturn\",\"service\":\"coturn.service\",\"type\":\"system\"}"
          "{\"name\":\"VaultWarden\",\"service\":\"vaultwarden.service\",\"type\":\"system\"}"
          "{\"name\":\"Caddy\",\"service\":\"caddy.service\",\"type\":\"system\"}"
          "{\"name\":\"Tor\",\"service\":\"tor.service\",\"type\":\"system\"}"
        ];
      };

      "org/gnome/shell/extensions/vitals" = {
        hot-sensors = [
          "_storage_free_"
          "_processor_usage_"
          "_memory_usage_"
        ];
      };

      "org/gnome/software" = {
        check-timestamp = lib.gvariant.mkInt64 1760848349;
        first-run = false;
      };

      "org/gtk/gtk4/settings/color-chooser" = {
        selected-color = lib.gvariant.mkTuple [ true 0.0 0.0 0.0 1.0 ];
      };
    };

  }
  ];

}
