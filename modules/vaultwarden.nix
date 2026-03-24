{ config, pkgs, lib, ... }:

let
	personalization = import ./personalization.nix;
in

lib.mkIf config.sovran_systemsOS.features.vaultwarden {

	services.vaultwarden = {
		enable = true;
		    config = {

        		DOMAIN = "https://${personalization.vaultwarden_url}";
        		SIGNUPS_ALLOWED = false;
        		ROCKET_ADDRESS = "127.0.0.1";
        		ROCKET_PORT = 8777;
        		ROCKET_LOG = "critical";
        	};
		dbBackend = "sqlite";
		environmentFile = "/var/lib/secrets/vaultwarden/vaultwarden.env";
	};
}
