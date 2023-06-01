{ config, pkgs, lib, ... }:

{

	imports = [	
		./configuration.nix
		./synapse.nix
		./coturn.nix
		./bitcoinecosystem.nix
		./vaultwarden.nix
		/etc/nixos/hardware-configuration.nix
		];
}