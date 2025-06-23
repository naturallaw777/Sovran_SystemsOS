{ config, pkgs, lib, ... }:


let
	personalization = import ./modules/personalization.nix;		
in

{
	
	imports =
		
		[ 
			 
			./modules/modules.nix

		];

	# Bootloader.
	boot.loader.systemd-boot.enable = true;
	boot.loader.efi.canTouchEfiVariables = true;
	boot.loader.efi.efiSysMountPoint = "/boot/efi";
	boot.kernelPackages =  pkgs.linuxPackages_latest;

	# Enable Automount without Fail for Internal Drive.
	fileSystems."/run/media/Second_Drive" = {
		device = "LABEL=BTCEcoandBackup";
		fsType = "ext4";
		options = [ "nofail" ];
	};

	fileSystems."/boot/efi".options = [ "umask=0077" "defaults" ];

	nix.settings.experimental-features = [ "nix-command" "flakes" ];

	networking.hostName = "nixos"; # Define your hostname.

	# Enable networking
	networking.networkmanager.enable = true;

	# Set your time zone.
	time.timeZone = "America/Los_Angeles";

	# Select internationalisation properties.
	i18n.defaultLocale = "en_US.UTF-8";

	# Enable the X11 windowing system.
	services.xserver.enable = true;

	# Enable the GNOME Desktop Environment.
	services.displayManager.gdm.enable = true;
	services.desktopManager.gnome.enable = true;

	# Configure keymap in X11
	services.xserver.xkb = {
		layout = "us";
		variant = "";
	};

	# Enable CUPS to print documents.
	services.printing.enable = true;

	# Systemd Settings
	systemd.enableEmergencyMode = false;

	# Enable sound with pipewire.
	services.pulseaudio.enable = false;
	security.rtkit.enable = true;
	services.pipewire = {
		enable = true;
		alsa.enable = true;
		alsa.support32Bit = true;
		pulse.enable = true;
	};

	users.users = {
		free = {
			isNormalUser = true;
			description = "free";
			extraGroups = [ "networkmanager" ];
		};
	};

	# Enable automatic login for the user.
	services.displayManager.autoLogin.enable = true;
	services.displayManager.autoLogin.user = "free";

	# Workaround for GNOME autologin: https://github.com/NixOS/nixpkgs/issues/103746#issuecomment-945091229
	systemd.services."getty@tty1".enable = true;
	systemd.services."autovt@tty1".enable = true;

	# Allow Flatpak
	services.flatpak.enable = true;

	# Allow unfree packages
	nixpkgs.config.allowUnfree = true;

	nixpkgs.config.permittedInsecurePackages = [

		"jitsi-meet-1.0.8043"
	];
	
	# List packages installed in system profile. To search, run:
	# $ nix search wget
	environment.systemPackages = with pkgs; [
		(callPackage ./modules/systemd-manager_sovran_systems.nix {})
		git
		wget
		fish
		htop
		btop
		gnomeExtensions.dash-to-dock
		gnomeExtensions.vitals
		gnomeExtensions.pop-shell
		gnomeExtensions.just-perfection
		gnomeExtensions.appindicator
		gnomeExtensions.date-menu-formatter
		gnome-tweaks
		papirus-icon-theme
		ranger
		neofetch
		gedit
		matrix-synapse
		openssl
		pwgen
		aspell
		aspellDicts.en
		lm_sensors
		hunspell
		hunspellDicts.en_US
		synadm
		brave
		dua
		bitwarden-desktop
		gparted
		pv
		unzip
		parted
		screen
		zenity
		libargon2
		gnome-terminal
		libreoffice-fresh
		dig
		firefox
		element-desktop
		wp-cli

	];

	programs.nixvim = {
		enable = true;
		colorschemes.catppuccin.enable = true;
		plugins.lualine.enable = true;
  	};


	programs.bash.promptInit = "fish";
	
	programs.fish = {
		enable = true;
		promptInit = "neofetch";
	};


####### CADDY  #######
	services.caddy = {
		enable = true;
		user = "caddy";
		group = "root";
		email = "${personalization.caddy_email_for_acme}";

		virtualHosts = {
			"${personalization.wordpress_url}" = {
				 extraConfig = ''
					encode gzip zstd
					root * /var/lib/www/wordpress
					php_fastcgi unix//run/phpfpm/mypool.sock
					file_server browse
					'';
			};

			"${personalization.nextcloud_url}" = {
				extraConfig = ''
					encode gzip zstd
					root * /var/lib/www/nextcloud
					php_fastcgi unix//run/phpfpm/mypool.sock {
						trusted_proxies private_ranges
					}
					file_server
					redir /.well-known/carddav /remote.php/dav/ 301
					redir /.well-known/caldav /remote.php/dav/ 301
					header {
						Strict-Transport-Security max-age=31536000;
						}
					'';
			 };

			"${personalization.matrix_url}" = {
					extraConfig = ''
						reverse_proxy /_matrix/* http://localhost:8008
						reverse_proxy /_synapse/client/* http://localhost:8008
					'';
			};

			"${personalization.matrix_url}:8448" = {
					extraConfig = ''
							reverse_proxy http://localhost:8008
					'';
			};

			"${personalization.btcpayserver_url}" = {
					extraConfig = ''
						reverse_proxy http://localhost:23000
						encode gzip zstd
					'';
			};
			
			"https://${personalization.vaultwarden_url}" = {
					extraConfig = ''
						reverse_proxy http://localhost:8777
						encode gzip zstd
					'';
			};

			":3051" = {
					extraConfig = ''
						reverse_proxy :3050
						encode gzip zstd
					'';
			};
		};
	};

###### AGENIX ######
	age.identityPaths = [ "/root/.ssh/agenix/agenix-secret-keys" ];

	age.secrets.matrix_reg_secret = {

		file = /var/lib/agenix-secrets/matrix_reg_secret.age;
		mode = "770";
		owner = "matrix-synapse";
		group = "matrix-synapse";
	};



###### CREATE DATABASE (WORDPRESS, MATRIX_SYNAPSE, AND NEXTCLOUD) #######
	services.postgresql = {
		enable = true;
	};

	
	services.postgresql.authentication = lib.mkForce ''
			# Generated file; do not edit!
			# TYPE  DATABASE        USER            ADDRESS                 METHOD
			local   all             all                                     trust
			host    all             all             127.0.0.1/32            trust
			host    all             all             ::1/128                 trust
			'';


	services.mysql = {
		enable = true;
		package = pkgs.mariadb;
	};

	
	services.postgresql.initialScript = pkgs.writeText "begin-init.sql" ''
		CREATE ROLE "ncusr" WITH LOGIN PASSWORD '${personalization.nextclouddb}';
		CREATE DATABASE "nextclouddb" WITH OWNER "ncusr"
			TEMPLATE template0
			LC_COLLATE = "C"
			LC_CTYPE = "C";


		CREATE ROLE "matrix-synapse" WITH LOGIN PASSWORD '${personalization.matrixdb}';
		CREATE DATABASE "matrix-synapse" WITH OWNER "matrix-synapse"
			TEMPLATE template0
			LC_COLLATE = "C"
			LC_CTYPE = "C";    
	
	''
	;

	services.mysql.initialScript = pkgs.writeText "wordpress-init.sql" ''
		CREATE DATABASE wordpressdb;
		CREATE USER 'wpusr'@'localhost' IDENTIFIED BY '${personalization.wordpressdb}';
		GRANT ALL ON wordpressdb.* TO 'wpusr'@'localhost';
		FLUSH PRIVILEGES;
	''
	;


####### KEEP AWAKE for DISPLAY and HEADLESS #######
	services.displayManager.gdm.autoSuspend = false;

	systemd.sleep.extraConfig = ''
  		AllowSuspend=no
  		AllowHibernation=no
  		AllowHybridSleep=no
  		AllowSuspendThenHibernate=no
	'';


####### BACKUP TO INTERNAL DRIVE #######
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


####### CRON #######
	services.cron = {
		enable = true;
		systemCronJobs = [
		
		"*/5 * * * * caddy  /run/current-system/sw/bin/php -f /var/lib/www/nextcloud/cron.php"
		"*/15 * * * * root  /run/current-system/sw/bin/bash /var/lib/njalla/njalla.sh"
		"*/15 * * * * root  /run/current-system/sw/bin/bash /var/lib/external_ip/external_ip.sh"
		"0 0 * * 0 docker-user  yes | /run/current-system/sw/bin/docker system prune -a"
		
		];
	};


####### TOR #######
	services.tor = {
		enable = true;
		client.enable = true;
		torsocks.enable = true;
	};
	
	services.privoxy.enableTor = true;


####### Enable the OpenSSH daemon #######
	services.openssh = {
		enable = true;
		settings = {
			PasswordAuthentication = false;
			KbdInteractiveAuthentication = false;
			PermitRootLogin = "yes";
		};
	};


#######FailtoBan#######
	services.fail2ban = {
		enable = true;
		ignoreIP = [
		"127.0.0.0/8" 
		"10.0.0.0/8" 
		"172.16.0.0/12" 
		"192.168.0.0/16"
		"8.8.8.8"
		];
	};
	

####### Open ports in the firewall #######
	networking.firewall.allowedTCPPorts = [ 80 443 5349 8448 3050 3051 ];
	networking.firewall.allowedUDPPorts = [ 80 443 5349 8448 3050 3051 ];
	
	networking.firewall.allowedUDPPortRanges = [
		{ from=49152; to=65535; } # TURN relay
	];

	networking.firewall.enable = true;

	
####### AUTO COLLECT GARABAGE #######
	nix.gc = {
		automatic = true;
		dates = "weekly";
		options = "--delete-older-than 7d";
	};

	
	system.stateVersion = "22.05";

}
