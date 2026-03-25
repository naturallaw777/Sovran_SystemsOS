{ config, pkgs, lib, ... }:

  config.sovran_systemsOS.features.rdp {

    services.gnome.gnome-remote-desktop.enable = true;

    networking.firewall.allowedTCPPorts = [ 3389 ];

    environment.systemPackages = with pkgs; [
      freerdp
    ];
}




