{ config, pkgs, lib, ... }:


let

	custom-php = pkgs.php83.buildEnv {
		extensions = { enabled, all }: enabled ++ (with all; [ bz2 apcu redis imagick memcached ]);
		extraConfig = ''
			
			display_errors = On
			display_startup_errors = On
			max_execution_time = 10000
			max_input_time = 3000
			memory_limit = 1G;
			opcache.enable=1;
			opcache.memory_consumption=512;
			opcache_revalidate_freq = 240;
			opcache.max_accelerated_files=20000;
			post_max_size = 3G
			upload_max_filesize = 3G
			apc.enable_cli=1
			opcache.interned_strings_buffer = 64
			redis.session.locking_enabled=1
			redis.session.lock_retries=-1
			redis.session.lock_wait_time=10000
			
		'';
	};
in

{	
	users.users = {

		php = {
			isSystemUser = true;
			createHome = false;
			uid = 7777;
		};
	};

	users.users.php.group = "php";
	
	users.groups.php = {};

	environment.systemPackages = with pkgs; [
		
		custom-php
	];

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
}
