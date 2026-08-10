{
  description = "Sovran Systems OS - A secure, self-hosted server OS";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    nixpkgs-stable.url = "github:nixos/nixpkgs/nixos-26.05";
    nixvim.url = "github:nix-community/nixvim";
    btc-clients.url = "github:emmanuelrosa/btc-clients-nix";
  };

  outputs = { self, nixpkgs, nixpkgs-stable, nixvim, btc-clients }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
      pkgs-stable = import nixpkgs-stable {
        inherit system;
        config.allowUnfree = true;
      };
    in
    {
      nixosConfigurations.nixos = nixpkgs.lib.nixosSystem {
        inherit system;
        specialArgs = { inherit pkgs-stable; };
        modules = [
          ./configuration.nix
          ./modules
          btc-clients.nixosModules.bitcoin
          nixvim.nixosModules.nixvim
        ];
      };
    };
}
