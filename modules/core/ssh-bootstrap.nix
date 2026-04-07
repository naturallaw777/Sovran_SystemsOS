{ config, pkgs, lib, ... }:

let
  userName = "free";
  keyPath = "/home/${userName}/.ssh/factory_login";
  userExists = builtins.hasAttr userName config.users.users;
in
lib.mkIf userExists {

  systemd.tmpfiles.rules = [
    "d /root/.ssh 0700 root root -"
    "d /home/${userName}/.ssh 0700 ${userName} users -"
  ];

  systemd.services.ssh-passphrase-setup = {
    description = "Generate per-device SSH key passphrase";
    wantedBy = [ "multi-user.target" ];
    before = [ "factory-ssh-keygen.service" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    path = [ pkgs.pwgen pkgs.coreutils ];
    script = ''
      if [ ! -f "/var/lib/secrets/ssh-passphrase" ]; then
        mkdir -p /var/lib/secrets
        pwgen -s 20 1 > /var/lib/secrets/ssh-passphrase
        chmod 600 /var/lib/secrets/ssh-passphrase
      fi
    '';
  };

  systemd.services.factory-ssh-keygen = {
    description = "Generate factory SSH key for ${userName} if missing";
    wantedBy = [ "multi-user.target" ];
    after = [ "ssh-passphrase-setup.service" ];
    requires = [ "ssh-passphrase-setup.service" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    path = [ pkgs.openssh pkgs.coreutils ];
    script = ''
      if [ ! -f "${keyPath}" ]; then
        PASSPHRASE=$(cat /var/lib/secrets/ssh-passphrase)
        ssh-keygen -q -N "$PASSPHRASE" -t ed25519 -f "${keyPath}"
        chown ${userName}:users "${keyPath}" "${keyPath}.pub"
        chmod 600 "${keyPath}"
        chmod 644 "${keyPath}.pub"
      fi
    '';
  };

  systemd.services.factory-ssh-authorize = {
    description = "Authorize factory SSH key for root";
    wantedBy = [ "multi-user.target" ];
    after = [ "factory-ssh-keygen.service" ];
    requires = [ "factory-ssh-keygen.service" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    path = [ pkgs.coreutils ];
    script = ''
      if [ -f "${keyPath}.pub" ]; then
        PUB=$(cat "${keyPath}.pub")
        mkdir -p /root/.ssh
        touch /root/.ssh/authorized_keys
        grep -qxF "$PUB" /root/.ssh/authorized_keys || echo "$PUB" >> /root/.ssh/authorized_keys
        chmod 600 /root/.ssh/authorized_keys
      fi
    '';
  };
}
