# Fallback nbxplorer package if not in nixpkgs
# This is rarely needed — nixpkgs-unstable usually has it
{ lib, buildDotnetModule, fetchFromGitHub, dotnetCorePackages }:
buildDotnetModule rec {
  pname = "nbxplorer";
  version = "2.5.22";
  src = fetchFromGitHub {
    owner = "dgarage";
    repo = "NBXplorer";
    rev = "v${version}";
    sha256 = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";
  };
  projectFile = "NBXplorer/NBXplorer.csproj";
  nugetDeps = ./nbxplorer-deps.nix; # not needed if using nixpkgs version
  dotnet-sdk = dotnetCorePackages.sdk_8_0;
  dotnet-runtime = dotnetCorePackages.aspnetcore_8_0;
  meta = with lib; { description = "NBXplorer fallback"; license = licenses.mit; };
}
