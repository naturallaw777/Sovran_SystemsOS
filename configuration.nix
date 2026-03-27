{ config, pkgs, lib, ... }:

{
  imports = [
    ./modules/modules.nix
  ];

  # ── Boot ────────────────────────────────────────────────────
  boot.loader.systemd-boot.enable = true;
  boot.loader.efi.canTouchEfiVariables = true;
  boot.loader.efi.efiSysMountPoint = "/boot/efi";
  boot.kernelPackages = pkgs.linuxPackages_latest;

  # ── Filesystems ─────────────────────────────────────────────
  fileSystems."/run/media/Second_Drive" = {
    device = "LABEL=BTCEcoandBackup";
    fsType = "ext4";
    options = [ "nofail" ];
  };

  fileSystems."/boot/efi".options = [ "umask=0077" "defaults" ];

  # ── Nix Settings ────────────────────────────────────────────
  nix.settings = {
    experimental-features = [ "nix-command" "flakes" ];
    download-buffer-size = 524288000;
  };

  # ── Networking ──────────────────────────────────────────────
  networking.hostName = "nixos";
  networking.networkmanager.enable = true;
  networking.firewall.enable = true;
  networking.firewall.allowedTCPPorts = [ 80 443 8448 3051 ];
  networking.firewall.allowedUDPPorts = [ 80 443 8448 3051 ];
  networking.firewall.allowedUDPPortRanges = [
    { from = 49152; to = 65535; }
  ];

  # ── Locale / Time ──────────────────────────────────────────
  time.timeZone = "America/Los_Angeles";
  i18n.defaultLocale = "en_US.UTF-8";

  # ── Desktop ────────────────────────────────────────────────
  services.xserver.enable = true;
  services.displayManager.gdm.enable = true;
  services.displayManager.gdm.autoSuspend = false;
  services.desktopManager.gnome.enable = true;
  services.xserver.xkb = { layout = "us"; variant = ""; };
  services.printing.enable = true;
  systemd.enableEmergencyMode = false;

  # ── Audio ──────────────────────────────────────────────────
  services.pulseaudio.enable = false;
  security.rtkit.enable = true;
  services.pipewire = {
    enable = true;
    alsa.enable = true;
    alsa.support32Bit = true;
    pulse.enable = true;
  };

  # ── Users ──────────────────────────────────────────────────
  users.users.free = {
    isNormalUser = true;
    description = "free";
    extraGroups = [ "networkmanager" ];
  };

  services.displayManager.autoLogin.enable = true;
  services.displayManager.autoLogin.user = "free";

  # ── Flatpak ────────────────────────────────────────────────
  services.flatpak.enable = true;
  systemd.services.flatpak-repo = {
    wantedBy = [ "multi-user.target" ];
    after = [ "network-online.target" ];
    wants = [ "network-online.target" ];
    path = [ pkgs.flatpak ];
    script = ''
      flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
    '';
  };

  # ── Packages ───────────────────────────────────────────────
  nixpkgs.config.allowUnfree = true;
  nixpkgs.config.permittedInsecurePackages = [ "jitsi-meet-1.0.8043" ];

  environment.systemPackages = with pkgs; [
    git wget fish htop btop
    gnomeExtensions.transparent-top-bar-adjustable-transparency
    gnomeExtensions.systemd-manager
    gnomeExtensions.dash-to-dock
    gnomeExtensions.vitals
    gnomeExtensions.pop-shell
    gnomeExtensions.just-perfection
    gnomeExtensions.appindicator
    gnomeExtensions.date-menu-formatter
    gnome-tweaks papirus-icon-theme
    ranger fastfetch gedit openssl pwgen
    aspell aspellDicts.en lm_sensors
    hunspell hunspellDicts.en_US
    synadm brave dua bitwarden-desktop
    gparted pv unzip parted screen zenity
    libargon2 gnome-terminal libreoffice-fresh
    dig firefox element-desktop wp-cli axel
    lk-jwt-service livekit-libwebrtc livekit-cli livekit
    matrix-synapse
  ];

  # ── Shell ──────────────────────────────────────────────────
  programs.nixvim = {
    enable = true;
    colorschemes.catppuccin.enable = true;
    plugins.lualine.enable = true;
  };

  programs.bash.promptInit = "fish";
  programs.fish = { enable = true; promptInit = "fastfetch"; };

  # ── PostgreSQL base ────────────────────────────────────────
  services.postgresql = {
    enable = true;
    authentication = lib.mkForce ''
      local   all   all                 trust
      host    all   all   127.0.0.1/32  trust
      host    all   all   ::1/128       trust
    '';
  };

  # ── Agenix ─────────────────────────────────────────────────
  age.identityPaths = [ "/root/.ssh/agenix/agenix-secret-keys" ];
  age.secrets.matrix_reg_secret = {
    file = /var/lib/agenix-secrets/matrix_reg_secret.age;
    mode = "770";
    owner = "matrix-synapse";
    group = "matrix-synapse";
  };

  # ── Backups ────────────────────────────────────────────────
  services.rsnapshot = {
    enable = true;
    extraConfig = ''
snapshot_root	/run/media/Second_Drive/BTCEcoandBackup/NixOS_Snapshot_Backup
retain	hourly	5
retain	daily	5
backup	/home/	localhost/
backup	/var/lib/	localhost/
backup	/etc/nixos/	localhost/
backup	/etc/nix-bitcoin-secrets/	localhost/
    '';
    cronIntervals = {
      daily = "50 21 * * *";
      hourly = "0 * * * *";
    };
  };

  # ── Cron (base system crons only) ─────────────────────────
  services.cron = {
    enable = true;
    systemCronJobs = [
      "*/15 * * * * root /run/current-system/sw/bin/bash /var/lib/njalla/njalla.sh"
      "*/15 * * * * root /run/current-system/sw/bin/bash /var/lib/external_ip/external_ip.sh"
      "0 0 * * 0 docker-user yes | /run/current-system/sw/bin/docker system prune -a"
    ];
  };

  # ── Tor ────────────────────────────────────────────────────
  services.tor = { enable = true; client.enable = true; torsocks.enable = true; };
  services.privoxy.enableTor = true;

  # ── SSH ────────────────────────────────────────────────────
  services.openssh = {
    enable = true;
    settings = {
      PasswordAuthentication = false;
      KbdInteractiveAuthentication = false;
      PermitRootLogin = "yes";
    };
  };

  # ── Fail2Ban ───────────────────────────────────────────────
  services.fail2ban = {
    enable = true;
    ignoreIP = [ "127.0.0.0/8" "10.0.0.0/8" "172.16.0.0/12" "192.168.0.0/16" "8.8.8.8" ];
  };

  # ── Garbage Collection ─────────────────────────────────────
  nix.gc = { automatic = true; dates = "weekly"; options = "--delete-older-than 7d"; };

  system.stateVersion = "22.05";
}
