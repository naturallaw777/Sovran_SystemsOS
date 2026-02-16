## Custom Add-ons for your Sovran Pro

Add-ons are extra features you can have installed before your Sovran Pro is shipped to you. 

1. Since Sovran_SystemsOS runs Bitcoin Knots by default as opposed to Bitcion Core, you can customize your Sovran Pro's Bitcoin node to run Bitcoin Core.

https://github.com/bitcoin/bitcoin


2. The Bitcoin Mempool can be added and can be accessed via Tor or on your local network.

https://github.com/mempool/mempool


The code will be installed in the `custom.nix` file.


The code for Bitcoin Core is as follows:

```nix
services.bitcoind.package = lib.mkForce config.nix-bitcoin.pkgs.bitcoind;
```


The code for Mempool is as follows:

```nix
services.mempool = {
    enable = true;
    frontend.enable = true;
};

services.mysql.package = lib.mkForce pkgs.mariadb;

nix-bitcoin.onionServices.mempool-frontend.enable = true;

services.caddy = {
    virtualHosts = {
        ":60847" = {
            extraConfig = ''
			    reverse_proxy :60845
				encode gzip zstd
			'';
		};
    };
};
```
