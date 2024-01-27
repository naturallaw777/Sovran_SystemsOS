{ config, pkgs, lib, ... }:

{
	nix-bitcoin.generateSecrets = true;
	
	services.bitcoind = {
		enable = true;
		dataDir = "/run/media/Second_Drive/BTCEcoandBackup/Bitcoin_Node";
		txindex = true;
		tor.proxy = true;
		disablewallet = true;
		extraConfig = ''
			peerbloomfilters=1
			server=1
		'';
	};

	systemd.services.bitcoind.wants = [ "network-online.target" ];

	nix-bitcoin.onionServices.bitcoind.enable = true;
	nix-bitcoin.onionServices.electrs.enable = true;
	nix-bitcoin.onionServices.rtl.enable = true;

	services.lnd = {
		enable = true;
		tor.enforce = true;
		tor.proxy = true;
	};

	services.lnd.macaroons.btcpayserver.permissions = lib.mkForce ''
			{"entity":"address","action":"write"},
			{"entity":"info","action":"read"},
			{"entity":"info","action":"write"},
			{"entity":"invoices","action":"read"},
			{"entity":"invoices","action":"write"},
			{"entity":"macaroon","action":"generate"},
			{"entity":"macaroon","action":"read"},
			{"entity":"macaroon","action":"write"},
			{"entity":"message","action":"read"},
			{"entity":"message","action":"write"},
			{"entity":"offchain","action":"read"},
			{"entity":"offchain","action":"write"},
			{"entity":"onchain","action":"read"},
			{"entity":"onchain","action":"write"},
			{"entity":"peers","action":"read"},
			{"entity":"peers","action":"write"},
			{"entity":"signer","action":"generate"},
			{"entity":"signer","action":"read"}
		'';

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

	services.rtl = {
		enable = true;
		tor.enforce = true;
		port = 3050;
		nightTheme = true;
		nodes = {
			lnd = {
				enable = true;
				loop = true;
			};
		reverseOrder = true;
		};
	};

	services.mempool.enable = true;

	nix-bitcoin.onionServices.mempool-frontend.enable = true;

	nix-bitcoin.onionServices.lnd.public = true;
	
	services.lnd.lndconnect = {
		enable = true;
		onion = true;
	};
	
	services.charge-lnd.enable = true;

	services.btcpayserver.lightningBackend = "lnd";
		
	services.electrs = {
		enable = true;
		tor.enforce = true;
		dataDir = "/run/media/Second_Drive/BTCEcoandBackup/Electrs_Data";
		};
	
	services.btcpayserver = {
		enable = true;
		};
		
	nix-bitcoin.nodeinfo.enable = true;
		
	nix-bitcoin.operator = {
		enable = true;
		name = "free";
	};

	nix-bitcoin.useVersionLockedPkgs = true;
	
}
