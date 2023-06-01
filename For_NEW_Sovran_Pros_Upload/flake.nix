{
	description = "The Ultimate Sovran Pro Configuration from Sovran Systems";

	inputs = {
		Sovran_Systems.url = "git+https://git.sovransystems.com/Sovran_Systems/Sovran_Pro";
	};

	outputs = { self, Sovran_Systems, ... }@inputs: {
		nixosConfigurations."nixos" = Sovran_Systems.inputs.nixpkgs.lib.nixosSystem {
			system = "x86_64-linux";
 			modules = [ Sovran_Systems.nixosModules.Sovran_Pro ];
		};
	};
}