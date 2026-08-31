{
	description = "The Ultimate Sovran_SystemsOS Configuration from Sovran Systems";

	inputs = {
		nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
		nixvim.url = "github:nix-community/nixvim";
		btc-clients.url = "github:emmanuelrosa/btc-clients-nix";
		nixpkgs-stable.url = "github:nixos/nixpkgs/nixos-26.05";

		# Bitcoin / Lightning stack — standalone flake, consumed as a module.
		sovran-bitcoin.url = "github:naturallaw777/Sovran_Bitcoin";
	};

	outputs = { self, nixpkgs, nixvim, btc-clients, nixpkgs-stable, sovran-bitcoin, ... }:

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
				{ nixpkgs.hostPlatform = "x86_64-linux"; nixpkgs.overlays = [ overlay-stable ]; }
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
				./modules/sovran-bitcoin-integration.nix
				nixvim.nixosModules.nixvim
			];
		};

		nixosModules.Sovran_SystemsOS = { pkgs, lib, config, ... }: {
			imports = [
				({ config, pkgs, ... }: {
					nixpkgs.overlays = [ overlay-stable ];
				})
				./configuration.nix
				sovran-bitcoin.nixosModules.default
				./modules/sovran-bitcoin-integration.nix
				nixvim.nixosModules.nixvim
			];
			config = {
				environment.systemPackages = with pkgs; [
					btc-clients.packages.${pkgs.system}.bisq
					btc-clients.packages.${pkgs.system}.bisq2
					btc-clients.packages.${pkgs.system}.sparrow
				];
			};
		};

		checks.x86_64-linux = let
			pkgs = import nixpkgs {
				system = "x86_64-linux";
			};
		in {
			# Bitcoin hardening and package checks now live in the Sovran_Bitcoin flake.
			# Run them with: nix build github:naturallaw777/Sovran_Bitcoin#checks.x86_64-linux
		};
	};
}
