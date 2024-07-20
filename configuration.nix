{ config, pkgs, lib, ... }:


let
	personalization = import ./modules/personalization.nix;
		
		
	custom-php = pkgs.php81.buildEnv {
		extensions = { enabled, all }: enabled ++ (with all; [ bz2 apcu redis imagick memcached ]);
		extraConfig = ''
			display_errors = On
			display_startup_errors = On
			max_execution_time = 6000
			max_input_time = 3000
			memory_limit = 8G;
			opcache.enable=1;
			opcache.memory_consumption=512;
			opcache_revalidate_freq = 240;
			opcache.max_accelerated_files=10000;
			auto_prepend_file = '/var/lib/www/wordpress/wordfence-waf.php'
			post_max_size = 3G
			upload_max_filesize = 3G
			opcache.interned_strings_buffer = 32
			apc.enable_cli=1
			redis.session.locking_enabled=1
			redis.session.lock_retries=-1
			redis.session.lock_wait_time=10000

		'';
	};
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
	services.xserver.displayManager.gdm.enable = true;
	services.xserver.desktopManager.gnome.enable = true;

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
	hardware.pulseaudio.enable = false;
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


####### PHP user for PHPFPM #######
		php = {
			isSystemUser = true;
			createHome = false;
			uid = 7777;
		};
	};

	users.users.php.group = "php";
	users.groups.php = {};

	# Enable automatic login for the user.
	services.displayManager.autoLogin.enable = true;
	services.displayManager.autoLogin.user = "free";

	# Workaround for GNOME autologin: https://github.com/NixOS/nixpkgs/issues/103746#issuecomment-945091229
	systemd.services."getty@tty1".enable = true;
	systemd.services."autovt@tty1".enable = true;


	# Fix the GNOME Desktop Environment Performance

	nixpkgs.config.allowAliases = false;

	nixpkgs.overlays = [
	# GNOME 46: triple-buffering-v4-46
		(final: prev: {
			gnome = prev.gnome.overrideScope (gnomeFinal: gnomePrev: {
				mutter = gnomePrev.mutter.overrideAttrs (old: {
					src = pkgs.fetchFromGitLab  {
						domain = "gitlab.gnome.org";
						owner = "vanvugt";
						repo = "mutter";
						rev = "triple-buffering-v4-46";
						hash = "sha256-nz1Enw1NjxLEF3JUG0qknJgf4328W/VvdMjJmoOEMYs=";
					};
				});
			});
		})
	];


	# Allow Flatpak
	services.flatpak.enable = true;

	# Allow unfree packages
	nixpkgs.config.allowUnfree = true;

	# List packages installed in system profile. To search, run:
	# $ nix search wget
	environment.systemPackages = with pkgs; [
		(callPackage ./modules/systemd-manager_sovran_systems.nix {})
		git
		wget
		librewolf
		fish
		htop
		btop
		gnomeExtensions.dash-to-dock
		gnomeExtensions.transparent-top-bar-adjustable-transparency
		gnomeExtensions.vitals
		gnomeExtensions.pop-shell
		gnomeExtensions.just-perfection
		gnomeExtensions.appindicator
		gnomeExtensions.date-menu-formatter
		gnome-tweaks
		papirus-icon-theme
		ranger
		sparrow
		bisq-desktop
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
		custom-php
		matrix-synapse-tools.synadm
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
		nextcloud-client
		firefox
		element-desktop

	];

	programs.bash.promptInit = "fish";
	programs.fish = {
		enable = true;
		promptInit = "neofetch";
	};


####### PHPFMP  #######
	services.phpfpm.pools = {
		mypool = {
			user = "caddy";
			group = "php";
			phpPackage = custom-php;
			settings = {
				"pm" = "dynamic";
				"pm.max_children" = 75;
				"pm.start_servers" = 10;
				"pm.min_spare_servers" = 5;
				"pm.max_spare_servers" = 20;
				"pm.max_requests" = 500;
				"clear_env" = "no";
			};
		};			
	};


####### CADDY  #######
	services.caddy = {
		enable = true;
		package = pkgs.caddy;
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
						php_fastcgi unix//run/phpfpm/mypool.sock
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
			};

	
	services.postgresql.initialScript = pkgs.writeText "begin-init.sql" ''
		CREATE ROLE "ncusr" WITH LOGIN PASSWORD '${personalization.age.secrets.nextclouddb.file}';
		CREATE DATABASE "nextclouddb" WITH OWNER "ncusr"
			TEMPLATE template0
			LC_COLLATE = "C"
			LC_CTYPE = "C";


		CREATE ROLE "matrix-synapse" WITH LOGIN PASSWORD '${personalization.age.secrets.matrixdb.file}';
		CREATE DATABASE "matrix-synapse" WITH OWNER "matrix-synapse"
			TEMPLATE template0
			LC_COLLATE = "C"
			LC_CTYPE = "C";    
	
	''
	;

	services.mysql.initialScript = pkgs.writeText "wordpress-init.sql" ''
		CREATE DATABASE wordpressdb;
		GRANT ALL ON *.* TO 'wpusr'@'localhost' IDENTIFIED BY '${personalization.age.secrets.wordpressdb.file}';
		FLUSH PRIVILEGES;
	''
	;


####### KEEP AWAKE for DISPLAY and HEADLESS #######
	services.xserver.displayManager.gdm.autoSuspend = false;
	services.power-profiles-daemon.enable = false;


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
