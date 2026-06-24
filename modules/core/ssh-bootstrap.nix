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
    description = "Generate or repair factory SSH key for ${userName}";
    wantedBy = [ "multi-user.target" ];
    after = [ "ssh-passphrase-setup.service" ];
    requires = [ "ssh-passphrase-setup.service" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    path = [ pkgs.openssh pkgs.coreutils ];
    script = ''
      PASSPHRASE=$(cat /var/lib/secrets/ssh-passphrase)

      generate_factory_key() {
        ssh-keygen -q -N "$PASSPHRASE" -t ed25519 -f "${keyPath}"
        chown ${userName}:users "${keyPath}" "${keyPath}.pub"
        chmod 600 "${keyPath}"
        chmod 644 "${keyPath}.pub"
      }

      if [ ! -f "${keyPath}" ]; then
        generate_factory_key
      elif ! ssh-keygen -y -P "$PASSPHRASE" -f "${keyPath}" >/dev/null 2>&1; then
        backup_suffix=$(date -u +%Y%m%d%H%M%S)
        backup_path="${keyPath}.bak-$backup_suffix"
        backup_index=0

        while [ -e "$backup_path" ] || [ -e "$backup_path.pub" ]; do
          backup_index=$((backup_index + 1))
          backup_path="${keyPath}.bak-$backup_suffix-$backup_index"
        done

        mv "${keyPath}" "$backup_path"

        if [ -f "${keyPath}.pub" ]; then
          mv "${keyPath}.pub" "$backup_path.pub"
        fi

        generate_factory_key
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
