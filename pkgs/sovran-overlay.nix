# Sovran overlay — provides packages not in nixpkgs or needing overrides
# All Bitcoin packages are now sourced from nixpkgs (unstable) directly.
# This overlay only fills gaps where nixpkgs is missing/broken.
final: prev: let
  # lndinit is not in nixpkgs — vendor it from nix-bitcoin source
  lndinit = prev.buildGoModule rec {
    pname = "lndinit";
    version = "0.1.3-beta";
    src = prev.fetchFromGitHub {
      owner = "lightninglabs";
      repo = pname;
      rev = "v${version}";
      sha256 = "sha256-sO1DpbppCurxr9g9nUl9Vx82FJK1mTcUw3rY1Fm1wEU=";
    };
    vendorHash = "sha256-El44BS5Bu0K/klMxkajciU/R6uqiXBMOiLN536QztbE=";
    subPackages = [ "." ];
    meta = with prev.lib; {
      description = "Wallet initializer utility for lnd (vendored from nix-bitcoin)";
      homepage = "https://github.com/lightninglabs/lndinit";
      license = licenses.mit;
    };
  };

  # netns-exec stub — netns isolation is stubbed, this is no-op
  # If not needed, stub it to coreutils
  netns-exec = prev.writeShellScriptBin "netns-exec" ''
    exec "$@"
  '';

  # nbxplorer is needed by btcpayserver but was removed from nixpkgs in some versions
  # Use nixpkgs version if available, otherwise build from nix-bitcoin pin
  nbxplorer = prev.nbxplorer or (prev.callPackage ./nbxplorer.nix {} );
in {
  inherit lndinit netns-exec;
  # Re-expose nbxplorer only if missing
  nbxplorer = if prev ? nbxplorer then prev.nbxplorer else nbxplorer;
}
