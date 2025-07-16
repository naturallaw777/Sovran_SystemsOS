{ config, pkgs, lib, ... }:
    
{    
	
	systemd.services.postgresql.postStart = lib.mkForce '''';
	

}
