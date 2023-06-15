{config, pkgs, lib, ...}:

let
	personalization = import ./personalization.nix;
	in
{
	services.onlyoffice = {
		enable = true;
		#jwtSecretFile = "${personalization.onlyofficejwtSecretFile}";
		jwtSecretFile = "${age.secrets.onlyofficejwtSecretFile.file}";
	};	

	services.nginx.defaultSSLListenPort = 9443;
	services.nginx.defaultHTTPListenPort = 9080;

}

