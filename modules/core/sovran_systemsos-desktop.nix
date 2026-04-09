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
        picture-options = "zoom";
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
          "light-style@gnome-shell-extensions.gcampax.github.com"
        ];

        favorite-apps = [
          "brave-browser.desktop"
          "org.gnome.Settings.desktop"
          "org.gnome.Nautilus.desktop"
          "sovran-hub.desktop"
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

      "org/gnome/desktop/app-folders" = {
        folder-children = [ "Browsers" "Office" "Terminal" "Chat" "Bitcoin" "Media" "System" ];
      };

      "org/gnome/desktop/app-folders/folders/Browsers" = {
        name = "Browsers";
        apps = [
          "brave-browser.desktop"
          "firefox.desktop"
          "org.gnome.Epiphany.desktop"
        ];
      };

      "org/gnome/desktop/app-folders/folders/Office" = {
        name = "Office";
        apps = [
          "libreoffice-writer.desktop"
          "libreoffice-calc.desktop"
          "libreoffice-impress.desktop"
          "libreoffice-draw.desktop"
          "libreoffice-base.desktop"
          "libreoffice-math.desktop"
          "libreoffice-startcenter.desktop"
          "org.gnome.TextEditor.desktop"
          "org.gnome.gedit.desktop"
          "org.gnome.Calculator.desktop"
          "org.gnome.Calendar.desktop"
          "org.gnome.Contacts.desktop"
          "org.gnome.Geary.desktop"
          "org.gnome.Evince.desktop"
        ];
      };

      "org/gnome/desktop/app-folders/folders/Terminal" = {
        name = "Terminal";
        apps = [
          "org.gnome.Terminal.desktop"
          "org.gnome.tweaks.desktop"
          "gparted.desktop"
        ];
      };

      "org/gnome/desktop/app-folders/folders/Chat" = {
        name = "Chat";
        apps = [
          "element-desktop.desktop"
        ];
      };

      "org/gnome/desktop/app-folders/folders/Bitcoin" = {
        name = "Bitcoin";
        apps = [
          "sparrow-desktop.desktop"
          "Bisq.desktop"
          "bisq2.desktop"
        ];
      };

      "org/gnome/desktop/app-folders/folders/Media" = {
        name = "Media";
        apps = [
          "org.gnome.Loupe.desktop"
          "org.gnome.Totem.desktop"
          "org.gnome.Snapshot.desktop"
          "org.gnome.Weather.desktop"
          "org.gnome.Maps.desktop"
          "org.gnome.Clocks.desktop"
          "org.gnome.Music.desktop"
          "org.gnome.Characters.desktop"
          "org.gnome.font-viewer.desktop"
        ];
      };

      "org/gnome/desktop/app-folders/folders/System" = {
        name = "System";
        apps = [
          "org.gnome.Settings.desktop"
          "org.gnome.Nautilus.desktop"
          "org.gnome.Software.desktop"
          "sovran-hub.desktop"
          "bitwarden.desktop"
          "org.gnome.DiskUtility.desktop"
          "org.gnome.SystemMonitor.desktop"
          "org.gnome.Logs.desktop"
          "org.gnome.Connections.desktop"
          "org.gnome.baobab.desktop"
          "zenity.desktop"
        ];
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