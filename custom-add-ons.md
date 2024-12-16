## Custom Add-ons for your Sovran Pro

Add-ons are extra features you can have installed before your Sovran Pro is shipped to you. 


1. There is Jitsi Meet that is available to be added on. Jitsi is a video conference software in which you send a web link to a video conference and anyone can join. 

https://jitsi.org


2. There is also Bitcoin Knots Node available to be added instead of the regular Bitcoin Node. Bitcoin Knots allows a special filter to block unwanted, unusable, erroneous, yet harmless data on the Bitcoin Block chain.

https://bitcoinknots.org


3. By default Sovran_SystemsOS runs LND as the default Lightning node software for BTCpayserver. You are now able to run CLN as the backend to BTCpayserver instead of LND.

https://blockstream.com/lightning/

4. There is Mempool to be added on via a Tor connection.

https://github.com/mempool/mempool


The code will be installed in the `custom.nix` file.


The code for Jitsi Meet is as follows:

```nix
systemd.services.jitsi-videobridge-helper = {
    
    script = ''
     
     systemctl restart jitsi-videobridge2 jicofo jibri   
     
    '';

    unitConfig = {
      Type = "simple";
      After = "btcpayserver.service";
      Requires = "network-online.target";
    };
     
    serviceConfig = {
      RemainAfterExit = "yes";
      Type = "oneshot";
    };

    wantedBy = [ "multi-user.target" ];
  
  };


  services.jitsi-videobridge.config = {
    videobridge = {
      http-servers = {
        private = {
          port = 8090;   
        };
      };
    };
  };

  services.jitsi-meet = {
    enable = true;
    hostName = "**CUSTOM_DOMAIN_NAME**";
    config = {
      enableWelcomePage = false;
      prejoinPageEnabled = true;
      defaultLang = "en";
      liveStreamingEnabled = false;
      fileRecordingsEnabled = true;
      fileRecordingsServiceEnabled = true;
      localRecording = {
        enable = true;
        notifyAllParticipants = true;
      };
    };
      
    interfaceConfig = {
      SHOW_JITSI_WATERMARK = false;
      SHOW_WATERMARK_FOR_GUESTS = false;
    };
  };


  services.jitsi-meet.caddy.enable = true;
  services.jitsi-meet.nginx.enable = false;
  services.jitsi-videobridge.openFirewall = true;
  services.jitsi-meet.jibri.enable = true;
  services.jibri.config = {
    recording = {
      recordings-directory = "/run/media/Second_Drive/BTCEcoandBackup/Jitsi_Recordings";
    };
    

    ffmpeg = {
      resolution = "1280x720";
      framerate = 30;
      video-encode-preset = "ultrafast";
      h264-constant-rate-factor = 40; 
    
    };
  
  };
  
  
  services.jitsi-videobridge.nat.publicAddress = builtins.readFile /var/lib/secrets/external_ip;
  services.jitsi-videobridge.nat.localAddress = builtins.readFile /var/lib/secrets/internal_ip;

  services.cron = {
	 enable = true;
	 systemCronJobs = [
    "*/15 * * * * root /run/current-system/sw/bin/bash /var/lib/internal_ip/internal_ip.sh"
	 ];
  };
```


The code for Bitcoin Knots is as follows:

```nix
services.bitcoind.package = pkgs.bitcoind-knots;
```


The code for CLN for BTCpayserver backend is as follows:

```nix
services.btcpayserver.lightningBackend = mkForce "clightning";
```

The code for Mempool is as follows:

```nix
services.mempool.enable = true;
```

