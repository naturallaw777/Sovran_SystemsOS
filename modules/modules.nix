{ config, pkgs, lib, ... }:

{

	imports = [	
		
		./php.nix
		./synapse.nix
		./coturn.nix
		./bitcoinecosystem.nix
		./vaultwarden.nix
		./Sovran_SystemsOS_File_Fixes_And_New_Services.nix
	
		];
}
