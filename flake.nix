{
	description = "The Ultimate Sovran_SystemsOS Configuration from Sovran Systems";

	inputs = {
		nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
		nix-bitcoin.url = "github:fort-nix/nix-bitcoin/release";
		nixvim.url = "github:nix-community/nixvim";
		btc-clients.url = "github:emmanuelrosa/btc-clients-nix";
		nixpkgs-stable.url = "github:nixos/nixpkgs/nixos-24.11";
		bip110.url = "github:emmanuelrosa/bitcoin-knots-bip-110-nix";
	};

	outputs = { self, nixpkgs, nix-bitcoin, nixvim, btc-clients, nixpkgs-stable, bip110, ... }:

	let
		overlay-stable = final: prev: {
			stable = import nixpkgs-stable {
				system = prev.stdenv.hostPlatform.system;
				config.allowUnfree = true;
			};
		};
	in
	{
		nixosConfigurations.nixos = nixpkgs.lib.nixosSystem {
			modules = [
				{ nixpkgs.hostPlatform = "x86_64-linux"; }
			];
		};

		nixosConfigurations.sovran-iso = nixpkgs.lib.nixosSystem {
			system = "x86_64-linux";
			modules = [
				({ config, pkgs, ... }: {
					nixpkgs.overlays = [ overlay-stable ];
				})
				./iso.nix
				nix-bitcoin.nixosModules.default
				nixvim.nixosModules.nixvim
			];
		};

		nixosModules.Sovran_SystemsOS = { pkgs, lib, config, ... }: {
			imports = [
				({ config, pkgs, ... }: {
					nixpkgs.overlays = [ overlay-stable ];
				})
				./configuration.nix
				nix-bitcoin.nixosModules.default
				nixvim.nixosModules.nixvim
			];
			config = {
				environment.systemPackages = with pkgs; [
					btc-clients.packages.${pkgs.system}.bisq
					btc-clients.packages.${pkgs.system}.bisq2
					btc-clients.packages.${pkgs.system}.sparrow
				];
				sovran_systemsOS.packages.bip110 = bip110.packages.${pkgs.system}.bitcoind-knots-bip-110;
			};
		};
	};
}
