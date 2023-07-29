{
	description = "Sovran_SystemsOS for the Sovran Pro from Sovran Systems";

	inputs = {
		
		Sovran_Systems.url = "git+https://git.sovransystems.com/Sovran_Systems/Sovran_SystemsOS";
	
	};

	outputs = { self, Sovran_Systems, ... }@inputs: {
		
		nixosConfigurations."nixos" = Sovran_Systems.inputs.nixpkgs.lib.nixosSystem {
			
			system = "x86_64-linux";
 			
 			modules = [ Sovran_Systems.nixosModules.Sovran_SystemsOS ];
		
		};
	
	};

}