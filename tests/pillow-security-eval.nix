# Evaluation check for modules/pillow-security.nix
#
#   NIXPKGS=/path/to/nixpkgs nix-instantiate --eval --strict tests/pillow-security-eval.nix
#
# NIXPKGS must point at nixpkgs 31ecbaca1bde (the rev pinned in flake.lock as
# nixpkgs_2) or newer.  Nothing is compiled, but Pillow's *source* is a
# fixed-output derivation, so building `check.pillowSrcFetches` verifies that
# the hash in modules/pillow-security.nix really is Pillow 13.0.0:
#
#   NIXPKGS=/path/to/nixpkgs nix-build --no-out-link -A pillowSrcFetches \
#     tests/pillow-security-eval.nix
#
# Expected results on nixpkgs 31ecbaca1bde:
#   stock.synapsePillow      = "12.3.0"    <- what this system ships today
#   patched.synapsePillow    = "13.0.0"    <- the fix
#   patched.wrappedPillow    = "13.0.0"    <- the package NixOS actually runs
#   patched.hubPillow        = "12.3.0"    <- Hub's Python set untouched
#   guarded.isNoOp           = true        <- self-disabling guard works
let
  nixpkgsPath = builtins.getEnv "NIXPKGS";
  np =
    if nixpkgsPath == ""
    then throw "NIXPKGS is not set (point it at nixpkgs 31ecbaca1bde or newer)"
    else /. + nixpkgsPath;

  lib = import (np + "/lib");

  floor = import ../modules/pillow-security.nix { inherit lib; };

  # A floor below what nixpkgs already ships must reduce to a pure no-op.
  floorBelowStock = (import ../modules/pillow-security.nix {
    inherit lib;
    version = "12.0.0";
  }).overlay;

  mkPkgs = overlays: import np { system = "x86_64-linux"; inherit overlays; };

  # How the NixOS matrix-synapse module wraps the package for its service
  # (nixos/modules/services/matrix/synapse.nix: `wrapped = pkgs.matrix-synapse
  # .override { extras = wantedExtras; inherit (cfg) plugins; }`).
  wrap = pkgs: pkgs.matrix-synapse.override {
    extras = [ "systemd" "postgres" "url-preview" "cache-memory" ];
    plugins = [ ];
  };

  stock = mkPkgs [ ];
  patched = mkPkgs [ floor.overlay ];
  guarded = mkPkgs [ floorBelowStock ];
in
{
  check = {
    floor = floor.version;

    # ── What the pinned nixpkgs does on its own ─────────────────────────────
    stock.pillow = stock.python3Packages.pillow.version;
    stock.synapse = stock.matrix-synapse.version;
    stock.synapsePillow = stock.matrix-synapse.unwrapped.python.pkgs.pillow.version;

    # ── The overlay must move the Pillow that Synapse runs against ──────────
    patched.synapsePillow = patched.matrix-synapse.unwrapped.python.pkgs.pillow.version;
    patched.synapsePillowSrcTag = patched.matrix-synapse.unwrapped.python.pkgs.pillow.src.tag;
    patched.wrappedPillow = (wrap patched).unwrapped.python.pkgs.pillow.version;

    # ── ...and must not touch anything else ────────────────────────────────
    patched.synapseVersionUnchanged =
      patched.matrix-synapse.version == stock.matrix-synapse.version;
    patched.hubPillow = patched.python3Packages.pillow.version;
    patched.hubFastapiUnchanged =
      patched.python3Packages.fastapi.version == stock.python3Packages.fastapi.version;

    # ── Self-disabling: floor below stock => stock derivation, no rebuild ──
    guarded.synapsePillow = guarded.matrix-synapse.unwrapped.python.pkgs.pillow.version;
    guarded.isNoOp =
      guarded.matrix-synapse-unwrapped.drvPath == stock.matrix-synapse-unwrapped.drvPath;
  };

  # Fixed-output derivation: `nix-build -A pillowSrcFetches` must succeed and
  # the unpacked tree must report __version__ = 13.0.0.
  pillowSrcFetches = patched.matrix-synapse.unwrapped.python.pkgs.pillow.src;
}
