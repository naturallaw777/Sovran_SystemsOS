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

	nix-bitcoin.onionServices.bitcoind.enable = true;
	nix-bitcoin.onionServices.electrs.enable = true;

	services.lnd = {
		enable = true;
	};

	services.lightning-loop = {
		enable = true;
	};

	services.lightning-pool = {
		enable = true;
	};

	services.rtl = {
		enable = true;
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
	
}
