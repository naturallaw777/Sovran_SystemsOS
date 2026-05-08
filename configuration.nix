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
  boot.kernelParams = [ "quiet" "loglevel=3" "rd.systemd.show_status=false" "udev.log_level=3" ];
  boot.blacklistedKernelModules = [ "rxrpc" ];

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
  networking.firewall.allowedUDPPorts = [ 5353 ];

  # ── Avahi (mDNS) ───────────────────────────────────────────
  services.avahi = {
    enable = true;
    hostName = "sovransystemsos";
    nssmdns4 = true;
    publish = { enable = true; addresses = true; };
  };

  # ── Locale / Time ──────────────────────────────────────────
  time.timeZone = null;
  i18n.defaultLocale = lib.mkDefault "en_US.UTF-8";
  i18n.supportedLocales = [
    "en_US.UTF-8/UTF-8"
    "en_GB.UTF-8/UTF-8"
    "es_ES.UTF-8/UTF-8"
    "fr_FR.UTF-8/UTF-8"
    "de_DE.UTF-8/UTF-8"
    "pt_BR.UTF-8/UTF-8"
    "ja_JP.UTF-8/UTF-8"
    "zh_CN.UTF-8/UTF-8"
    "ko_KR.UTF-8/UTF-8"
    "ru_RU.UTF-8/UTF-8"
    "ar_SA.UTF-8/UTF-8"
    "hi_IN/UTF-8"
  ];

  # ── Desktop ────────────────────────────────────────────────
  services.displayManager.gdm.enable = true;
  services.displayManager.gdm.autoSuspend = false;
  services.displayManager.gdm.wayland = true;
  services.desktopManager.gnome.enable = true;
  services.printing.enable = true;
  systemd.enableEmergencyMode = false;
  environment.gnome.excludePackages = [ pkgs.gnome-tour ];
  security.pam.services.gdm-password.enableGnomeKeyring = true;
  security.pam.services.gdm-autologin.enableGnomeKeyring = true;

  # Declaratively guarantee the GNOME Keyring default pointer exists.
  # Defining the full path ensures root doesn't accidentally lock the user out of .local
  systemd.tmpfiles.rules = [
    "d /home/free/.local 0700 free users -"
    "d /home/free/.local/share 0700 free users -"
    "d /home/free/.local/share/keyrings 0700 free users -"
    "f /home/free/.local/share/keyrings/default 0600 free users - login\n"
  ];


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

  services.displayManager.autoLogin.enable = false;

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

  environment.systemPackages = with pkgs; [
    nftables
    git wget fish htop btop
    gnomeExtensions.transparent-top-bar-adjustable-transparency
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
    matrix-synapse age
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

  # ── Cron ───────────────────────────────────────────────────
  services.cron = {
    enable = true;
    systemCronJobs = [
      "*/15 * * * * root /run/current-system/sw/bin/bash /var/lib/njalla/njalla.sh"
    ];
  };

  # ── Tor ────────────────────────────────────────────────────
  services.tor = { enable = true; client.enable = true; torsocks.enable = true; };

  # ── Garbage Collection ─────────────────────────────────────
  nix.gc = { automatic = true; dates = "weekly"; options = "--delete-older-than 7d"; };

  system.stateVersion = "22.05";
}
