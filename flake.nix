{
	description = "The Ultimate Sovran_SystemsOS Configuration for the Sovran Pro from Sovran Systems";

	inputs = {
		
		nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

		nix-bitcoin.url = "github:fort-nix/nix-bitcoin/release";
		
		agenix.url = "github:ryantm/agenix";

		agenix.inputs.darwin.follows = "";

		erosanix.url = "github:emmanuelrosa/erosanix";

	};

	outputs = { self, nixpkgs, nix-bitcoin, agenix, erosanix, ... }: 
		
		{
		
		nixosConfigurations.nixos = nixpkgs.lib.nixosSystem {
			system ="x86_64-linux";
		
		};
		
		nixosModules.Sovran_SystemsOS = { pkgs, ... }: {
			
			imports = [

				./configuration.nix

				(nixpkgs + "./modules/personalization.nix")

				nix-bitcoin.nixosModules.default

				agenix.nixosModules.default

 			];

 			environment.systemPackages = with pkgs; [
 			  
 			  erosanix.packages.x86_64-linux.sparrow
 			
 			];
		};
	};
}