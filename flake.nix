{
	description = "The Ultimate Sovran_SystemsOS Configuration from Sovran Systems";

	inputs = {
		nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
		nixvim.url = "github:nix-community/nixvim";
		btc-clients.url = "github:emmanuelrosa/btc-clients-nix";
		nixpkgs-stable.url = "github:nixos/nixpkgs/nixos-26.05";
		sovran-bitcoin.url = "github:naturallaw777/Sovran_Bitcoin";
		# TEMPORARY: remove this input and the overlay below once Brave Origin
		# reaches nixos-unstable.
		nixpkgs-brave.url = "github:NixOS/nixpkgs/master";
	};

	outputs = inputs@{ self, nixpkgs, nixvim, btc-clients, nixpkgs-stable, sovran-bitcoin, ... }:

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
				self.nixosModules.Sovran_SystemsOS
				./hardware-configuration.nix
				./role-state.nix
				./custom.nix
			];
		};

		nixosConfigurations.sovran_systemsos-iso = nixpkgs.lib.nixosSystem {
			modules = [
				{ nixpkgs.hostPlatform = "x86_64-linux"; nixpkgs.overlays = [ overlay-stable ]; }
				./iso/common.nix
				sovran-bitcoin.nixosModules.default
				nixvim.nixosModules.nixvim
			];
		};

		nixosModules.Sovran_SystemsOS = { pkgs, lib, config, ... }: {
			imports = [
				({ config, pkgs, ... }: {
					nixpkgs.overlays = [
						overlay-stable
						# TEMPORARY: use Brave Origin from nixpkgs master until it reaches
						# nixos-unstable; then remove this overlay and nixpkgs-brave above.
						(final: prev: {
							brave-origin = (import inputs.nixpkgs-brave {
								system = prev.stdenv.hostPlatform.system;
								config = prev.config;
							}).brave-origin;
						})
					];
				})
				./configuration.nix
				sovran-bitcoin.nixosModules.default
				./modules/sovran-bitcoin-integration.nix
				nixvim.nixosModules.nixvim
			];
			config = {
				environment.systemPackages = with pkgs; [
					btc-clients.packages.${pkgs.stdenv.hostPlatform.system}.bisq
					btc-clients.packages.${pkgs.stdenv.hostPlatform.system}.bisq2
					btc-clients.packages.${pkgs.stdenv.hostPlatform.system}.sparrow
				];
			};
		};
	};
}
