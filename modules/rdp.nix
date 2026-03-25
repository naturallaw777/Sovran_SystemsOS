{ config, pkgs, lib, ... }:

let
  cfg = config.sovran_systemsOS.features.rdp;
in
lib.mkIf cfg {

  services.gnome.gnome-remote-desktop.enable = true;

  networking.firewall.allowedTCPPorts = [ 3389 ];

  environment.systemPackages = with pkgs; [
    freerdp
  ];

  # Ensure correct directory ownership declaratively
  systemd.tmpfiles.rules = [
    "d /var/lib/gnome-remote-desktop 0700 gnome-remote-desktop gnome-remote-desktop -"
  ];

 systemd.services.grd-cert = {
  description = "GRD TLS cert";

  wantedBy = [ "multi-user.target" ];

  serviceConfig.Type = "oneshot";

  script = ''
    CERT_DIR=/var/lib/gnome-remote-desktop

    if [ ! -f "$CERT_DIR/rdp-tls.key" ]; then
      ${pkgs.util-linux}/bin/runuser -u gnome-remote-desktop -- \
        ${pkgs.freerdp}/bin/winpr-makecert -silent -rdp \
        -path "$CERT_DIR" rdp-tls
    fi
  '';
};

  systemd.user.services.grd-setup = {
    description = "GNOME Remote Desktop setup";

    wantedBy = [ "default.target" ];
    after = [ "graphical-session.target" ];

    serviceConfig.Type = "oneshot";

    script = ''
      set -euo pipefail

      CERT_DIR=/var/lib/gnome-remote-desktop

      ${pkgs.gnome-remote-desktop}/bin/grdctl rdp set-tls-key "$CERT_DIR/rdp-tls.key"
      ${pkgs.gnome-remote-desktop}/bin/grdctl rdp set-tls-cert "$CERT_DIR/rdp-tls.crt"
      ${pkgs.gnome-remote-desktop}/bin/grdctl rdp enable

      if ! ${pkgs.gnome-remote-desktop}/bin/grdctl rdp show | grep -q username; then
        ${pkgs.gnome-remote-desktop}/bin/grdctl rdp set-credentials "free" "a"
      fi
    '';
  };

}
