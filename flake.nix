{
	description = "The Ultimate Sovran_SystemsOS Configuration for the Sovran Pro from Sovran Systems";

	inputs = {
		
		nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

		nix-bitcoin.url = "github:fort-nix/nix-bitcoin/release";
		
		agenix.url = "github:ryantm/agenix";

		agenix.inputs.darwin.follows = "";

		nixvim.url = "github:nix-community/nixvim";

		bisq1.url = "github:emmanuelrosa/bisq-for-nixos";

	};

	outputs = { self, nixpkgs, nix-bitcoin, nixvim, agenix, ... }@attrs: { 
		
		nixosConfigurations.nixos = nixpkgs.lib.nixosSystem {
			
			system ="x86_64-linux";
			
			specialArgs = attrs;
		
		};
		
		nixosModules.Sovran_SystemsOS = { pkgs, ... }: {
			
			imports = [

				./configuration.nix

				nix-bitcoin.nixosModules.default

				agenix.nixosModules.default

				nixvim.nixosModules.nixvim

 			];
		};
	};
}
