{ config, pkgs, lib, ... }:
{
  # Only enable what this machine needs
  sovran_systemsOS.services.wordpress.enable = true;
  sovran_systemsOS.services.nextcloud.enable = true;
  sovran_systemsOS.services.synapse.enable = true;
  # btcpayserver is NOT enabled — no domain file needed, no vhost created
}