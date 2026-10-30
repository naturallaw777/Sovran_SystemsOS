# ── Pillow security floor for Matrix Synapse ──────────────────────────────────
#
# This is NOT a NixOS module.  It is imported by modules/synapse.nix, which
# applies `.overlay` to nixpkgs and asserts on `.version`.
#
# Why this file exists
# --------------------
# Synapse is the only Pillow consumer in Sovran_SystemsOS: nixpkgs builds
# matrix-synapse-unwrapped against `python3Packages.pillow`.  Synapse itself
# only declares `pillow>=10.0.1`, so there is no dependency-resolution
# conflict to fix here — *any* modern Pillow satisfies it.  The problem is
# purely that the Pillow the pinned nixpkgs ships is too old.
#
# Security floor (October 2026)
# -----------------------------
# Pillow 13.0.0 (2026-10-16) is the only release that fixes:
#   • CVE-2026-112900 — EPS filename argument injection into Ghostscript,
#     CVSS v4.0 9.2, affects every release from 2.6.0 through 12.3.0.
#   • CVE-2026-112398 — FlashPix heap overflow (code execution from a crafted
#     file).
#   • The accompanying TIFF and JPEG memory-corruption fixes,
#     ~40 advisories in total.  There is no 12.x backport: 13.0.0 or nothing.
#
#   Exposure note: Synapse's Pillow use is thumbnailing and image metadata.
#   Ghostscript is not in Synapse's environment, and Synapse hands Pillow a
#   temporary file object rather than an attacker-supplied filename, so the
#   EPS/Ghostscript RCE is effectively unreachable on this system.  The
#   decoder memory-corruption bugs are the ones a federated homeserver — which
#   stores untrusted uploaded media — can plausibly reach.  Patch it, but this
#   is not a five-alarm fire.
#
# Why a backport instead of a flake update
# ----------------------------------------
#   nixpkgs master still ships pillow 12.3.0 at the rev this flake pins
#   (flake.lock nixpkgs_2 = 31ecbaca1bdefa45dffc409f0250bd8039ea0010,
#   2026-10-27).  The 13.0.0 bump is merged into `staging`
#   (NixOS/nixpkgs#575689, 2026-10-19) and backported to release-26.05
#   (#576110, 2026-10-20), but staging-next has not been merged into master
#   yet, so `nix flake update nixpkgs` does NOT pick it up today.
#
#   The nixpkgs-stable input (nixos-26.05,
#   6f06d204d8f2d8761d9da78778745974a3216381) already builds pillow 13.0.0.
#   The `hash` below is copied from that known-good build — verified to fetch
#   python-pillow 13.0.0 (see tests/pillow-security-eval.nix).
#
# Why the override is this small
# ------------------------------
#   The 12.3.0 -> 13.0.0 delta in nixpkgs is exactly `version` and `src.hash`;
#   buildInputs, build-system and the test suite are unchanged, so an
#   `overridePythonAttrs` bump is safe.  (Pillow 13.0.0 dropped Python 3.10;
#   nixpkgs builds Synapse on 3.11+, so that removal does not apply.)
#
# Scope and lifetime
# ------------------
#   Only the Python set that Synapse uses is touched, because the NixOS
#   matrix-synapse module is built from `pkgs.matrix-synapse-unwrapped` — its
#   own option docs say "use an overlay to override
#   pkgs.matrix-synapse-unwrapped" (services.matrix-synapse.package is
#   read-only).  pkgs.python3Packages — which the Sovran Hub is built from —
#   keeps the stock version, so the rebuild blast radius is one derivation,
#   not the whole Python closure.
#
#   This is self-disabling by derivation identity: once the pinned nixpkgs
#   ships pillow >= `version`, the `versionOlder` test below is false, the
#   override becomes a no-op, every derivation in Synapse's Python set is
#   identical to stock and the drvPath is unchanged — nothing is rebuilt.
#   When that happens, delete this file, its use in modules/synapse.nix and
#   tests/pillow-security-eval.nix.
#
# Verified against nixpkgs 31ecbaca1bde (see tests/pillow-security-eval.nix):
#     NIXPKGS=/path/to/nixpkgs nix-instantiate --eval --strict tests/pillow-security-eval.nix
{ lib, version ? "13.0.0", hash ? "sha256-7FHwvgfT40qiHmvcJFZN/FlOECE0YiqOLBEYCMugk+4=" }:

{
  inherit version;

  overlay = final: prev:
    let
      # NOTE 1: do not write `prev.python3.override { ... }` here — inside an
      # overlay that alias chain re-enters the package fixpoint and Nix dies
      # with "infinite recursion encountered" at pkgs/stdenv/booter.nix.
      # `prev.python3Packages.python` is the same interpreter, already
      # instantiated, so overriding its packageOverrides stays local.
      #
      # NOTE 2: do not test the stock Pillow version with
      # `prev.python3Packages.pillow` either.  Forcing a member of the Python
      # package scope through `prev` inside an overlay loads nixpkgs' by-name
      # `self`, which is the final fixpoint being built -> infinite recursion.
      # Reading `super.pillow` *inside* the scope (below) is safe.
      pinnedPython = prev.python3Packages.python.override {
        packageOverrides = _self: super: {
          pillow = super.pillow.overridePythonAttrs (
            old:
            if lib.versionOlder old.version version then
              {
                inherit version;
                src = prev.fetchFromGitHub {
                  owner = "python-pillow";
                  repo = "pillow";
                  # Same ref form as nixpkgs, so `hash` stays valid.
                  tag = version;
                  inherit hash;
                };
              }
            else
              { }
          );
        };
      };
    in
    {
      matrix-synapse-unwrapped = prev.matrix-synapse-unwrapped.override {
        python3Packages = pinnedPython.pkgs;
      };
    };
}
