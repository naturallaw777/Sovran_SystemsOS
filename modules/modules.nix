{ config, pkgs, lib, ... }:

{

	imports = [	

		./synapse.nix
		./coturn.nix
		./bitcoinecosystem.nix
		./vaultwarden.nix
		./onlyoffice.nix
		./Sovran_SystemsOS_File_Fixes_And_New_Services.nix
		
		];
}