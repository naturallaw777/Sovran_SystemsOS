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


---

#### The code will be installed in the `custom.nix` file located at `/etc/nixos/custom.nix` from the initial setup.

If you would like to add in these features yourself, then open the *terminal* app and type or paste in

```bash
ssh root@localhost
```
Type in the password in the diaolog box if necessary. It is the same password to run the Sovran_Systems_Updater app.

Then press enter.

Next, type or paste in
```bash
nano /etc/nixos/custom.nix
```
Then press enter.

Next type or paste the codes below *(Sovran_SystemsOS Features)* into the termainl/nano window.

Once done, press `ctr s` then `ctr x` to save and exit.

Last, type or paste in
```bash
nixos-rebuild switch --impure
```
Then press enter.

After it is done bulding, reboot your Sovran Pro typeing or pasting in
```bash
reboot
```


---

### Sovran_SystemsOS Feature Set (All Features are off by default)

1. The code to enable Bitcoin Core is as follows:

```nix
sovran_systemsOS.features.bitcoin-core = lib.mkForce true;
```

2. The code to enable BIP-110 is as follows:

```nix
sovran_systemsOS.features.bip110 = lib.mkForce true;
```

3. The code to enable Mempool is as follows:

```nix
sovran_systemsOS.features.mempool = lib.mkForce true;
```

4. The code to enable Haven Relay is as follows (also Haven will need a new domain to work):

```nix
sovran_systemsOS.features.haven = lib.mkForce true;
sovran_systemsOS.nostr_npub = "pasteyournpubhere";
```

5. The code to enable Element Calling is as follows (also Element Calling will need a new domain to work):

```nix
sovran_systemsOS.features.element-calling = lib.mkForce true;
```

6. The code to enable Gnome Remote Desktop is as follows:

```nix
sovran_systemsOS.features.rdp = lib.mkForce true;
```
Next, in a open the terminal app and in the new window paste this in:

```bash
ssh root@localhost
```
Press enter

Type in the password if required. It will be the same password to run the Sovran_SystemsOS_Updater app.

Last, paste in this command to see the log in information to log in from any RDP client software (i.e. Remmina) from any computer on your home network
```bash
cat /var/lib/gnome-remote-desktop/rdp-credentials
```



