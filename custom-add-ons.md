## Custom Add-ons for your Sovran Pro

Add-ons are extra features you can have installed before your Sovran Pro is shipped to you. 

1. Since Sovran_SystemsOS runs Bitcoin Knots by default as opposed to Bitcion Core, you can customize your Sovran Pro or Sovran Pro Max node to run Bitcoin Core.

https://github.com/bitcoin/bitcoin


2. By default Sovran_SystemsOS runs LND as the default Lightning node software for BTCpayserver. You are now able to run CLN as the backend to BTCpayserver instead of LND.

https://blockstream.com/lightning/


3. There is Mempool to be added on via a Tor connection.

https://github.com/mempool/mempool


The code will be installed in the `custom.nix` file.


The code for Bitcoin Core is as follows:

```nix
services.bitcoind.package = mkForce config.nix-bitcoin.pkgs.bitcoind;
```


The code for CLN for BTCpayserver backend is as follows:

```nix
services.btcpayserver.lightningBackend = mkForce clightning;
```


The code for Mempool is as follows:

```nix
services.mempool.enable = true;
```

