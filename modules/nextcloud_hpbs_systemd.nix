{config, pkgs, lib, ...}:

let
 
 personalization = import ./personalization.nix;

in

{

systemd.services.nextcloud_notify_push_hpbs = {
	  
	unitConfig = {
		Description = "Push server (High Preformance Back End) for Nextcloud Clients";
		Requires = "network-online.target";
	};
	   
	serviceConfig = {
		Enviornment = "PORT=7867";
		ExecStart = "/run/current-system/sw/bin/notify_push /var/lib/www/nextcloud/config/config.php";
		RemainAfterExit = "yes";
		Type = "notify";
		User = "caddy";
		Group = "php";
	};

	wantedBy = [ "multi-user.target" ];
	
	};


}
