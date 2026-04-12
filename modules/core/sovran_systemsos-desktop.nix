{ config, pkgs, lib, ... }: 

let

  wallpaperSrc = ../../assets/wallpapers;

  customWallpaper = pkgs.stdenvNoCC.mkDerivation {
    pname = "sovran-systemsos-wallpaper";
    version = "2.0";
    src = wallpaperSrc;
    nativeBuildInputs = [ pkgs.librsvg ];
    installPhase = ''
      mkdir -p $out/share/backgrounds/sovran

      rsvg-convert -w 1920 -h 1080 \
        $src/sovran-wallpaper-08-tagline-only.svg \
        -o $out/share/backgrounds/sovran/sovran-standard.png

      rsvg-convert -w 3440 -h 1440 \
        $src/sovran-wallpaper-12-ultrawide-3440x1440.svg \
        -o $out/share/backgrounds/sovran/sovran-ultrawide.png
    '';
  };

  wallpaperInit = pkgs.writeShellScriptBin "sovran-wallpaper-init" ''
    STAMP="$HOME/.config/sovran-wallpaper-set"
    if [ -f "$STAMP" ]; then
      exit 0
    fi

    BG_DIR="/run/current-system/sw/share/backgrounds/sovran"
    STANDARD="$BG_DIR/sovran-standard.png"
    ULTRAWIDE="$BG_DIR/sovran-ultrawide.png"

    WIDTH=$(${pkgs.dbus}/bin/dbus-send \
      --session \
      --print-reply \
      --dest=org.gnome.Mutter.DisplayConfig \
      /org/gnome/Mutter/DisplayConfig \
      org.gnome.Mutter.DisplayConfig.GetCurrentState \
      2>/dev/null \
      | grep -oP 'uint32 \K[0-9]+' \
      | head -1)

    CHOSEN="$STANDARD"
    if [ -n "$WIDTH" ] && [ "$WIDTH" -ge 2560 ] && [ -f "$ULTRAWIDE" ]; then
      CHOSEN="$ULTRAWIDE"
    fi

    ${pkgs.dconf}/bin/dconf write /org/gnome/desktop/background/picture-uri \
      "'file://$CHOSEN'"
    ${pkgs.dconf}/bin/dconf write /org/gnome/desktop/background/picture-uri-dark \
      "'file://$CHOSEN'"
    ${pkgs.dconf}/bin/dconf write /org/gnome/desktop/background/picture-options \
      "'zoom'"

    mkdir -p "$HOME/.config"
    touch "$STAMP"
  '';

in 

{

  environment.systemPackages = [ customWallpaper wallpaperInit ];

  environment.etc."xdg/autostart/sovran-wallpaper-init.desktop".text = ''
    [Desktop Entry]
    Type=Application
    Name=Sovran Wallpaper Init
    Exec=${wallpaperInit}/bin/sovran-wallpaper-init
    X-GNOME-Autostart-enabled=true
    X-GNOME-Autostart-Phase=Application
    NoDisplay=true
  '';

  programs.dconf.enable = true;

  programs.dconf.profiles.user.databases = [
  {
    settings = {

      "org/gnome/desktop/background" = {
        picture-uri = "file:///run/current-system/sw/share/backgrounds/sovran/sovran-standard.png";
        picture-uri-dark = "file:///run/current-system/sw/share/backgrounds/sovran/sovran-standard.png";
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

      "org/gnome/settings-daemon/plugins/power" = {
        sleep-inactive-ac-type = "nothing";
        sleep-inactive-ac-timeout = lib.gvariant.mkInt32 0;
        sleep-inactive-battery-type = "nothing";
        sleep-inactive-battery-timeout = lib.gvariant.mkInt32 0;
        idle-dim = false;
        ambient-enabled = false;
        power-button-action = "nothing";
      };

      "org/gnome/desktop/session" = {
        idle-delay = lib.gvariant.mkUint32 0;
      };

      "org/gnome/desktop/screensaver" = {
        lock-enabled = false;
        idle-activation-enabled = false;
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
          "sparrow.desktop"
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
          "sparrow.desktop"
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

    locks = [
      "/org/gnome/desktop/background/picture-uri"
      "/org/gnome/desktop/background/picture-uri-dark"
      "/org/gnome/desktop/background/picture-options"
      "/org/gnome/desktop/background/primary-color"
      "/org/gnome/desktop/background/secondary-color"
      "/org/gnome/desktop/input-sources/sources"
      "/org/gnome/desktop/input-sources/xkb-options"
      "/org/gnome/desktop/interface/color-scheme"
      "/org/gnome/desktop/interface/enable-animations"
      "/org/gnome/desktop/interface/icon-theme"
      "/org/gnome/evolution-data-server/migrated"
      "/org/gnome/mutter/edge-tiling"
      "/org/gnome/nautilus/icon-view/default-zoom-level"
      "/org/gnome/nautilus/preferences/default-folder-viewer"
      "/org/gnome/nautilus/preferences/migrated-gtk-settings"
      "/org/gnome/nautilus/preferences/search-filter-time-type"
      "/org/gnome/shell/disabled-extensions"
      "/org/gnome/shell/enabled-extensions"
      "/org/gnome/shell/favorite-apps"
      "/org/gnome/shell/welcome-dialog-last-shown-version"
      "/org/gnome/desktop/app-folders/folder-children"
      "/org/gnome/desktop/app-folders/folders/Browsers/name"
      "/org/gnome/desktop/app-folders/folders/Browsers/apps"
      "/org/gnome/desktop/app-folders/folders/Office/name"
      "/org/gnome/desktop/app-folders/folders/Office/apps"
      "/org/gnome/desktop/app-folders/folders/Terminal/name"
      "/org/gnome/desktop/app-folders/folders/Terminal/apps"
      "/org/gnome/desktop/app-folders/folders/Chat/name"
      "/org/gnome/desktop/app-folders/folders/Chat/apps"
      "/org/gnome/desktop/app-folders/folders/Bitcoin/name"
      "/org/gnome/desktop/app-folders/folders/Bitcoin/apps"
      "/org/gnome/desktop/app-folders/folders/Media/name"
      "/org/gnome/desktop/app-folders/folders/Media/apps"
      "/org/gnome/desktop/app-folders/folders/System/name"
      "/org/gnome/desktop/app-folders/folders/System/apps"
      "/org/gnome/shell/extensions/dash-to-dock/background-color"
      "/org/gnome/shell/extensions/dash-to-dock/background-opacity"
      "/org/gnome/shell/extensions/dash-to-dock/custom-background-color"
      "/org/gnome/shell/extensions/dash-to-dock/dash-max-icon-size"
      "/org/gnome/shell/extensions/dash-to-dock/dock-position"
      "/org/gnome/shell/extensions/dash-to-dock/height-fraction"
      "/org/gnome/shell/extensions/dash-to-dock/preferred-monitor"
      "/org/gnome/shell/extensions/dash-to-dock/preferred-monitor-by-connector"
      "/org/gnome/shell/extensions/dash-to-dock/show-trash"
      "/org/gnome/shell/extensions/dash-to-dock/transparency-mode"
      "/org/gnome/shell/extensions/date-menu-formatter/font-size"
      "/org/gnome/shell/extensions/date-menu-formatter/pattern"
      "/org/gnome/shell/extensions/date-menu-formatter/text-align"
      "/org/gnome/shell/extensions/date-menu-formatter/update-level"
      "/org/gnome/shell/extensions/just-perfection/support-notifier-showed-version"
      "/org/gnome/shell/extensions/just-perfection/support-notifier-type"
      "/org/gnome/shell/extensions/pop-shell/tile-by-default"
      "/org/gnome/shell/extensions/vitals/hot-sensors"
      "/org/gnome/software/check-timestamp"
      "/org/gnome/software/first-run"
      "/org/gtk/gtk4/settings/color-chooser/selected-color"
    ];

  }
  ];

}