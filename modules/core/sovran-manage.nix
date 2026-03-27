{ config, pkgs, lib, ... }:

let
  sovran-manage = pkgs.writeShellScriptBin "sovran-manage" (builtins.readFile ../../scripts/sovran-manage.sh);
in
{
  environment.systemPackages = [
    sovran-manage
    pkgs.pwgen
    pkgs.dig
    pkgs.curl
  ];
}