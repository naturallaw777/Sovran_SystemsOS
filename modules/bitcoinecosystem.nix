{ config, pkgs, lib, ... }:

{
	
	## Bitcoind
	
	services.bitcoind = {
		enable = true;
    package = pkgs.stable.bitcoind-knots;
		dataDir = "/run/media/Second_Drive/BTCEcoandBackup/Bitcoin_Node";
		txindex = true;
		tor.proxy = true;
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



	## CLN
	
	services.clightning = {
		enable = true;
		tor.proxy = true;
		tor.enforce = true;
		port = 9737;
	};
	
	nix-bitcoin.onionServices.clightning.public = true;


	services.clightning.replication = {
		enable = true;
		local.directory = "/run/media/Second_Drive/BTCEcoandBackup/clightning_db_backup";
		encrypt = false;
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
	
	services.lightning-loop = {
		enable = true;
		tor.enforce = true;
		tor.proxy = true;
	};

	services.lightning-pool = {
		enable = true;
		tor.enforce = true;
		tor.proxy = true;
	};
	

	## RTL
	
	services.rtl = {
		enable = true;
		tor.enforce = true;
		port = 3050;
		nightTheme = true;
		nodes = {
			clightning = {
				enable = true;
				extraConfig = {
					Settings = {
						enableOffers = true;
					};
				};
			};
		
			lnd = {
				enable = true;
				loop = true;
			};
		
		reverseOrder = true;
		
		};
	};

	## Lndconnect

	services.lnd.lndconnect = {
		enable = true;
		onion = true;
	};

	services.clightning.plugins.clnrest = {
		enable = true;
			lnconnect = {
				enable = true;
				onion = true;
			};
	};
	

	## BTCpay Server
	
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

	nix-bitcoin.useVersionLockedPkgs = true;
	
}
