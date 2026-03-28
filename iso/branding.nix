{ config, pkgs, lib, ... }:

let
  theme = pkgs.callPackage ./plymouth-theme.nix {};
in
{
  boot.plymouth.enable = true;
  boot.plymouth.theme = "sovran";
  boot.plymouth.themePackages = [ theme ];
  boot.kernelParams = [ "quiet" "splash" ];
}