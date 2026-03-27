{ config, pkgs, lib, ... }:

lib.mkIf config.sovran_systemsOS.features.bitcoin {
	
	## Bitcoind
	
	services.bitcoind = {
		enable = true;
    package = config.nix-bitcoin.pkgs.bitcoind-knots;
		dataDir = "/run/media/Second_Drive/BTCEcoandBackup/Bitcoin_Node";
		txindex = true;
		tor.proxy = true;
    tor.enforce = true;
		disablewallet = true;
		extraConfig = ''
			peerbloomfilters=1
			server=1
		'';
	};

	nix-bitcoin.onionServices.bitcoind.enable = true;
	nix-bitcoin.onionServices.electrs.enable = true;
	nix-bitcoin.onionServices.rtl.enable = true;


	## Electrs
	
	services.electrs = {
		enable = true;
		tor.enforce = true;
		dataDir = "/run/media/Second_Drive/BTCEcoandBackup/Electrs_Data";
		};


  ## LND
	
	services.lnd = {
		enable = true;
		tor.enforce = true;
		tor.proxy = true;
		extraConfig = ''
			protocol.option-scid-alias=true
		'';
	};

	nix-bitcoin.onionServices.lnd.public = true;


  ## LNDconnect

	services.lnd.lndconnect = {
		enable = true;
		onion = true;
	};	

		
	## RTL
	
	services.rtl = {
		enable = true;
		tor.enforce = true;
		port = 3050;
		nightTheme = true;
		nodes = {
			lnd = {
				enable = true;
			};
		
		};
	};


	## BTCpayserver
	
	services.btcpayserver = {
		enable = true;
		};
		
	services.btcpayserver.lightningBackend = "lnd";

	
	## System

	nix-bitcoin.generateSecrets = true;

	nix-bitcoin.nodeinfo.enable = true;
		
	nix-bitcoin.operator = {
		enable = true;
		name = "free";
	};

	nix-bitcoin.useVersionLockedPkgs = false;
	
}
