## Custom Add-ons for your Sovran Pro

Add-ons are extra features you can have installed before your Sovran Pro is shipped to you or you can install them yourself. 

1. Since Sovran_SystemsOS runs Bitcoin Knots by default as opposed to Bitcion Core, you can customize your Sovran Pro's Bitcoin node to run Bitcoin Core.

https://github.com/bitcoin/bitcoin

2. BIP-110 keeps Bitcoin more efficient as Peer to Peer Cash and you can run it along side your Bitocoin node.

https://github.com/bitcoin/bips/blob/master/bip-0110.mediawiki

3. The Bitcoin Mempool can be added and can be accessed via Tor or on your local network.

https://github.com/mempool/mempool

4. The Haven Relay for NOSTR (NOTES AND OTHER STUFF TRANSMITED BY RELAYS) is a Decenterized Social Media/File Sharing.

https://github.com/barrydeen/haven

5. You can run the new Element Voice and Video calling backend.

https://github.com/element-hq/element-call

6. You can run the Gnome Remote Desktop to view your desktop from another computer in the nextwork.

https://gitlab.gnome.org/GNOME/gnome-remote-desktop

#### The code will be installed in the `custom.nix` file.


1. The code for Bitcoin Core is as follows:

```nix
sovran_systemsOS.features.bitcoin-core = lib.mkForce true;
```

2. The code for BIP-110 is as follows:

```nix
sovran_systemsOS.features.bip110 = lib.mkForce true;
```

3. The code for Mempool is as follows:

```nix
sovran_systemsOS.features.mempool = lib.mkForce true;
```

4. The code for Haven Relay is as follows:

```nix
sovran_systemsOS.features.haven = lib.mkForce true;
sovran_systemsOS.nostr_npub = "pasteyournpubhere";
```

5. The code for Element Calling is as follows:

```nix
sovran_systemsOS.features.element-calling = lib.mkForce true;
```

6. The code for Gnome Remote Desktop is as follows:

```nix
sovran_systemsOS.features.rdp = lib.mkForce true;
```
Next in a new termianl window paste this in:

```bash
ssh root@localhost
```
Type in the password if required. It will be the same password to run the Sovran_SystemsOS_Updater app.

Next paste in these commands and make sure you add your own username and password
```bash
sudo -u gnome-remote-desktop winpr-makecert -silent -rdp -path /var/lib/gnome-remote-desktop rdp-tls
grdctl --system rdp set-tls-key /var/lib/gnome-remote-desktop/rdp-tls.key
grdctl --system rdp set-tls-cert /var/lib/gnome-remote-desktop/rdp-tls.crt
grdctl --system rdp enable
grdctl --system rdp set-credentials "custom-username" "custom-password"
```
Next restart Gnome-Remote-Desktop
```bash
systemctl restart gnome-remote-desktop
```
Last access Sovran_SystemsOS Desktop from any computer in your nextwork by using any software client that can connectsthrough RDP service.



