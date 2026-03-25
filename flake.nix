{
	description = "The Ultimate Sovran_SystemsOS Configuration from Sovran Systems";

	inputs = {
		
		nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

		nix-bitcoin.url = "github:fort-nix/nix-bitcoin/release";
		
		agenix.url = "github:ryantm/agenix";

		agenix.inputs.darwin.follows = "";

		nixvim.url = "github:nix-community/nixvim";

		btc-clients.url = "github:emmanuelrosa/btc-clients-nix";

		nixpkgs-stable.url = "github:nixos/nixpkgs/nixos-24.11";

    bip110.url = "github:emmanuelrosa/bitcoin-knots-bip-110-nix";

	};

	outputs = { self, nixpkgs, nix-bitcoin, nixvim, agenix, btc-clients, nixpkgs-stable, bip110, ... }:

	let 
		
    system = "x86_64-linux";

		overlay-stable = final: prev: {

			stable = import nixpkgs-stable {
				inherit system;
				config.allowunfree = true;

			};

		};

	in

{ 
		
  nixosConfigurations.nixos = nixpkgs.lib.nixosSystem {
			
	  inherit system;
  
  };
		
  nixosModules.Sovran_SystemsOS = { pkgs, lib, config, ... }: {

    imports = [
      ({ config, pkgs, ... }: {
        nixpkgs.overlays = [ overlay-stable ];
      })

      ./configuration.nix
      nix-bitcoin.nixosModules.default
      agenix.nixosModules.default
      nixvim.nixosModules.nixvim
    ];

    config = {
      environment.systemPackages = with pkgs; [
        btc-clients.packages.${pkgs.system}.bisq
        btc-clients.packages.${pkgs.system}.bisq2
        btc-clients.packages.${pkgs.system}.sparrow
      ];

    sovran_systemsOS.bip110.package =
      bip110.packages.${pkgs.system}.bitcoind-knots-bip-110;
    };
  };
}
