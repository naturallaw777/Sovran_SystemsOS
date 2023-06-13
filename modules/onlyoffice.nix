{config, pkgs, lib, ...}:

let
	personalization = import ./personalization.nix;
	in
{
	services.onlyoffice = {
		enable = true;
		hostname = "${personalization.onlyoffice_url}";
	};

	services.nginx.defaultSSLListenPort = 9443;
	services.nginx.defaultHTTPListenPort = 9080;

	security.acme = {
	  acceptTerms = true;
	  defaults.email = "cert+${personalization.caddy_email_for_zerossl}";
	  certs."${personalization.onlyoffice_url}" = {
	    webroot = "/var/lib/acme/challenges-com";
	    email = "cert+${personalization.caddy_email_for_zerossl}";
	    group = "nginx";
		};
	};
	
	users.users.nginx.extraGroups = [ "acme" ];

}