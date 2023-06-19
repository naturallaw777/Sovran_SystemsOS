{config, pkgs, lib, ...}:

let
	personalization = import ./personalization.nix;
	in
{
	services.onlyoffice = {
		enable = true;
		jwtSecretFile = "${personalization.onlyofficejwtSecretFile}";
	};	

	services.nginx.defaultSSLListenPort = 9443;
	services.nginx.defaultHTTPListenPort = 9080;


	services.epmd.listenStream = "127.0.0.7:4369";

}

