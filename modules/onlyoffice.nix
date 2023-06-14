{config, pkgs, lib, ...}:

let
	personalization = import ./personalization.nix;
	in
{
	services.onlyoffice = {
		enable = true;
		#hostname = "${personalization.onlyoffice_url}";
		examplePort = 8100;
		enableExampleServer = true;

	};	

	services.nginx.defaultSSLListenPort = 9443;
	services.nginx.defaultHTTPListenPort = 9080;

}

