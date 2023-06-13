{config, pkgs, lib, ...}:

let
	personalization = import ./personalization.nix;
	in
{
	services.onlyoffice = {
		enable = true;
		enableExampleServer = true;
		examplePort = 8100;
	};	
}