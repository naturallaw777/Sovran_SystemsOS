{ config, lib, pkgs, ... }:

lib.mkIf config.sovran_systemsOS.features.sshd {

  # Extend to listen on all interfaces for remote access
  services.openssh.listenAddresses = lib.mkForce [
    { addr = "127.0.0.1"; port = 22; }
    { addr = "0.0.0.0"; port = 22; }
  ];

  # Only open port 22 when SSH is actually enabled
  networking.firewall.allowedTCPPorts = [ 22 ];

  # Fail2Ban protects SSH when it's active
  services.fail2ban = {
    enable = true;
    ignoreIP = [ "127.0.0.0/8" "10.0.0.0/8" "172.16.0.0/12" "192.168.0.0/16" ];
  };

}