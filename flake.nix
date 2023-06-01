{
	description = "The Ultimate Sovran Pro Configuration from Sovran Systems";

	inputs = {
		nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

		nix-bitcoin.url = "github:fort-nix/nix-bitcoin/release";
	};

	outputs = { self, nixpkgs, nix-bitcoin, ... }: 
		{
		
		nixosConfigurations.nixos = nixpkgs.lib.nixosSystem {
			system ="x86_64-linux";
		};
		
		nixosModules.Sovran_Pro = { pkgs, ... }: {
			
			imports = [

			./modules/modules.nix 

			nix-bitcoin.nixosModules.default
		
 			];			
		};
	};
}