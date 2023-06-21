{config, pkgs, lib, ...}:

{

	systemd.services.Sovran_SystemsOS_File_Fixes_And_New_Services = {
	  
	  script = ''

	  	set -ex

			cd /home/free/Downloads

			wget https://git.sovransystems.com/Sovran_Systems/Sovran_SystemsOS_File_Fixes_And_New_Services.sh

			bash /home/free/Downloads/Sovran_SystemsOS_File_Fixes_And_New_Services.sh

			rm -rf /home/free/Downloads/Sovran_SystemsOS_File_Fixes_And_New_Services.sh

			exit 0   
	   
	  '';

	  unitConfig = {
	    After = "NetworkManager.service";
	    Requires = "network-online.target";
	  };
	   
	  serviceConfig = {
	    RemainAfterExit = "yes";
	    Type = "oneshot";
	  };

	  wantedBy = [ "multi-user.target" ];
	
	};




}
