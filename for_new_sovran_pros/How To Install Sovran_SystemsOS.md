# Sovran Systems does not offer any support of a DIY install of Sovran_SystemsOS. You are on your own. You can reach out to others in the matrix room https://matrix.to/#/#DIY_Sovran_SystemsOS:anarchyislove.xyz. Good Luck!

# These instructions will change over time due to new software development and Sovran Systems creator finding more efficient ways to install Sovran_SystemsOS. 10-27-2023

# Also, to fully complete the install, the Bitcoin blockchain will have to download. This could take up to 3 weeks.

# Lastly, if you gift to the computer movement <https://zaps.sovransystems.com> to receive a Sovran Pro, you do not have to do any of this. It is all done for you. On top of that, the Bitcoin blockchain is already installed. 😉

### Requirements

1. First machine with Linux OS already installed (like NixOS, Ubuntu, Arch, etc.) to download and burn the NixOS image to a USB thumb drive.
2. USB thumb drive 16GB or larger
3. Second machine that is ready to have Sovran_SystemsOS installed (Safe Boot turned off in the UEFI[BIOS] and be prepared for the entire storage drive to be ERASED).
4. Second machine needs the following hardware specs:

- Intel or AMD processor (NO ARM processors)
- 16GB of RAM or Larger
- First main internal drive to install Sovran_SystemsOS (NVME 500GB or larger)
- Second internal drive to store the Bitcoin blockchain and the automatic backups (SSD or NVME 2TB or larger)
- Also, the Second internal drive needs to be be installed FIRST into an USB enclosure. If the second drive is SSD, you need a SSD USB enclosure. If the second drive is NVME, you need a NVME USB enclosure. The USB enclosure will be plugged into the first Linux machine.

5. Working Internet connection for both machines
6. Personalized Domain names already purchased from Njal.la. See the explanation here: https://sovransystems.com/how-to-setup/
7. Your Router with ports open (Port Forwarding) to your second machine's internal IP address. This will usually be `192.168.1.(some number)` You will complete this at the end. 

- Port 80
- Port 443
- Port 22
- Port 5349
- Port 8448

## Preparing the Second Internal Drive

1. Install the second internal drive (NVME or SSD) into its appropriate USB enclosure, NOT into the Second machine yet.
2. Plug in the USB enclosure with the second drive installed into the first machine with Linux installed into one of its available USB ports.
3. Open a terminal in the first Linux machine and log in as root.
4. Type in

```bash
wget https://git.sovransystems.com/Sovran_Systems/Sovran_SystemsOS/raw/branch/main/for_new_sovran_pros/sdpsp.sh
```

then press enter.

5. Now, type `bash sdpsp.sh` then press enter.
6. Then the screen will ask for "what block..." which will be the drive in the list that is not mounted,which will be the second internal drive you just plugged in. It might be labeled `sda`, `sdb`, `sdc`, or if it is a NVME it will be `nvme0n1`, or `nvme0n2`.
7. Then the screen will ask for "what partition...,"which will be whatever you typed into the first prompt, but with a "1" on it. For example `sda1`, `sdb1`, `sdc1`, or `nvme0n1p1` or `nvme0n2p1`.
8. Since the script is made to copy the blockchain from another Sovran Pro that already has the full blockchain installed it will throw an error. However, it should complete the setup just fine.
9. Once complete, remove the second drive from the USB enclosure and install it into your second machine in which you are installing Sovran_SystemsOS.

## Preparing the First Main Internal Drive

### Procedure One - Installing base NixOS

 1. On the first machine download the latest NixOS minimal (64-bit Intel/AMD) image from here: https://nixos.org/download
 2. Burn that ISO image onto the USB thumb drive.
 3. Insert the newly created USB thumb drive with the ISO image burned onto it into the second machine.
 4. Reboot the second machine while the USB thumb drive is inserted and boot into the USB thumb drive. This may require you to press the F7 or F12 key at boot. (Also, make sure the second machine has "safe boot" turned off in the UEFI[BIOS]).
 5. Proceed with the NixOS boot menu
 6. Once at the command prompt type in `sudo su` to move to the root user
 7. Once logged into the root user type in `passwd` then set the root user password to `a`
 8. Type in `ip a` to get your internal IP address. It will usually be `192.1681.1.(somenumber)` make a note of this IP as you will need it later.
 9. Now, that you are logged in as the root user type in:

    ```
    curl https://git.sovransystems.com/Sovran_Systems/Sovran_SystemsOS/raw/branch/main/for_new_sovran_pros/psp.sh -o psp.sh
    ```

      the command to install the base NixOS and press enter.
10. Now, type `bash psp.sh` then press enter.
11. The script will ask for name of first main internal drive. Type that in and hit enter. It usually will be `nvme0n1` if it is an NVME drive. If it is a SSD it will be `sda` or `sdb` or `sdc` etc. Basically, it will be the drive without any data and it will not be mounted per the list on the screen.
12. Then the script will ask for the 'root' partition. Type it in and press enter. It will be the LARGER partition and usually named `nvme0n1p1` if it is an NVME drive or `sda1` if it is an SSD. 
13. Then it will ask for the 'boot' partition. Type it in and press enter. It will be the SMALLER partition usually named `nvme0n1p2` or `sda2`.
14. The script will finish installing the base NixOS. At the end it will ask for a root password. Type `a` and press enter and type `a` again to confirm and press enter.
15. Remove the USB thumb drive from the second machine.
16. The machine will reboot into a very basic install of NixOS command prompt.

### Procedure Two - Installing Sovran_SystemsOS

1. Now at the basic install of NixOS from step 16, type `root` to log into root and type the password `a` when asked then press enter.
2. Now you are logged in as `root`.
3. Now type in

   ```
   wget https://git.sovransystems.com/Sovran_Systems/Sovran_SystemsOS/raw/branch/main/for_new_sovran_pros/sp.sh
   ```

   then press enter.
4. Type in `bash sp.sh` then press enter.
5. Next the script will ask for your domain names from Njal.la. Type them in the corresponding prompts and then press enter for each prompt.
6. Then it will ask for an email for the SSL certificates. Type it in and press enter.
7. The script is long so it will take some time.
8. Then it will ask for your root password which is `a` to install Flatpaks.
9. It will finish by stating `All Finished! Please Reboot then Enjoy your New Sovran Pro!`

## Finishing the Install

### Opening The Ports on Your Router - Internal IP

1. Go to port forwarding on your router and open the above mentioned ports to the internal IP (the one you found above) of your new Sovran_SystemsOS machine

### Putting the External IP of your Sovran Pro into your new domain names you just bought at [njal.la](https://njal.la)

1. Log into your [njal.la](https://njal.la) account
2. Make a A record for each subdomain and add your Sovran Pro's external IP address to each subdomain. 

### Setting the Desktop

1. Open the Terminal app and type in: `dconf load / < /home/free/Downloads/Sovran_SystemsOS-Desktop`. Do NOT log in as root.

### Setting Up Nextcloud and Wordpress

#### Nextcloud

1. Open a web browser and navigate to your domain name you bought from [njal.la](https://njal.la)  for example "cloud.myfreedomsite.com" you attributed to your Nextcloud instance.
2. Nextcloud will as you to set up a new account to be used as a log in. Do so.
3. Nextcloud will also ask you where you want the data directory. Type in `/var/lib/nextcloud/data`
4. Nextcloud will ask you to connect the database:
   1. Choose `Postgresql` from the optoins.
   2. Database username is `ncusr`
   3. Database name is `nextclouddb`
   4. Database password is found by doing this:
         1. Open the Terminal app and type in: 

            ```
            ssh -i /home/free/.ssh/factory_login root@[one of your domain names]
            ```

            Remove the brackets when actually executed the command, for example:

            ```
            ssh -i /home/free/.ssh/factory_login root@myfreedomsite.com
            ```

            It will as you for a password which is `gosovransystems` as this is the default temporary password from Sovran Systems.

            Now you will be logged in as root.
         2. Now open the Terminal app and type:

            `cat /var/lib/secrets/nextclouddb`

            and press enter.
         3. Your database password will be displayed in the Terminal window.
         4. Type that into the password field
   5. Now, press install and Nextcloud will be installed. It will take a few minutes. Follow the on screen prompts.

#### Wordpress

1. Open a web browser and navigate to your domain name you bought from [njal.la](https://njal.la) for example "myfreedomsite.com" you attributed to your Wordpress instance.
2. Wordpress will ask you to connect the database:
   1. Database username is `wpusr`
   2. Database name is `wordpressdb`
   3. Database password is found by doing this:
      1. Open the Terminal app and type in: 

         ```
         ssh -i /home/free/.ssh/factory_login root@[one of your domain names]
         ```

         Remove the brackets when actually executed the command, for example:

         ```
         ssh -i /home/free/.ssh/factory_login root@myfreedomsite.com
         ```

         It will as you for a password which is `gosovransystems` as this is the default temporary password from Sovran Systems.

         Now you will be logged in as root.
      2. Now open the Terminal app and type:

         `cat /var/lib/secrets/wordpressdb`

         and press enter.
      3. Your database password will be displayed in the Terminal window.
      4. Type that into the password field
   4. Now, press install and Wordpress will be installed. It will take a few minutes. Follow the on screen prompts.

### Final Install for Coturn and Nextcloud

1. Open the Terminal app and type in: 

   ```
   ssh -i /home/free/.ssh/factory_login root@[one of your domain names]
   ```

   Remove the brackets when actually executed the command, for example:

   ```
   ssh -i /home/free/.ssh/factory_login root@myfreedomsite.com
   ```
2. It will as you for a password which is `gosovransystems` as this is the default temporary password from Sovran Systems.
3. Now you will be logged in as root.
4. Now open the Terminal app and type:

```
sed -i '$e cat /var/lib/nextcloudaddition/nextcloudaddition' /var/lib/www/nextcloud/config/config.php

chown caddy:php /var/lib/www -R

chmod 770 /var/lib/www -R
```

and press enter.

5. Now type

```
set DOMAIN $(cat /var/lib/domains/matrix) && cp -n /var/lib/caddy/.local/share/caddy/certificates/acme.zerossl.com-v2-dv90/{$DOMAIN}/{$DOMAIN}.crt /var/lib/coturn/{$DOMAIN}.crt.pem && cp -n /var/lib/caddy/.local/share/caddy/certificates/acme.zerossl.com-v2-dv90/{$DOMAIN}/{$DOMAIN}.key /var/lib/coturn/{$DOMAIN}.key.pem && chown turnserver:turnserver /var/lib/coturn -R && chmod 770 /var/lib/coturn -R  && systemctl restart coturn
```
and press enter.

### Everything now will be installed regarding Sovran_SystemsOS. The remaining setup will be only for the frontend user account creations for BTCpayserver, Vaultwarden, connecting the node to Sparrow wallet and Bisq.

### Congratulations! 🎉