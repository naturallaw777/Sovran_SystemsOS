# Sovran Systems offers limited support of a DIY install of Sovran_SystemsOS. You can reach out to others in the matrix room https://matrix.to/#/#DIY_Sovran_SystemsOS:anarchyislove.xyz.

# These instructions will change over time due to new software development and Sovran Systems creator finding more efficient ways to install Sovran_SystemsOS. 9-12-2024

# Also, to fully complete the install, the Bitcoin blockchain will have to download. This could take up to 3 weeks.

# Lastly, if you gift to the computer movement <https://zaps.sovransystems.com> to receive a Sovran Pro, you do not have to do any of this. It is all done for you. On top of that, the Bitcoin blockchain is already installed. 😉

### Requirements

1. First computer with Linux OS already installed (like NixOS, Ubuntu, Arch, etc.) to download and burn the NixOS image to a USB thumb drive.
2. USB thumb drive 16GB or larger
3. Second computer that is ready to have Sovran_SystemsOS installed (Safe Boot turned off in the UEFI[BIOS] and be prepared for the entire storage drive to be ERASED!).
4. Second computer needs the following hardware specs:

- Intel or AMD processor (NO ARM processors)
- 32GB of RAM or Larger
- First main NVME internal drive to install Sovran_SystemsOS (500GB or larger)
- Second NVME internal drive to store the Bitcoin blockchain and the automatic backups (NVME 4TB or larger)
- Also, the second NVME internal drive needs to be installed FIRST into a USB enclosure. You will need a NVME USB enclosure. The USB enclosure will be plugged into the first Linux machine.

5. Working Internet connection for both computers
6. Personalized Domain names already purchased from Njal.la. See the explanation here: https://sovransystems.com/how-to-setup/
7. Your Router with ports open (Port Forwarding) to your second machine's internal IP address. This will usually be `192.168.1.(some number)` You will complete this at the end.

- Port 80
- Port 443
- Port 22
- Port 5349
- Port 8448

## Preparing the Second Internal Drive

1. Install the second NVME internal drive into the USB enclosure, NOT into the Second computer yet.
2. Plug in the USB enclosure into the first computer with Linux OS already installed into one of its available USB ports.
3. **Please Make Sure You Know The Existing Storage Names On This First Linux Computer. If You Run The Script Below And You Do Not Know What You Are Doing, You Could Potentially Erase Your First Linux Computer's Data. I Am Not Responsibly For Your Errors**
4. Open a terminal in the first Linux computer and log in as root.
5. Type in or copy and paste:

```bash
wget https://git.sovransystems.com/Sovran_Systems/Sovran_SystemsOS/raw/branch/main/for_new_sovran_pros/sdpsp.sh
```

then press enter.

6. Now, type `bash sdpsp.sh` then press enter.
7. Then the screen will ask for "what block..." which will be the drive in the list that is not mounted, which will be the drive you just plugged in. It might be labeled `sda`, or `sdb` etc. Type in the drive name and press `enter`.
8. Then the screen will ask for "what partition...,"which will be whatever you typed into the first prompt, but with a "1" on it. For example, `sda1` or `sdb1`. Type it into the terminal and press `enter`.
9. Since the script is made to copy the blockchain from another Sovran Pro that already has the full blockchain installed it will throw an error. However, it should complete the setup just fine.
10. Once complete, remove the second drive from the USB enclosure and install it into your second computer in which you are installing Sovran_SystemsOS.

## Preparing the First Main Internal Drive

### Procedure One - Installing base NixOS

 1. Still on the first computer with Linux OS already installed, download the latest NixOS <u>minimal</u> (64-bit Intel/AMD) image from here: https://nixos.org/download
 2. Burn that ISO image onto the USB thumb drive.
 3. Insert the newly created USB thumb drive with the ISO image into the second computer (the one you are installing Sovran_SystemsOS).
 4. Reboot the second computer while the USB thumb drive is inserted and boot into the USB thumb drive. This may require you to press the F7 or F12 key at boot. (Also, make sure the second computer has "safe boot" turned off in the UEFI[BIOS]).
 5. Proceed with the NixOS boot menu
 6. Once at the command prompt type in `sudo su` to move to the root user
 7. Once logged into the root user type in `passwd` then set the root user password to `a`
 8. Type in `ip a` to get your internal IP address. It will usually be `192.1681.1.(somenumber)` make a note of this IP as you will need it later.
 9. Now, that you are logged in as the root user type in or copy and paste:

    ```bash
    curl https://git.sovransystems.com/Sovran_Systems/Sovran_SystemsOS/raw/branch/main/for_new_sovran_pros/psp_physical_ram.sh -o psp_physical_ram.sh
    ```

    the command to install the base NixOS and press enter.
10. Now, type `bash psp_physical_ram.sh` then press enter.
11. The script will ask for name of first main internal drive. It usually will be `nvme0n1`. Basically, it will be the drive without any data and it will not be mounted per the list on the screen. Type in the name and press enter on the keyboard.
12. Then the script will ask for the 'Boot' partition. It will be the SMALLER partition and usually named `nvme0n1p1`. Type in the name and press enter on the keyboard.
13. Then it will ask for the 'Primary' partition. It will be the LARGER partition usually named `nvme0n1p2`. Type in the name and press enter on the keyboard.
14. The script will finish installing the base NixOS. At the end it will ask for a root password. Type `a` and press enter and type `a` again to confirm and press enter.
15. The machine will reboot into a very basic install of NixOS command prompt.
16. Remove the USB thumb drive from the second computer.


### Procedure Two  - Opening The Ports on Your Router - Internal IP

1. Go to port forwarding on your router and open the above mentioned ports to the internal IP (the one you found above) of your new Sovran_SystemsOS machine


### Procedure Three - Installing Sovran_SystemsOS


1. Now at the basic install of NixOS from Procedure One, type `root` to log into root and type the password `a` when asked then press enter.
2. Now you are logged in as `root`.
3. Now type in or copy and paste:

   ```bash
   wget https://git.sovransystems.com/Sovran_Systems/Sovran_SystemsOS/raw/branch/main/for_new_sovran_pros/sp.sh
   ```

   then press enter.
4. Type in `bash sp.sh` then press enter.
5. Next the script will ask for your domain names from Njal.la. Type them in the corresponding prompts and then press enter for each prompt.
6. Then it will ask for an email for the SSL certificates. Type it in and press enter.
7. The script is long so it will take some time.
8. It will finish by stating `All Finished! Please Reboot then Enjoy your New Sovran Pro!`
9. Press the power button on the machine for it to turn off THEN press it again to power the machine

## Finishing the Install


### Putting the External IP of your New DIY Sovran Pro into your new domain names you just bought at [njal.la](https://njal.la)

1. On your New DIY Sovran Pro, log into your [njal.la](https://njal.la) account
2. Make a "dynamic" record for each subdomain 
3. Njal.la will now display a `curl` command for each sub-domain.
4. Open the `Terminal` on your New DIY Sovran Pro and type in or copy and paste:

    ```bash
    ssh root@localhost
    ```
    It will as you for a password which is `gosovransystems` as this is the default temporary password from Sovran Systems. 
    
    Now you will be logged in as root.

5. Now type:

    `nano /var/lib/njalla/njalla.sh`

    and press enter.


3. Paste the `curl` commands from njal.la's website for each sub-domain. Each `curl` command gets a new line. For example:

   ```bash
   ...
   curl "https://njal.la/update/?h=test.testsovransystems.com&k=8n7vk3afj-jkyg37&a=${IP}"
   curl "https://njal.la/update/?h=zap.testsovransystems.com&k=8no*73afj-jkygi2ea=${IP}"
   ...
   
   ```
   ##### Make sure the default `&auto` from njal.la is replaced by `&a=${IP}` at the end of each `curl` command in the `/var/lib/njalla/njalla.sh` as in the example above.

7. After you have added all the sub-domins into `/var/lib/njalla/njalla.sh`, press `ctrl + s` then press `ctrl + x` to save and exit `nano`.

8. Close the `Terminal`.

### Setting the Desktop

1. Open the `Terminal` again and type in: `dconf load / < /home/free/Downloads/Sovran_SystemsOS-Desktop`. Do NOT log in as root.

2. Close the `Terminal`.

### Setting Up Nextcloud and Wordpress

#### Nextcloud

1. Open a web browser and navigate to your domain name you bought from [njal.la](https://njal.la) for example "cloud.myfreedomsite.com" you attributed to your Nextcloud instance.
2. Nextcloud will as you to set up a new account to be used as a log in. Do so.
3. Nextcloud will also ask you where you want the data directory. Type in `/var/lib/nextcloud/data`
4. Nextcloud will ask you to connect the database:
   1. Choose `Postgresql` from the optoins.
   2. Database username is `ncusr`
   3. Database name is `nextclouddb`
   4. Database password is found by doing this:
      1. Open the `Terminal` again, then type in or copy and paste:

         ```bash
         ssh root@localhost
         ```
         Now you will be logged in as root.

      2. Now type:

         `cat /var/lib/secrets/nextclouddb`

         and press enter.

      3. Your database password will be displayed in the `Terminal` window.
      4. Type that into the password field

5. Now, press `Install` on the Nextcloud website and Nextcloud will be installed. It will take a few minutes. Follow the on screen prompts.

#### Wordpress

1. Open a web browser and navigate to your domain name you bought from [njal.la](https://njal.la) for example "myfreedomsite.com" you attributed to your Wordpress instance.
2. Wordpress will ask you to connect the database:
   1. Database username is `wpusr`
   2. Database name is `wordpressdb`
   4. Database password is found by doing this:
      1. Open the `Terminal` again, then type in or copy and paste:

         ```bash
         ssh root@localhost
         ```
         Now you will be logged in as root.

      2. Now type:

         `cat /var/lib/secrets/wordpressdb`

         and press enter.

      3. Your database password will be displayed in the `Terminal` window.
      4. Type that into the password field

5. Now, press `Install` on the Wordpress website and Wordpress will be installed. It will take a few minutes. Follow the on screen prompts.

### Final Install for Coturn, Flatpak, and Nextcloud

1. Staying in the `Terminal` type in or copy and paste:

    ```bash
    sed -i '$e cat /var/lib/nextcloudaddition/nextcloudaddition' /var/lib/www/nextcloud/config/config.php

    chown caddy:php /var/lib/www -R

    chmod 700 /var/lib/www R
    ```
    and press enter.

2. Now type or copy and paste:

    ```bash
    set DOMAIN $(cat /var/lib/domains/matrix) && cp -n /var/lib/caddy/.local/share/caddy/certificates/acme-v02.api.letsencrypt.org-directory/{$DOMAIN}/{$DOMAIN}.crt /var/lib/coturn/{$DOMAIN}.crt.pem && cp -n /var/lib/caddy/.local/share/caddy/certificates/acme-v02.api.letsencrypt.org-directory/{$DOMAIN}/{$DOMAIN}.key /var/lib/coturn/{$DOMAIN}.key.pem && chown turnserver:turnserver /var/lib/coturn -R && chmod 770 /var/lib/coturn -R  && systemctl restart coturn
    ```
    and press enter.

3. Now type or copy and paste:

    ```bash
    sudo -u free flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
    ```
    and press enter.

    It will ask for your `Administrator` password and to get the password open a new `Terminal` window and type:
    
    ```bash
    ssh root@localhost
    ```
    press enter.

    Now you will be logged in as root.

    Now type:

    ```bash
    cat /var/lib/secrets/main
    ```
    Then the `Administrator`'s password will be displayed. Copy and paste the password into the other `Terminal` window that is open. Then press enter.

    Now you can close the `Terminal`.

### Everything now will be installed regarding Sovran_SystemsOS. The remaining setup will be only for the front-end user account creations for BTCpayserver, Vaultwarden, connecting the node to Sparrow wallet and Bisq.

### Congratulations! 🎉
