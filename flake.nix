{
	description = "The Ultimate Sovran_SystemsOS Configuration for the Sovran Pro from Sovran Systems";

	inputs = {
		
		nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

		nix-bitcoin.url = "github:fort-nix/nix-bitcoin/release";
		
		agenix.url = "github:ryantm/agenix";

		agenix.inputs.darwin.follows = "";

		nixvim.url = "github:nix-community/nixvim";

		bisq1.url = "github:emmanuelrosa/bisq-for-nixos";

		nixpkgs-stable.url = "github:nixos/nixpkgs/nixos-24.11";

		btcpayserver-new.url = "github:Dreaming-Codes/nixpkgs/update-btcpayserver";

		

	};

	outputs = { self, nixpkgs, nix-bitcoin, nixvim, agenix, bisq1, nixpkgs-stable, btcpayserver-new, ... }: 

	let 
		system = "x86_64-linux";

		overlay-stable = final: prev: {

			stable = import nixpkgs-stable {
				inherit system;
				config.allowunfree = true;

			};

		};

		overlay-btcpaynew = final: prev: {
			
			new-btcpaynew = import btcpayserver-new {
				inherit system;
				config.allowunfree = true;
			};
		};
	in

	{ 
		
	nixosConfigurations.nixos = nixpkgs.lib.nixosSystem {
			
		inherit system;


		};
		
		nixosModules.Sovran_SystemsOS = { pkgs, ... }: {

			imports = [

				({ config, pkgs, ... }: { nixpkgs.overlays = [ overlay-stable overlay-btcpaynew ]; })

				./configuration.nix

				nix-bitcoin.nixosModules.default

				agenix.nixosModules.default

				nixvim.nixosModules.nixvim

 			];
			
			environment.systemPackages = with pkgs; [
				bisq1.packages.x86_64-linux.bisq-desktop
			];

		};
	};
}
