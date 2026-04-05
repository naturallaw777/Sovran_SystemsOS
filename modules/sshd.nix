{ config, lib, pkgs, ... }:

lib.mkIf config.sovran_systemsOS.features.sshd {

  services.openssh = {
    enable = true;
    settings = {
      PasswordAuthentication = false;
      KbdInteractiveAuthentication = false;
      PermitRootLogin = "yes";
    };
  };

  # Only open port 22 when SSH is actually enabled
  networking.firewall.allowedTCPPorts = [ 22 ];

  # Fail2Ban protects SSH when it's active
  services.fail2ban = {
    enable = true;
    ignoreIP = [ "127.0.0.0/8" "10.0.0.0/8" "172.16.0.0/12" "192.168.0.0/16" ];
  };

}
