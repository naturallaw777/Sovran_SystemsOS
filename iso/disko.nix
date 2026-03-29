{ device ? "/dev/sda", dataDevice ? "", ... }:

{
  disko.devices = {
    disk = {
      main = {
        type = "disk";
        device = builtins.toString device;
        content = {
          type = "gpt";
          partitions = {
            ESP = {
              priority = 1;
              name = "ESP";
              start = "1M";
              end = "512M";
              type = "EF00";
              content = {
                type = "filesystem";
                format = "vfat";
                mountpoint = "/boot/efi";
                mountOptions = [ "umask=0077" "defaults" ];
              };
            };
            root = {
              name = "root";
              start = "512M";
              end = "100%";
              content = {
                type = "filesystem";
                format = "ext4";
                mountpoint = "/";
                extraArgs = [ "-L" "sovran_systemsos" ];
              };
            };
          };
        };
      };
    } // (if dataDevice != "" then {
      data = {
        type = "disk";
        device = builtins.toString dataDevice;
        content = {
          type = "gpt";
          partitions = {
            primary = {
              name = "primary";
              start = "1M";
              end = "100%";
              content = {
                type = "filesystem";
                format = "ext4";
                mountpoint = "/run/media/Second_Drive";
                extraArgs = [ "-L" "BTCEcoandBackup" ];
              };
            };
          };
        };
      };
    } else {});
  };
}