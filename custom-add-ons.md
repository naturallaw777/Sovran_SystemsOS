## Custom Add-ons for your Sovran Pro

Add-ons are extra features you can have installed before your Sovran Pro is shipped to you. 

1. There is also Bitcoin Knots Node available to be added instead of the regular Bitcoin Node. Bitcoin Knots allows a special filter to block unwanted, unusable, erroneous data on the Bitcoin Timechain chain.

https://bitcoinknots.org


2. By default Sovran_SystemsOS runs LND as the default Lightning node software for BTCpayserver. You are now able to run CLN as the backend to BTCpayserver instead of LND.

https://blockstream.com/lightning/


3. There is Mempool to be added on via a Tor connection.

https://github.com/mempool/mempool


The code will be installed in the `custom.nix` file.


The code for Bitcoin Knots is as follows:

```nix
services.bitcoind.package = pkgs.bitcoind-knots;
```


The code for CLN for BTCpayserver backend is as follows:

```nix
services.btcpayserver.lightningBackend = mkForce "clightning";
```

The code for Mempool is as follows:

```nix
services.mempool.enable = true;
```

