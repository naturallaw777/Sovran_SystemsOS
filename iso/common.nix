{ config, pkgs, lib, modulesPath, ... }:

let
  sovranSource = builtins.path { path = ../.; name = "sovran-systemsos"; };

  pythonEnv = pkgs.python3.withPackages (ps: [ ps.pygobject3 ps.pycairo ]);

  installerPy = pkgs.writeShellScriptBin "sovran-install" ''
    export GI_TYPELIB_PATH=${pkgs.gtk4}/lib/girepository-1.0:${pkgs.libadwaita}/lib/girepository-1.0:${pkgs.glib}/lib/girepository-1.0:${pkgs.pango.out}/lib/girepository-1.0:${pkgs.gdk-pixbuf}/lib/girepository-1.0:${pkgs.graphene}/lib/girepository-1.0:${pkgs.cairo}/lib/girepository-1.0:${pkgs.harfbuzz}/lib/girepository-1.0:${pkgs.gobject-introspection}/lib/girepository-1.0
export LD_LIBRARY_PATH=${pkgs.gtk4}/lib:${pkgs.libadwaita}/lib:${pkgs.glib}/lib:${pkgs.pango.out}/lib:${pkgs.gdk-pixbuf}/lib:${pkgs.graphene}/lib:${pkgs.cairo}/lib:${pkgs.harfbuzz}/lib
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
 
  nix.settings.experimental-features = [ "nix-command" "flakes" ];

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
    parted
    dosfstools
    e2fsprogs
    gptfdisk
    nixos-install-tools
    git
    curl
    openssh
    tailscale
    jq
    xxd
  ];

  # Remote install support — SSH on the live ISO
  services.openssh = {
    enable = true;
    listenAddresses = [{ addr = "0.0.0.0"; port = 22; }];
    settings = {
      PasswordAuthentication = true;
      PermitRootLogin = "yes";
    };
  };
  users.users.root.initialPassword = "sovran-remote";

  # mDNS so the machine is discoverable as sovran-installer.local
  services.avahi = {
    enable = true;
    hostName = "sovran-installer";
    nssmdns4 = true;
    publish = { enable = true; addresses = true; };
  };

  environment.etc."sovran/logo.png".source = ./assets/splash-logo.png;
  environment.etc."sovran/flake".source = sovranSource;
  environment.etc."sovran/installer.py".source = ./installer.py;

  # These files are gitignored — set at build time by placing them in iso/secrets/
  environment.etc."sovran/enroll-token" = lib.mkIf (builtins.pathExists ./secrets/enroll-token) {
    text = builtins.readFile ./secrets/enroll-token;
    mode = "0600";
  };

  environment.etc."sovran/provisioner-url" = lib.mkIf (builtins.pathExists ./secrets/provisioner-url) {
    text = builtins.readFile ./secrets/provisioner-url;
    mode = "0644";
  };

  # Tailscale client for mesh VPN
  services.tailscale.enable = true;

  # Auto-provision service — registers with provisioning server and joins Tailnet
  systemd.services.sovran-auto-provision = {
    description = "Auto-register with Sovran provisioning server and join Tailnet";
    after = [ "network-online.target" "tailscaled.service" ];
    wants = [ "network-online.target" "tailscaled.service" ];
    wantedBy = [ "multi-user.target" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    path = [ pkgs.tailscale pkgs.curl pkgs.jq pkgs.coreutils pkgs.iproute2 pkgs.xxd ];
    script = ''
      TOKEN_FILE="/etc/sovran/enroll-token"
      URL_FILE="/etc/sovran/provisioner-url"

      [ -f "$TOKEN_FILE" ] || { echo "No enroll token found, skipping auto-provision"; exit 0; }
      [ -f "$URL_FILE" ] || { echo "No provisioner URL found, skipping auto-provision"; exit 0; }

      TOKEN=$(cat "$TOKEN_FILE")
      PROV_URL=$(cat "$URL_FILE")
      [ -n "$TOKEN" ] || exit 0
      [ -n "$PROV_URL" ] || exit 0

      # Wait for network + tailscaled
      sleep 10

      # Collect machine info
      HOSTNAME="sovran-deploy-$(head -c 8 /dev/urandom | xxd -p)"
      MAC=$(ip link show | grep ether | head -1 | awk '{print $2}' || echo "unknown")

      echo "Registering with provisioning server at $PROV_URL..."

      # Retry up to 6 times (covers slow DHCP)
      RESPONSE=""
      for i in $(seq 1 6); do
        RESPONSE=$(curl -sf --max-time 15 -X POST \
          "$PROV_URL/register" \
          -H "Authorization: Bearer $TOKEN" \
          -H "Content-Type: application/json" \
          -d "{\"hostname\": \"$HOSTNAME\", \"mac\": \"$MAC\"}" 2>/dev/null) && break
        echo "Attempt $i failed, retrying in 10s..."
        sleep 10
      done

      if [ -z "$RESPONSE" ]; then
        echo "ERROR: Failed to register with provisioning server after 6 attempts"
        exit 1
      fi

      HS_KEY=$(echo "$RESPONSE" | jq -r '.headscale_key')
      LOGIN_SERVER=$(echo "$RESPONSE" | jq -r '.login_server')

      if [ -z "$HS_KEY" ] || [ "$HS_KEY" = "null" ]; then
        echo "ERROR: No Headscale key in response: $RESPONSE"
        exit 1
      fi

      echo "Joining Tailnet via $LOGIN_SERVER as $HOSTNAME..."
      tailscale up \
        --login-server="$LOGIN_SERVER" \
        --authkey="$HS_KEY" \
        --hostname="$HOSTNAME"

      TAILSCALE_IP=$(tailscale ip -4)
      echo "Successfully joined Tailnet as $HOSTNAME ($TAILSCALE_IP)"
    '';
  };

  environment.etc."xdg/autostart/sovran-installer.desktop".text = ''
[Desktop Entry]
Type=Application
Name=Sovran Guided Installer
Exec=${installerPy}/bin/sovran-install
Terminal=false
X-GNOME-Autostart-enabled=true
'';
}
