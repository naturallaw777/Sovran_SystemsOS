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

      rsvg-convert -w 3440 -h 1440 \
        $src/sovran-wallpaper-12-ultrawide-3440x1440.svg \
        -o $out/share/backgrounds/sovran/sovran-ultrawide.png
    '';
  };

  sovranThemeInit = pkgs.writeShellScriptBin "sovran-theme-init" ''
    STAMP="$HOME/.config/sovran-theme-applied"
    USER_DB="$HOME/.config/dconf/user"

    # ── Always apply wallpaper on version change ──
    WALLPAPER_VERSION="${customWallpaper.version}"
    WALLPAPER_STAMP="$HOME/.config/sovran-wallpaper-version"

    BG_DIR="/run/current-system/sw/share/backgrounds/sovran"
    ULTRAWIDE="$BG_DIR/sovran-ultrawide.png"

    CURRENT_WALLPAPER_VERSION=""
    if [ -r "$WALLPAPER_STAMP" ]; then
      read -r CURRENT_WALLPAPER_VERSION < "$WALLPAPER_STAMP"
    fi

    if [ "$CURRENT_WALLPAPER_VERSION" != "$WALLPAPER_VERSION" ]; then
      if [ -f "$ULTRAWIDE" ]; then
        ${pkgs.dconf}/bin/dconf write /org/gnome/desktop/background/picture-uri "'file://$ULTRAWIDE'"
        ${pkgs.dconf}/bin/dconf write /org/gnome/desktop/background/picture-uri-dark "'file://$ULTRAWIDE'"
        ${pkgs.dconf}/bin/dconf write /org/gnome/desktop/background/picture-options "'zoom'"
        mkdir -p "$(dirname "$WALLPAPER_STAMP")"
        echo "$WALLPAPER_VERSION" > "$WALLPAPER_STAMP"
      fi
    fi

    # ── Brave Origin migration (existing installs upgrading from `brave`) ──
    # The old package's brave-browser.desktop no longer exists, so GNOME drops
    # it from the dock and the Browsers folder.  Swap the id in place, but only
    # when the stale value is still present (never touch user customizations).
    if [ -f "$USER_DB" ]; then
      FAVS="$(${pkgs.dconf}/bin/dconf read /org/gnome/shell/favorite-apps 2>/dev/null || true)"
      if [ -n "$FAVS" ]; then
        NEW_FAVS="''${FAVS//brave-browser.desktop/brave-origin.desktop}"
        if [ "$NEW_FAVS" != "$FAVS" ]; then
          ${pkgs.dconf}/bin/dconf write /org/gnome/shell/favorite-apps "$NEW_FAVS"
        fi
      fi

      BROWSER_APPS="$(${pkgs.dconf}/bin/dconf read /org/gnome/desktop/app-folders/folders/Browsers/apps 2>/dev/null || true)"
      if [ -n "$BROWSER_APPS" ]; then
        NEW_BROWSER_APPS="''${BROWSER_APPS//brave-browser.desktop/brave-origin.desktop}"
        if [ "$NEW_BROWSER_APPS" != "$BROWSER_APPS" ]; then
          ${pkgs.dconf}/bin/dconf write /org/gnome/desktop/app-folders/folders/Browsers/apps "$NEW_BROWSER_APPS"
        fi
      fi
    fi

    # A previous fresh install wrote the user's mimeapps.list with the old id;
    # XDG gives it precedence over the new system-wide default, so rewrite it.
    MIME_LIST="$HOME/.config/mimeapps.list"
    if [ -f "$MIME_LIST" ] && ${pkgs.gnugrep}/bin/grep -q 'brave-browser\.desktop' "$MIME_LIST"; then
      ${pkgs.gnused}/bin/sed -i 's/brave-browser\.desktop/brave-origin.desktop/g' "$MIME_LIST"
    fi

    # Already applied — skip
    if [ -f "$STAMP" ]; then
      exit 0
    fi

    # Existing machine updating — user already has their own settings, don't overwrite
    if [ -f "$USER_DB" ]; then
      mkdir -p "$HOME/.config"
      touch "$STAMP"
      exit 0
    fi

    # Fresh install — no user-db exists yet, apply full Sovran theme below

    mkdir -p "$HOME/.config"
    cat > "$HOME/.config/mimeapps.list" << EOF
[Default Applications]
text/html=brave-origin.desktop
x-scheme-handler/http=brave-origin.desktop
x-scheme-handler/https=brave-origin.desktop
x-scheme-handler/about=brave-origin.desktop
x-scheme-handler/unknown=brave-origin.desktop
EOF

    ${pkgs.dconf}/bin/dconf load / << EOF
[org/gnome/desktop/interface]
color-scheme='prefer-dark'
enable-animations=true
icon-theme='Papirus-Dark'

[org/gnome/settings-daemon/plugins/power]
sleep-inactive-ac-type='nothing'
sleep-inactive-ac-timeout=0
sleep-inactive-battery-type='nothing'
sleep-inactive-battery-timeout=0
idle-dim=false
ambient-enabled=false
power-button-action='nothing'

[org/gnome/desktop/session]
idle-delay=uint32 0

[org/gnome/desktop/screensaver]
lock-enabled=false
idle-activation-enabled=false

[org/gnome/mutter]
edge-tiling=false

[org/gnome/nautilus/icon-view]
default-zoom-level='large'

[org/gnome/nautilus/preferences]
default-folder-viewer='icon-view'
migrated-gtk-settings=true
search-filter-time-type='last_modified'

[org/gnome/shell]
disabled-extensions=['just-perfection-desktop@just-perfection']
enabled-extensions=['appindicatorsupport@rgcjonas.gmail.com', 'dash-to-dock-cosmic-@halfmexicanhalfamazing@gmail.com', 'Vitals@CoreCoding.com', 'dash-to-dock@micxgx.gmail.com', 'pop-shell@system76.com', 'date-menu-formatter@marcinjakubowski.github.com', 'light-style@gnome-shell-extensions.gcampax.github.com']
favorite-apps=['brave-origin.desktop', 'org.gnome.Settings.desktop', 'org.gnome.Nautilus.desktop', 'sovran-hub.desktop', 'org.gnome.Software.desktop', 'org.gnome.Geary.desktop', 'org.gnome.Contacts.desktop', 'org.gnome.Calendar.desktop', 'sparrow.desktop', 'Bisq.desktop', 'bisq2.desktop']
welcome-dialog-last-shown-version='48.4'

[org/gnome/desktop/app-folders]
folder-children=['Browsers', 'Office', 'Terminal', 'Chat', 'Bitcoin', 'Media', 'System']

[org/gnome/desktop/app-folders/folders/Browsers]
name='Browsers'
apps=['brave-origin.desktop', 'firefox.desktop', 'org.gnome.Epiphany.desktop']

[org/gnome/desktop/app-folders/folders/Office]
name='Office'
apps=['libreoffice-writer.desktop', 'libreoffice-calc.desktop', 'libreoffice-impress.desktop', 'libreoffice-draw.desktop', 'libreoffice-base.desktop', 'libreoffice-math.desktop', 'libreoffice-startcenter.desktop', 'org.gnome.TextEditor.desktop', 'org.gnome.gedit.desktop', 'org.gnome.Calculator.desktop', 'org.gnome.Calendar.desktop', 'org.gnome.Contacts.desktop', 'org.gnome.Geary.desktop', 'org.gnome.Evince.desktop', 'onlyoffice-desktopeditors.desktop', 'simple-scan.desktop', 'system-config-printer.desktop']

[org/gnome/desktop/app-folders/folders/Terminal]
name='Terminal'
apps=['org.gnome.Terminal.desktop', 'org.gnome.tweaks.desktop', 'gparted.desktop', 'htop.desktop', 'btop.desktop', 'ranger.desktop', 'org.gnome.Console.desktop']

[org/gnome/desktop/app-folders/folders/Chat]
name='Chat'
apps=['element-desktop.desktop']

[org/gnome/desktop/app-folders/folders/Bitcoin]
name='Bitcoin'
apps=['sparrow.desktop', 'Bisq.desktop', 'bisq2.desktop']

[org/gnome/desktop/app-folders/folders/Media]
name='Media'
apps=['org.gnome.Loupe.desktop', 'org.gnome.Totem.desktop', 'org.gnome.Snapshot.desktop', 'org.gnome.Weather.desktop', 'org.gnome.Maps.desktop', 'org.gnome.Clocks.desktop', 'org.gnome.Music.desktop', 'org.gnome.Characters.desktop', 'org.gnome.font-viewer.desktop']

[org/gnome/desktop/app-folders/folders/System]
name='System'
apps=['org.gnome.Settings.desktop', 'org.gnome.Nautilus.desktop', 'org.gnome.Software.desktop', 'sovran-hub.desktop', 'bitwarden.desktop', 'org.gnome.DiskUtility.desktop', 'org.gnome.SystemMonitor.desktop', 'org.gnome.Logs.desktop', 'org.gnome.Connections.desktop', 'org.gnome.baobab.desktop', 'zenity.desktop']

[org/gnome/shell/extensions/dash-to-dock]
background-color='rgb(0,0,0)'
background-opacity=0.50000000000000001
custom-background-color=true
dash-max-icon-size=47
dock-position='BOTTOM'
height-fraction=0.90000000000000002
preferred-monitor=-2
preferred-monitor-by-connector='Virtual-1'
show-trash=false
transparency-mode='FIXED'

[org/gnome/shell/extensions/date-menu-formatter]
font-size=12
pattern='EEEE,  MMM d  h:mm a'
text-align='center'
update-level=1

[org/gnome/shell/extensions/just-perfection]
support-notifier-showed-version=34
support-notifier-type=0

[org/gnome/shell/extensions/pop-shell]
tile-by-default=true

[org/gnome/shell/extensions/vitals]
hot-sensors=['_storage_free_', '_processor_usage_', '_memory_usage_']

[org/gnome/software]
first-run=false

[org/gtk/gtk4/settings/color-chooser]
selected-color=(true, 0.0, 0.0, 0.0, 1.0)
EOF

    mkdir -p "$HOME/.config"
    touch "$STAMP"
  '';

in 

{

  environment.systemPackages = [ customWallpaper sovranThemeInit ];

  environment.etc."xdg/autostart/sovran-theme-init.desktop".text = ''
    [Desktop Entry]
    Type=Application
    Name=Sovran Theme Init
    Exec=${sovranThemeInit}/bin/sovran-theme-init
    X-GNOME-Autostart-enabled=true
    X-GNOME-Autostart-Phase=Application
    NoDisplay=true
  '';

  programs.dconf.enable = true;

  programs.dconf.profiles.user.databases = [
  {
    settings = {

      "org/gnome/desktop/background" = {
        picture-uri = "file:///run/current-system/sw/share/backgrounds/sovran/sovran-ultrawide.png";
        picture-uri-dark = "file:///run/current-system/sw/share/backgrounds/sovran/sovran-ultrawide.png";
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
          "brave-origin.desktop"
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
          "brave-origin.desktop"
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
          "onlyoffice-desktopeditors.desktop"
          "simple-scan.desktop"
          "system-config-printer.desktop"
        ];
      };

      "org/gnome/desktop/app-folders/folders/Terminal" = {
        name = "Terminal";
        apps = [
          "org.gnome.Terminal.desktop"
          "org.gnome.tweaks.desktop"
          "gparted.desktop"
          "htop.desktop"
          "btop.desktop"
          "ranger.desktop"
          "org.gnome.Console.desktop"
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

  }
  ];

  xdg.mime.defaultApplications = {
    "text/html" = "brave-origin.desktop";
    "x-scheme-handler/http" = "brave-origin.desktop";
    "x-scheme-handler/https" = "brave-origin.desktop";
    "x-scheme-handler/about" = "brave-origin.desktop";
    "x-scheme-handler/unknown" = "brave-origin.desktop";
  };

  environment.sessionVariables.BROWSER = "brave-origin";

}
